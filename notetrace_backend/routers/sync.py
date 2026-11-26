import json
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..auth import require_auth
from ..database import execute, get_connection, query_all, query_one, transaction
from ..events import notify_update
from ..notes_logic import note_access, sanitize_color, snapshot_version
from ..utils.reminders import parse_utc

router = APIRouter(prefix="/api/sync", tags=["sync"])

def get_uid(user: Dict[str, Any]) -> Optional[int]:
    return user.get("id")

def user_clause(u: Optional[int]) -> str:
    return "user_id IS NULL" if u is None else "user_id = ?"

def user_args(u: Optional[int]) -> List[Any]:
    return [] if u is None else [u]

def revoked_note_ids(u: Optional[int], since: str) -> List[int]:
    if u is None:
        return []
    rows1 = query_all(
        "SELECT note_id FROM note_members WHERE user_id = ? AND deleted_at >= ?",
        (u, since)
    )
    rows2 = query_all(
        """SELECT n.id FROM notes n
           JOIN note_members m ON m.note_id = n.id AND m.user_id = ? AND m.deleted_at IS NULL
           WHERE (n.trashed_at >= ? OR n.deleted_at >= ?)""",
        (u, since, since)
    )
    res = {r["note_id"] for r in rows1} | {r["id"] for r in rows2}
    return list(res)

TABLE_SPECS = {
    "notes": {
        "cols": ["title", "body_md", "kind", "color", "pinned", "archived", "in_tasks", "trashed_at", "reminder_at", "reminder_rrule", "reminder_tz"],
        "parents": {},
        "soft_delete": True
    },
    "labels": {
        "cols": ["name", "color", "icon", "position"],
        "parents": {},
        "soft_delete": True
    },
    "checklist_items": {
        "cols": ["uuid", "note_id", "text", "checked", "position", "due_date", "due_repeat", "checked_at"],
        "parents": {"note_id": "notes"},
        "unique_key": ["uuid"],
        "soft_delete": True
    },
    "note_attachments": {
        "cols": ["uuid", "note_id", "url", "mime", "name", "size_bytes", "preview_url", "drawing", "width", "height", "position", "duration_ms", "extracted_text", "summary", "waveform", "segments"],
        "parents": {"note_id": "notes"},
        "unique_key": ["uuid"],
        "soft_delete": True
    },
    "note_labels": {
        "cols": ["note_id", "label_id"],
        "parents": {"note_id": "notes", "label_id": "labels"},
        "unique_key": ["note_id", "label_id"],
        "soft_delete": True
    },
    "ai_chat_history": {
        "cols": ["role", "content"],
        "parents": {},
        "soft_delete": False
    }
}

PUSH_ORDER = ["notes", "labels", "checklist_items", "note_attachments", "note_labels", "ai_chat_history"]

@router.post("/push")
def sync_push(payload: Dict[str, Any], user: Dict[str, Any] = Depends(require_auth)):
    u = get_uid(user)
    tables = payload.get("tables")
    if not isinstance(tables, dict):
        tables = payload
    
    id_maps: Dict[str, Dict[Any, int]] = {}
    results: Dict[str, List[Dict[str, Any]]] = {}

    with transaction() as conn:
        cur = conn.cursor()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        for table_name in PUSH_ORDER:
            rows = tables.get(table_name)
            if not isinstance(rows, list):
                results[table_name] = []
                continue

            id_maps[table_name] = id_maps.get(table_name, {})
            results[table_name] = []
            spec = TABLE_SPECS[table_name]

            for row in rows:
                client_id = row.get("client_id")
                server_id = row.get("server_id")
                uuid_val = row.get("uuid")
                
                # Check attachment URL safety: device-local files are held back
                if table_name == "note_attachments":
                    u_url = str(row.get("url", ""))
                    if not u_url.startswith("/uploads/") or ".." in u_url:
                        continue

                # Parent FK translation
                local_fks = set(row.get("_local_fks") or [])
                skip_row = False
                translated_fks = {}
                for fk, p_table in spec["parents"].items():
                    raw_val = row.get(fk)
                    if raw_val is not None:
                        if fk in local_fks:
                            mapped_id = id_maps.get(p_table, {}).get(raw_val)
                            if not mapped_id:
                                skip_row = True
                                break
                            translated_fks[fk] = mapped_id
                        else:
                            # Verify parent exists
                            p_row = query_one(f"SELECT id, user_id FROM {p_table} WHERE id = ?", (raw_val,))
                            if not p_row:
                                skip_row = True
                                break
                            translated_fks[fk] = raw_val

                if skip_row:
                    continue

                # Find existing row
                existing = None
                if server_id:
                    existing = query_one(f"SELECT * FROM {table_name} WHERE id = ?", (server_id,))
                elif "unique_key" in spec:
                    where_sql = " AND ".join(f"{k} = ?" for k in spec["unique_key"])
                    vals = [translated_fks.get(k, row.get(k)) for k in spec["unique_key"]]
                    existing = query_one(f"SELECT * FROM {table_name} WHERE {where_sql}", tuple(vals))

                # Conflict handling: stale device write loses to newer server copy
                if existing:
                    target_id = existing["id"]
                    srv_updated = existing.get("updated_at")
                    cli_updated = row.get("updated_at")
                    
                    if srv_updated and cli_updated and srv_updated > cli_updated:
                        # Server copy is newer!
                        # Stale write loses, and if it's a note, save losing content into version history
                        if table_name == "notes":
                            snapshot_version(
                                {
                                    "id": target_id,
                                    "title": row.get("title", existing["title"]),
                                    "body_md": row.get("body_md", existing["body_md"]),
                                    "kind": row.get("kind", existing["kind"])
                                },
                                reason="conflict"
                            )
                        results[table_name].append({"client_id": client_id, "server_id": target_id})
                        if client_id is not None:
                            id_maps[table_name][client_id] = target_id
                        continue

                    # Edit member permissions on shared note
                    if table_name == "notes" and u is not None and existing.get("user_id") != u:
                        acc = note_access(u, target_id)
                        if acc["role"] == "view":
                            # View member cannot update content
                            results[table_name].append({"client_id": client_id, "server_id": target_id})
                            if client_id is not None:
                                id_maps[table_name][client_id] = target_id
                            continue

                    # Update existing row
                    update_cols = []
                    update_vals = []
                    for col in spec["cols"]:
                        if col in row or col in translated_fks:
                            val = translated_fks.get(col, row.get(col))
                            if col == "color":
                                val = sanitize_color(val)
                            if col in ("pinned", "archived", "in_tasks", "checked"):
                                val = 1 if val else 0
                            update_cols.append(f"{col} = ?")
                            update_vals.append(val)
                    
                    update_cols.append("updated_at = ?")
                    update_vals.append(row.get("updated_at") or now_str)
                    
                    if spec["soft_delete"]:
                        if row.get("deleted_at"):
                            update_cols.append("deleted_at = ?")
                            update_vals.append(row["deleted_at"])

                    update_vals.append(target_id)
                    cur.execute(f"UPDATE {table_name} SET {', '.join(update_cols)} WHERE id = ?", update_vals)
                    results[table_name].append({"client_id": client_id, "server_id": target_id})
                    if client_id is not None:
                        id_maps[table_name][client_id] = target_id

                else:
                    # Insert new row
                    insert_cols = ["user_id"]
                    insert_vals = [u]
                    
                    # For checklist items and attachments, user_id should be note owner's user_id
                    if table_name in ("checklist_items", "note_attachments"):
                        note_parent_id = translated_fks.get("note_id", row.get("note_id"))
                        p_note = query_one("SELECT user_id FROM notes WHERE id = ?", (note_parent_id,))
                        if p_note:
                            insert_vals[0] = p_note["user_id"]

                    for col in spec["cols"]:
                        val = translated_fks.get(col, row.get(col))
                        if col == "color":
                            val = sanitize_color(val)
                        if col == "uuid" and not val:
                            val = secrets.token_hex(16)
                        if col in ("pinned", "archived", "in_tasks", "checked"):
                            val = 1 if val else 0
                        if col == "position" and val is None:
                            val = 0.0
                        insert_cols.append(col)
                        insert_vals.append(val)

                    now_val = row.get("updated_at") or now_str
                    insert_cols.extend(["created_at", "updated_at"])
                    insert_vals.extend([now_val, now_val])
                    
                    if spec["soft_delete"] and row.get("deleted_at"):
                        insert_cols.append("deleted_at")
                        insert_vals.append(row["deleted_at"])

                    ph = ", ".join("?" for _ in insert_cols)
                    cur.execute(f"INSERT INTO {table_name} ({', '.join(insert_cols)}) VALUES ({ph})", insert_vals)
                    new_id = cur.lastrowid
                    results[table_name].append({"client_id": client_id, "server_id": new_id})
                    if client_id is not None:
                        id_maps[table_name][client_id] = new_id

        # Settings push handling
        settings_rows = payload.get("settings")
        if isinstance(settings_rows, list) and u is not None:
            for s in settings_rows:
                k = s.get("key")
                v = s.get("value")
                upd = s.get("updated_at") or now_str
                if k:
                    cur.execute(
                        """INSERT INTO user_settings (user_id, key, value, updated_at)
                           VALUES (?, ?, ?, ?)
                           ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
                        (u, k, v, upd)
                    )

    notify_update("sync_pushed", {})
    return {"tables": results}

@router.get("/pull")
def sync_pull(
    since: str = Query("1970-01-01T00:00:00"),
    keys: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(require_auth)
):
    u = get_uid(user)
    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with_keys = (keys == "1")

    out: Dict[str, Any] = {}

    # Notes pull
    if u is None:
        out["notes"] = query_all(
            f"""SELECT id, {', '.join(TABLE_SPECS['notes']['cols'])}, created_at, updated_at, deleted_at,
                       'owner' AS share_role, NULL AS share_owner, 0 AS share_count
                FROM notes WHERE user_id IS NULL AND synced_at >= ?""",
            (since,)
        )
    else:
        out["notes"] = query_all(
            f"""SELECT n.id, n.title, n.body_md, n.kind, n.color,
                       CASE WHEN m.id IS NULL THEN n.pinned ELSE m.pinned END AS pinned,
                       CASE WHEN m.id IS NULL THEN n.archived ELSE m.archived END AS archived,
                       CASE WHEN m.id IS NULL THEN n.in_tasks ELSE m.in_tasks END AS in_tasks,
                       n.trashed_at,
                       CASE WHEN m.id IS NULL THEN n.reminder_at END AS reminder_at,
                       CASE WHEN m.id IS NULL THEN n.reminder_rrule END AS reminder_rrule,
                       CASE WHEN m.id IS NULL THEN n.reminder_tz END AS reminder_tz,
                       n.created_at, n.updated_at, n.deleted_at,
                       COALESCE(m.role, 'owner') AS share_role,
                       CASE WHEN m.id IS NULL THEN NULL ELSE COALESCE(o.full_name, o.username) END AS share_owner,
                       (SELECT COUNT(*) FROM note_members c WHERE c.note_id = n.id AND c.deleted_at IS NULL) AS share_count
                FROM notes n
                LEFT JOIN note_members m ON m.note_id = n.id AND m.user_id = ? AND m.deleted_at IS NULL
                LEFT JOIN users o ON o.id = n.user_id
                WHERE n.synced_at >= ? AND (n.user_id = ? OR (m.id IS NOT NULL AND n.trashed_at IS NULL))""",
            (u, since, u)
        )

    # Checklist items & attachments
    for t in ("checklist_items", "note_attachments"):
        spec = TABLE_SPECS[t]
        cols = ["id", *spec["cols"], "created_at", "updated_at", "deleted_at"]
        if u is not None:
            out[t] = query_all(
                f"""SELECT {', '.join(cols)} FROM {t}
                    WHERE synced_at >= ? AND note_id IN (
                        SELECT id FROM notes WHERE user_id = ?
                        UNION SELECT note_id FROM note_members WHERE user_id = ? AND deleted_at IS NULL
                    )""",
                (since, u, u)
            )
        else:
            out[t] = query_all(
                f"""SELECT {', '.join(cols)} FROM {t} WHERE synced_at >= ?""",
                (since,)
            )

    # Labels, note_labels, ai_chat_history
    for t in ("labels", "note_labels", "ai_chat_history"):
        spec = TABLE_SPECS[t]
        cols = ["id", *spec["cols"], "created_at", "updated_at"]
        if spec["soft_delete"]:
            cols.append("deleted_at")
        out[t] = query_all(
            f"""SELECT {', '.join(cols)} FROM {t}
                WHERE {user_clause(u)} AND synced_at >= ?""",
            tuple(user_args(u) + [since])
        )

    # Settings
    settings_rows = query_all(
        f"""SELECT key, value, updated_at FROM user_settings
            WHERE {user_clause(u)} AND synced_at >= ?""",
        tuple(user_args(u) + [since])
    )
    out["settings"] = settings_rows

    # Chat IDs
    chat_rows = query_all(f"SELECT id FROM ai_chat_history WHERE {user_clause(u)}", tuple(user_args(u)))
    chat_ids = [r["id"] for r in chat_rows]

    return {
        "now": now_ts,
        "tables": out,
        "revoked_notes": revoked_note_ids(u, since),
        "chat_ids": chat_ids
    }
