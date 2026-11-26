import json
import re
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from .database import (
    execute,
    execute_count,
    get_connection,
    query_all,
    query_one,
    transaction,
)
from .utils.reminders import parse_utc, REPEATS
from .utils.task_rules import clean_task_repeat, next_due_date

NOTE_KINDS = {'text', 'checklist'}
NOTE_COLORS = {
    'ember', 'clay', 'amber', 'sand', 'lime', 'moss', 'sage', 'mint',
    'sky', 'tide', 'indigo', 'plum', 'orchid', 'rose', 'bark', 'slate'
}
TRASH_RETENTION_DAYS = 30
MEMBER_ROLES = {'view', 'edit'}
IMPORT_BATCH_MAX = 500
ATTACHMENTS_MAX_PER_NOTE = 50

def now_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def sanitize_color(color: Optional[str]) -> Optional[str]:
    if not color:
        return None
    c = str(color).strip().lower()
    return c if c in NOTE_COLORS else None

def note_access(user_id: Optional[int], note_id: int) -> Dict[str, Any]:
    """Determines user's access level to a note: 'owner', 'edit', 'view', or None."""
    note = query_one("SELECT * FROM notes WHERE id = ?", (note_id,))
    if not note:
        return {"note": None, "role": None}
    
    if user_id is None:
        # Single-user mode
        if note.get("deleted_at") is not None:
            return {"note": None, "role": None}
        return {"note": note, "role": "owner"}
    
    if note.get("user_id") == user_id:
        if note.get("deleted_at") is not None:
            return {"note": None, "role": None}
        return {"note": note, "role": "owner"}
    
    # Check note_members
    member = query_one(
        "SELECT * FROM note_members WHERE note_id = ? AND user_id = ? AND deleted_at IS NULL",
        (note_id, user_id)
    )
    if member and note.get("deleted_at") is None and note.get("trashed_at") is None:
        return {"note": note, "role": member.get("role", "view"), "member": member}
        
    return {"note": None, "role": None}

def hydrate_note(user_id: Optional[int], note_row: Dict[str, Any]) -> Dict[str, Any]:
    note = dict(note_row)
    note_id = note["id"]
    
    # Check member role / personal pin / archive
    member = None
    if user_id is not None and note.get("user_id") != user_id:
        member = query_one(
            "SELECT * FROM note_members WHERE note_id = ? AND user_id = ? AND deleted_at IS NULL",
            (note_id, user_id)
        )
        if member:
            note["share_role"] = member.get("role", "view")
            note["pinned"] = bool(member.get("pinned", 0))
            note["archived"] = bool(member.get("archived", 0))
            note["in_tasks"] = bool(member.get("in_tasks", 0))
            owner_user = query_one("SELECT username, full_name FROM users WHERE id = ?", (note["user_id"],))
            if owner_user:
                note["share_owner"] = owner_user.get("full_name") or owner_user.get("username")
    else:
        note["share_role"] = "owner"
        note["pinned"] = bool(note.get("pinned", 0))
        note["archived"] = bool(note.get("archived", 0))
        note["in_tasks"] = bool(note.get("in_tasks", 0))
        
        # Share count for owner
        cnt = query_one("SELECT COUNT(*) as c FROM note_members WHERE note_id = ? AND deleted_at IS NULL", (note_id,))
        note["share_count"] = cnt["c"] if cnt else 0

    # Items for checklist
    items = query_all(
        """SELECT id, uuid, text, checked, position, due_date, due_repeat, checked_at, created_at, updated_at
           FROM checklist_items
           WHERE note_id = ? AND deleted_at IS NULL
           ORDER BY position ASC, id ASC""",
        (note_id,)
    )
    for it in items:
        it["checked"] = bool(it.get("checked", 0))
    note["items"] = items

    # Labels
    # If member, labels are personal to the member!
    label_owner_id = user_id if user_id is not None else note.get("user_id")
    if label_owner_id is not None:
        labels = query_all(
            """SELECT l.id, l.name, l.color, l.icon, l.position
               FROM labels l
               JOIN note_labels nl ON nl.label_id = l.id
               WHERE nl.note_id = ? AND nl.user_id = ? AND nl.deleted_at IS NULL AND l.deleted_at IS NULL
               ORDER BY l.position ASC, l.id ASC""",
            (note_id, label_owner_id)
        )
    else:
        labels = query_all(
            """SELECT l.id, l.name, l.color, l.icon, l.position
               FROM labels l
               JOIN note_labels nl ON nl.label_id = l.id
               WHERE nl.note_id = ? AND nl.deleted_at IS NULL AND l.deleted_at IS NULL
               ORDER BY l.position ASC, l.id ASC""",
            (note_id,)
        )
    note["labels"] = labels

    # Attachments
    attachments = query_all(
        """SELECT id, uuid, url, mime, width, height, position, duration_ms, waveform, segments,
                  extracted_text, summary, name, size_bytes, preview_url, (drawing IS NOT NULL) AS has_drawing,
                  created_at, updated_at
           FROM note_attachments
           WHERE note_id = ? AND deleted_at IS NULL
           ORDER BY position ASC, id ASC""",
        (note_id,)
    )
    for att in attachments:
        att["has_drawing"] = bool(att.get("has_drawing"))
    note["attachments"] = attachments

    return note

def list_notes(
    user_id: Optional[int],
    view: str = "notes",
    label_id: Optional[int] = None,
    q: str = "",
    kind: Optional[str] = None
) -> List[Dict[str, Any]]:
    params: List[Any] = []
    where_clauses: List[str] = ["n.deleted_at IS NULL"]
    
    # Ownership or membership condition
    if user_id is not None:
        where_clauses.append("""
            (n.user_id = ? OR n.id IN (
                SELECT note_id FROM note_members WHERE user_id = ? AND deleted_at IS NULL
            ))
        """)
        params.extend([user_id, user_id])
        
    if view == "notes":
        where_clauses.append("n.trashed_at IS NULL")
        # Personal archive check
        if user_id is not None:
            where_clauses.append("""
                (
                    (n.user_id = ? AND n.archived = 0)
                    OR
                    (n.user_id != ? AND (SELECT archived FROM note_members WHERE note_id = n.id AND user_id = ? AND deleted_at IS NULL) = 0)
                )
            """)
            params.extend([user_id, user_id, user_id])
        else:
            where_clauses.append("n.archived = 0")
            
    elif view == "archive":
        where_clauses.append("n.trashed_at IS NULL")
        if user_id is not None:
            where_clauses.append("""
                (
                    (n.user_id = ? AND n.archived = 1)
                    OR
                    (n.user_id != ? AND (SELECT archived FROM note_members WHERE note_id = n.id AND user_id = ? AND deleted_at IS NULL) = 1)
                )
            """)
            params.extend([user_id, user_id, user_id])
        else:
            where_clauses.append("n.archived = 1")
            
    elif view == "trash":
        where_clauses.append("n.trashed_at IS NOT NULL")
        if user_id is not None:
            # Only owner sees notes in trash
            where_clauses.append("n.user_id = ?")
            params.append(user_id)
            
    elif view == "reminders":
        where_clauses.append("n.trashed_at IS NULL AND n.reminder_at IS NOT NULL")
        if user_id is not None:
            # Reminders only belong to owner
            where_clauses.append("n.user_id = ?")
            params.append(user_id)
            
    elif view == "shared":
        where_clauses.append("n.trashed_at IS NULL")
        if user_id is not None:
            where_clauses.append("""
                (n.user_id != ? AND n.id IN (
                    SELECT note_id FROM note_members WHERE user_id = ? AND deleted_at IS NULL
                ))
            """)
            params.extend([user_id, user_id])

    if kind:
        where_clauses.append("n.kind = ?")
        params.append(kind)

    if label_id:
        target_uid = user_id if user_id is not None else 0
        where_clauses.append("""
            n.id IN (
                SELECT note_id FROM note_labels
                WHERE label_id = ? AND (user_id = ? OR ? = 0) AND deleted_at IS NULL
            )
        """)
        params.extend([label_id, target_uid, target_uid])

    if q and q.strip():
        # FTS5 search
        safe_q = re.sub(r'["\*\^]', ' ', q).strip()
        tokens = [f'"{tok}"*' for tok in safe_q.split() if tok]
        if tokens:
            fts_query_str = " ".join(tokens)
            where_clauses.append("""
                n.id IN (
                    SELECT rowid FROM notes_fts WHERE notes_fts MATCH ?
                )
            """)
            params.append(fts_query_str)

    where_sql = " AND ".join(where_clauses)
    
    # Pinned sorting handling for members vs owner
    if user_id is not None:
        sql = f"""
            SELECT n.*,
                   CASE WHEN n.user_id = ? THEN n.pinned
                        ELSE COALESCE((SELECT pinned FROM note_members WHERE note_id = n.id AND user_id = ? AND deleted_at IS NULL), 0)
                   END AS effective_pinned
            FROM notes n
            WHERE {where_sql}
            ORDER BY effective_pinned DESC, n.updated_at DESC, n.id DESC
        """
        full_params = [user_id, user_id] + params
    else:
        sql = f"""
            SELECT n.*, n.pinned AS effective_pinned
            FROM notes n
            WHERE {where_sql}
            ORDER BY effective_pinned DESC, n.updated_at DESC, n.id DESC
        """
        full_params = params

    rows = query_all(sql, full_params)
    return [hydrate_note(user_id, r) for r in rows]

def get_note(user_id: Optional[int], note_id: int) -> Optional[Dict[str, Any]]:
    access = note_access(user_id, note_id)
    if not access["role"]:
        return None
    return hydrate_note(user_id, access["note"])

def snapshot_version(note_row: Dict[str, Any], reason: str = "edit"):
    note_id = note_row["id"]
    last_v = query_one(
        "SELECT * FROM note_versions WHERE note_id = ? ORDER BY id DESC LIMIT 1",
        (note_id,)
    )
    if last_v:
        # Check if identical or created within last 60 minutes
        last_dt = parse_utc(last_v.get("created_at"))
        now_dt = datetime.now(timezone.utc)
        if last_dt and (now_dt - last_dt).total_seconds() < 3600 and reason == "edit":
            return
            
    items = query_all(
        "SELECT uuid, text, checked, position FROM checklist_items WHERE note_id = ? AND deleted_at IS NULL ORDER BY position ASC",
        (note_id,)
    )
    for it in items:
        it["checked"] = bool(it["checked"])
        
    items_json = json.dumps(items) if items else None
    execute(
        """INSERT INTO note_versions (note_id, title, body_md, kind, items_json, reason, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (note_id, note_row.get("title", ""), note_row.get("body_md", ""), note_row.get("kind", "text"), items_json, reason, now_utc_str())
    )

def rename_links_in_notes(user_id: Optional[int], old_title: str, new_title: str, current_note_id: int):
    if not old_title or not new_title or old_title.strip() == new_title.strip():
        return
        
    # Check if another note exists with either old or new title (if so, skip to avoid ambiguous link conflicts)
    target_uid = user_id if user_id is not None else 0
    dup_old = query_one(
        "SELECT id FROM notes WHERE lower(title) = lower(?) AND id != ? AND user_id = ? AND deleted_at IS NULL",
        (old_title, current_note_id, target_uid)
    )
    dup_new = query_one(
        "SELECT id FROM notes WHERE lower(title) = lower(?) AND id != ? AND user_id = ? AND deleted_at IS NULL",
        (new_title, current_note_id, target_uid)
    )
    if dup_old or dup_new:
        return

    # Escape regex special characters in old_title
    pattern = re.compile(rf'\[\[{re.escape(old_title)}\]\]', re.IGNORECASE)
    replacement = f'[[{new_title}]]'

    notes = query_all("SELECT id, body_md FROM notes WHERE user_id = ? AND deleted_at IS NULL", (target_uid,))
    for n in notes:
        body = n.get("body_md") or ""
        if pattern.search(body):
            new_body = pattern.sub(replacement, body)
            execute(
                "UPDATE notes SET body_md = ?, updated_at = ? WHERE id = ?",
                (new_body, now_utc_str(), n["id"])
            )

def create_note(user_id: Optional[int], data: Dict[str, Any]) -> Dict[str, Any]:
    with transaction() as conn:
        title = str(data.get("title", "")).strip()
        body_md = str(data.get("body_md", ""))
        kind = data.get("kind", "text")
        if kind not in NOTE_KINDS:
            kind = "text"
            
        color = sanitize_color(data.get("color"))
        pinned = 1 if data.get("pinned") else 0
        archived = 1 if data.get("archived") else 0
        if archived:
            pinned = 0
            
        in_tasks = 1 if (data.get("in_tasks") or (kind == "checklist" and title.lower() == "tasks")) else 0
        reminder_at = None
        reminder_rrule = None
        reminder_tz = None
        if data.get("reminder_at"):
            parsed = parse_utc(data["reminder_at"])
            if parsed:
                reminder_at = parsed.strftime("%Y-%m-%d %H:%M:%S")
                if data.get("reminder_rrule") in REPEATS:
                    reminder_rrule = data["reminder_rrule"]
                    reminder_tz = data.get("reminder_tz")

        now_str = data.get("created_at") or now_utc_str()
        upd_str = data.get("updated_at") or now_str
        client_key = data.get("client_key")

        cur = conn.cursor()
        cur.execute(
            """INSERT INTO notes (user_id, title, body_md, kind, color, pinned, archived, in_tasks,
                                 reminder_at, reminder_rrule, reminder_tz, client_key, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, title, body_md, kind, color, pinned, archived, in_tasks,
             reminder_at, reminder_rrule, reminder_tz, client_key, now_str, upd_str)
        )
        note_id = cur.lastrowid

        # Insert checklist items if provided
        items = data.get("items") or []
        for idx, item in enumerate(items):
            item_uuid = item.get("uuid") or secrets.token_hex(16)
            item_text = str(item.get("text", ""))
            item_checked = 1 if item.get("checked") else 0
            item_pos = float(item.get("position", idx + 1))
            due_date = item.get("due_date")
            due_repeat = clean_task_repeat(item.get("due_repeat")) if due_date else None
            checked_at = now_str if item_checked else None
            
            cur.execute(
                """INSERT INTO checklist_items (uuid, user_id, note_id, text, checked, position, due_date, due_repeat, checked_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (item_uuid, user_id, note_id, item_text, item_checked, item_pos, due_date, due_repeat, checked_at, now_str, upd_str)
            )

        # Labels
        labels = data.get("labels") or []
        for l in labels:
            label_id = None
            if isinstance(l, dict) and "id" in l:
                label_id = l["id"]
            elif isinstance(l, int):
                label_id = l
            elif isinstance(l, str) and l.isdigit():
                label_id = int(l)
                
            if label_id:
                cur.execute(
                    """INSERT OR IGNORE INTO note_labels (user_id, note_id, label_id, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (user_id, note_id, label_id, now_str, upd_str)
                )

        # Attachments
        attachments = data.get("attachments") or []
        for idx, att in enumerate(attachments):
            att_url = str(att.get("url", "")).strip()
            if not att_url.startswith("/uploads/"):
                continue
            att_uuid = att.get("uuid") or secrets.token_hex(16)
            att_mime = att.get("mime")
            att_w = att.get("width")
            att_h = att.get("height")
            att_pos = float(att.get("position", idx + 1))
            cur.execute(
                """INSERT OR IGNORE INTO note_attachments (uuid, user_id, note_id, url, mime, width, height, position, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (att_uuid, user_id, note_id, att_url, att_mime, att_w, att_h, att_pos, now_str, upd_str)
            )

    return get_note(user_id, note_id)

def update_note(user_id: Optional[int], note_id: int, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    access = note_access(user_id, note_id)
    if not access["role"]:
        return None
        
    role = access["role"]
    note = access["note"]
    is_owner = (role == "owner")
    
    with transaction() as conn:
        cur = conn.cursor()
        now_str = now_utc_str()
        
        # If member with 'view' role: can ONLY toggle personal pinned, archived, in_tasks
        if role == "view":
            m_updates = []
            m_params = []
            if "pinned" in patch:
                m_updates.append("pinned = ?")
                m_params.append(1 if patch["pinned"] else 0)
            if "archived" in patch:
                m_updates.append("archived = ?")
                m_params.append(1 if patch["archived"] else 0)
            if "in_tasks" in patch:
                m_updates.append("in_tasks = ?")
                m_params.append(1 if patch["in_tasks"] else 0)
            if m_updates:
                m_updates.append("updated_at = ?")
                m_params.append(now_str)
                m_params.extend([note_id, user_id])
                cur.execute(
                    f"UPDATE note_members SET {', '.join(m_updates)} WHERE note_id = ? AND user_id = ?",
                    m_params
                )
            return hydrate_note(user_id, note)

        # Snapshot version if title/body/kind changes
        title_changed = "title" in patch and patch["title"] != note.get("title")
        body_changed = "body_md" in patch and patch["body_md"] != note.get("body_md")
        kind_changed = "kind" in patch and patch["kind"] != note.get("kind")
        if title_changed or body_changed or kind_changed:
            snapshot_version(note, reason="edit")

        # Personal pin/archive for edit member
        if not is_owner:
            m_updates = []
            m_params = []
            if "pinned" in patch:
                m_updates.append("pinned = ?")
                m_params.append(1 if patch["pinned"] else 0)
            if "archived" in patch:
                m_updates.append("archived = ?")
                m_params.append(1 if patch["archived"] else 0)
            if "in_tasks" in patch:
                m_updates.append("in_tasks = ?")
                m_params.append(1 if patch["in_tasks"] else 0)
            if m_updates:
                m_updates.append("updated_at = ?")
                m_params.append(now_str)
                m_params.extend([note_id, user_id])
                cur.execute(
                    f"UPDATE note_members SET {', '.join(m_updates)} WHERE note_id = ? AND user_id = ?",
                    m_params
                )

        # Prepare updates to main note row
        updates = []
        params = []

        if "title" in patch:
            updates.append("title = ?")
            params.append(str(patch["title"]))
            
        if "body_md" in patch:
            updates.append("body_md = ?")
            params.append(str(patch["body_md"]))
            
        if "kind" in patch and patch["kind"] in NOTE_KINDS:
            updates.append("kind = ?")
            params.append(patch["kind"])
            
        if "color" in patch:
            updates.append("color = ?")
            params.append(sanitize_color(patch["color"]))

        if is_owner:
            if "pinned" in patch:
                updates.append("pinned = ?")
                params.append(1 if patch["pinned"] else 0)
            if "archived" in patch:
                arch_val = 1 if patch["archived"] else 0
                updates.append("archived = ?")
                params.append(arch_val)
                if arch_val == 1:
                    updates.append("pinned = 0")
            if "in_tasks" in patch:
                updates.append("in_tasks = ?")
                params.append(1 if patch["in_tasks"] else 0)
                
            if "reminder_at" in patch:
                r_at = patch["reminder_at"]
                if r_at is None:
                    updates.append("reminder_at = NULL, reminder_rrule = NULL, reminder_tz = NULL")
                else:
                    parsed = parse_utc(r_at)
                    if parsed:
                        updates.append("reminder_at = ?")
                        params.append(parsed.strftime("%Y-%m-%d %H:%M:%S"))
                        rrule = patch.get("reminder_rrule") if "reminder_rrule" in patch else note.get("reminder_rrule")
                        tz = patch.get("reminder_tz") if "reminder_tz" in patch else note.get("reminder_tz")
                        if rrule in REPEATS:
                            updates.append("reminder_rrule = ?, reminder_tz = ?")
                            params.extend([rrule, tz])
                        else:
                            updates.append("reminder_rrule = NULL, reminder_tz = NULL")
            elif "reminder_rrule" in patch:
                if not note.get("reminder_at"):
                    updates.append("reminder_rrule = NULL")
                else:
                    rrule = patch["reminder_rrule"]
                    if rrule in REPEATS:
                        updates.append("reminder_rrule = ?")
                        params.append(rrule)
                        if "reminder_tz" in patch:
                            updates.append("reminder_tz = ?")
                            params.append(patch["reminder_tz"])
                    else:
                        updates.append("reminder_rrule = NULL, reminder_tz = NULL")

        if updates:
            updates.append("updated_at = ?")
            params.append(now_str)
            params.append(note_id)
            cur.execute(f"UPDATE notes SET {', '.join(updates)} WHERE id = ?", params)

        # Labels update
        if "labels" in patch:
            target_uid = user_id if user_id is not None else note.get("user_id")
            cur.execute("UPDATE note_labels SET deleted_at = ? WHERE note_id = ? AND user_id = ?", (now_str, note_id, target_uid))
            new_labels = patch["labels"] or []
            for l in new_labels:
                l_id = l["id"] if isinstance(l, dict) and "id" in l else l
                if l_id:
                    cur.execute(
                        """INSERT INTO note_labels (user_id, note_id, label_id, created_at, updated_at, deleted_at)
                           VALUES (?, ?, ?, ?, ?, NULL)
                           ON CONFLICT(note_id, label_id) DO UPDATE SET deleted_at = NULL, updated_at = ?""",
                        (target_uid, note_id, l_id, now_str, now_str, now_str)
                    )

        # Wikilink propagation
        if title_changed:
            old_title = patch.get("rename_links_from") or note.get("title")
            new_title = patch["title"]
            if patch.get("rename_links", True) is not False:
                rename_links_in_notes(user_id if is_owner else note.get("user_id"), old_title, new_title, note_id)

    return get_note(user_id, note_id)

def trash_note(user_id: Optional[int], note_id: int) -> bool:
    access = note_access(user_id, note_id)
    if access["role"] != "owner":
        return False
    execute(
        "UPDATE notes SET trashed_at = ?, updated_at = ? WHERE id = ?",
        (now_utc_str(), now_utc_str(), note_id)
    )
    return True

def restore_note(user_id: Optional[int], note_id: int) -> bool:
    access = note_access(user_id, note_id)
    if access["role"] != "owner":
        return False
    execute(
        "UPDATE notes SET trashed_at = NULL, updated_at = ? WHERE id = ?",
        (now_utc_str(), note_id)
    )
    return True

def delete_note_forever(user_id: Optional[int], note_id: int) -> bool:
    access = note_access(user_id, note_id)
    if access["role"] != "owner":
        return False
    with transaction() as conn:
        now_str = now_utc_str()
        conn.execute("UPDATE notes SET deleted_at = ?, updated_at = ? WHERE id = ?", (now_str, now_str, note_id))
        conn.execute("UPDATE checklist_items SET deleted_at = ?, updated_at = ? WHERE note_id = ?", (now_str, now_str, note_id))
        conn.execute("UPDATE note_labels SET deleted_at = ?, updated_at = ? WHERE note_id = ?", (now_str, now_str, note_id))
        conn.execute("UPDATE note_attachments SET deleted_at = ?, updated_at = ? WHERE note_id = ?", (now_str, now_str, note_id))
        conn.execute("UPDATE note_members SET deleted_at = ?, updated_at = ? WHERE note_id = ?", (now_str, now_str, note_id))
    return True

def empty_trash(user_id: Optional[int]) -> int:
    target_uid = user_id if user_id is not None else 0
    with transaction() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM notes WHERE user_id = ? AND trashed_at IS NOT NULL AND deleted_at IS NULL", (target_uid,))
        rows = cur.fetchall()
        count = len(rows)
        now_str = now_utc_str()
        for r in rows:
            nid = r["id"]
            conn.execute("UPDATE notes SET deleted_at = ?, updated_at = ? WHERE id = ?", (now_str, now_str, nid))
            conn.execute("UPDATE checklist_items SET deleted_at = ?, updated_at = ? WHERE note_id = ?", (now_str, now_str, nid))
            conn.execute("UPDATE note_labels SET deleted_at = ?, updated_at = ? WHERE note_id = ?", (now_str, now_str, nid))
            conn.execute("UPDATE note_attachments SET deleted_at = ?, updated_at = ? WHERE note_id = ?", (now_str, now_str, nid))
            conn.execute("UPDATE note_members SET deleted_at = ?, updated_at = ? WHERE note_id = ?", (now_str, now_str, nid))
        return count

def purge_expired_trash():
    cutoff = (datetime.now(timezone.utc) - timedelta(days=TRASH_RETENTION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    with transaction() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM notes WHERE trashed_at IS NOT NULL AND trashed_at < ?", (cutoff,))
        rows = cur.fetchall()
        for r in rows:
            conn.execute("DELETE FROM notes WHERE id = ?", (r["id"],))

def convert_note(user_id: Optional[int], note_id: int, target_kind: str) -> Optional[Dict[str, Any]]:
    access = note_access(user_id, note_id)
    if access["role"] not in ("owner", "edit"):
        return None
    note = access["note"]
    current_kind = note["kind"]
    if current_kind == target_kind:
        return get_note(user_id, note_id)
        
    with transaction() as conn:
        now_str = now_utc_str()
        if target_kind == "text":
            # Checklist to text
            items = query_all(
                "SELECT text, checked FROM checklist_items WHERE note_id = ? AND deleted_at IS NULL ORDER BY position ASC, id ASC",
                (note_id,)
            )
            lines = []
            for it in items:
                mark = "x" if it["checked"] else " "
                lines.append(f"- [{mark}] {it['text']}")
            new_body = "\n".join(lines)
            conn.execute(
                "UPDATE notes SET kind = 'text', body_md = ?, updated_at = ? WHERE id = ?",
                (new_body, now_str, note_id)
            )
            conn.execute(
                "UPDATE checklist_items SET deleted_at = ?, updated_at = ? WHERE note_id = ?",
                (now_str, now_str, note_id)
            )
        else:
            # Text to checklist
            body = note.get("body_md", "")
            lines = body.split("\n")
            conn.execute(
                "UPDATE notes SET kind = 'checklist', body_md = '', updated_at = ? WHERE id = ?",
                (now_str, note_id)
            )
            pos = 1.0
            for line in lines:
                l_str = line.strip()
                if not l_str:
                    continue
                m = re.match(r'^[-\*]\s+\[([ xX])\]\s*(.*)$', l_str)
                if m:
                    chk = (m.group(1).lower() == "x")
                    txt = m.group(2)
                else:
                    chk = False
                    txt = l_str.lstrip("-* ").strip()
                item_uuid = secrets.token_hex(16)
                conn.execute(
                    """INSERT INTO checklist_items (uuid, user_id, note_id, text, checked, position, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (item_uuid, note.get("user_id"), note_id, txt, 1 if chk else 0, pos, now_str, now_str)
                )
                pos += 1.0

    return get_note(user_id, note_id)

def add_item(user_id: Optional[int], note_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    access = note_access(user_id, note_id)
    if access["role"] not in ("owner", "edit"):
        return None
    note = access["note"]
    with transaction() as conn:
        now_str = now_utc_str()
        item_uuid = data.get("uuid") or secrets.token_hex(16)
        item_text = str(data.get("text", ""))
        item_checked = 1 if data.get("checked") else 0
        
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(position), 0) as max_pos FROM checklist_items WHERE note_id = ?", (note_id,))
        max_p = cur.fetchone()["max_pos"]
        item_pos = float(data.get("position", max_p + 1.0))
        
        due_date = data.get("due_date")
        due_repeat = clean_task_repeat(data.get("due_repeat")) if due_date else None
        checked_at = now_str if item_checked else None
        
        # Note owner owns checklist items
        item_user_id = note.get("user_id")
        cur.execute(
            """INSERT INTO checklist_items (uuid, user_id, note_id, text, checked, position, due_date, due_repeat, checked_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item_uuid, item_user_id, note_id, item_text, item_checked, item_pos, due_date, due_repeat, checked_at, now_str, now_str)
        )
        conn.execute("UPDATE notes SET updated_at = ? WHERE id = ?", (now_str, note_id))

    return get_note(user_id, note_id)

def update_item(user_id: Optional[int], note_id: int, uuid: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    access = note_access(user_id, note_id)
    if access["role"] not in ("owner", "edit"):
        return None
        
    item = query_one("SELECT * FROM checklist_items WHERE note_id = ? AND uuid = ? AND deleted_at IS NULL", (note_id, uuid))
    if not item:
        return None
        
    with transaction() as conn:
        now_str = now_utc_str()
        today = patch.get("today") or now_str[:10]
        
        next_text = str(patch.get("text", item["text"]))
        next_pos = float(patch.get("position", item["position"]))
        
        due_date = patch.get("due_date", item.get("due_date")) if "due_date" in patch else item.get("due_date")
        due_repeat = patch.get("due_repeat", item.get("due_repeat")) if "due_repeat" in patch else item.get("due_repeat")
        if not due_date:
            due_repeat = None
        else:
            due_repeat = clean_task_repeat(due_repeat)
            
        was_checked = bool(item.get("checked"))
        is_now_checked = bool(patch.get("checked")) if "checked" in patch else was_checked
        checked_at = item.get("checked_at")
        
        if "checked" in patch:
            if is_now_checked and not was_checked:
                # Ticking repeating task moves date forward and leaves unchecked!
                if due_repeat:
                    moved = next_due_date(due_date, due_repeat, today)
                    if moved:
                        due_date = moved
                        is_now_checked = False
                        checked_at = None
                else:
                    checked_at = now_str
            elif not is_now_checked and was_checked:
                checked_at = None

        conn.execute(
            """UPDATE checklist_items
               SET text = ?, checked = ?, position = ?, due_date = ?, due_repeat = ?, checked_at = ?, updated_at = ?
               WHERE note_id = ? AND uuid = ?""",
            (next_text, 1 if is_now_checked else 0, next_pos, due_date, due_repeat, checked_at, now_str, note_id, uuid)
        )
        conn.execute("UPDATE notes SET updated_at = ? WHERE id = ?", (now_str, note_id))

    return get_note(user_id, note_id)

def delete_item(user_id: Optional[int], note_id: int, uuid: str) -> Optional[Dict[str, Any]]:
    access = note_access(user_id, note_id)
    if access["role"] not in ("owner", "edit"):
        return None
    with transaction() as conn:
        now_str = now_utc_str()
        conn.execute(
            "UPDATE checklist_items SET deleted_at = ?, updated_at = ? WHERE note_id = ? AND uuid = ?",
            (now_str, now_str, note_id, uuid)
        )
        conn.execute("UPDATE notes SET updated_at = ? WHERE id = ?", (now_str, note_id))
    return get_note(user_id, note_id)

def reorder_items(user_id: Optional[int], note_id: int, uuids: List[str]) -> Optional[Dict[str, Any]]:
    access = note_access(user_id, note_id)
    if access["role"] not in ("owner", "edit"):
        return None
    with transaction() as conn:
        now_str = now_utc_str()
        for pos, u in enumerate(uuids):
            conn.execute(
                "UPDATE checklist_items SET position = ?, updated_at = ? WHERE note_id = ? AND uuid = ?",
                (float(pos + 1), now_str, note_id, u)
            )
        conn.execute("UPDATE notes SET updated_at = ? WHERE id = ?", (now_str, note_id))
    return get_note(user_id, note_id)

def list_labels(user_id: Optional[int]) -> List[Dict[str, Any]]:
    target_uid = user_id if user_id is not None else 0
    sql = """
        SELECT l.*,
               (SELECT COUNT(DISTINCT nl.note_id)
                FROM note_labels nl
                JOIN notes n ON n.id = nl.note_id
                WHERE nl.label_id = l.id AND nl.deleted_at IS NULL AND n.deleted_at IS NULL AND n.trashed_at IS NULL
               ) AS note_count
        FROM labels l
        WHERE (l.user_id = ? OR ? = 0) AND l.deleted_at IS NULL
        ORDER BY l.position ASC, l.id ASC
    """
    return query_all(sql, (target_uid, target_uid))

def create_label(user_id: Optional[int], data: Dict[str, Any]) -> Dict[str, Any]:
    name = str(data.get("name", "")).strip()
    if not name:
        return {"error": "Name is required"}
    target_uid = user_id if user_id is not None else 0
    dup = query_one(
        "SELECT id FROM labels WHERE user_id = ? AND lower(name) = lower(?) AND deleted_at IS NULL",
        (target_uid, name)
    )
    if dup:
        return {"error": "Label already exists"}
        
    color = sanitize_color(data.get("color"))
    icon = data.get("icon")
    pos = int(data.get("position", 0))
    now_str = now_utc_str()
    lid = execute(
        """INSERT INTO labels (user_id, name, color, icon, position, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, name, color, icon, pos, now_str, now_str)
    )
    res = query_one("SELECT * FROM labels WHERE id = ?", (lid,))
    res["note_count"] = 0
    return res

def update_label(user_id: Optional[int], label_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    target_uid = user_id if user_id is not None else 0
    label = query_one("SELECT * FROM labels WHERE id = ? AND (user_id = ? OR ? = 0) AND deleted_at IS NULL", (label_id, target_uid, target_uid))
    if not label:
        return None
        
    updates = []
    params = []
    if "name" in data:
        name = str(data["name"]).strip()
        if not name:
            return {"error": "Name cannot be empty"}
        dup = query_one(
            "SELECT id FROM labels WHERE user_id = ? AND lower(name) = lower(?) AND id != ? AND deleted_at IS NULL",
            (target_uid, name, label_id)
        )
        if dup:
            return {"error": "Label already exists"}
        updates.append("name = ?")
        params.append(name)
        
    if "color" in data:
        updates.append("color = ?")
        params.append(sanitize_color(data["color"]))
        
    if "icon" in data:
        updates.append("icon = ?")
        params.append(data["icon"])
        
    if updates:
        updates.append("updated_at = ?")
        params.append(now_utc_str())
        params.append(label_id)
        execute(f"UPDATE labels SET {', '.join(updates)} WHERE id = ?", params)
        
    return query_one("SELECT * FROM labels WHERE id = ?", (label_id,))

def delete_label(user_id: Optional[int], label_id: int) -> bool:
    target_uid = user_id if user_id is not None else 0
    label = query_one("SELECT * FROM labels WHERE id = ? AND (user_id = ? OR ? = 0) AND deleted_at IS NULL", (label_id, target_uid, target_uid))
    if not label:
        return False
    now_str = now_utc_str()
    with transaction() as conn:
        conn.execute("UPDATE labels SET deleted_at = ?, updated_at = ? WHERE id = ?", (now_str, now_str, label_id))
        conn.execute("UPDATE note_labels SET deleted_at = ?, updated_at = ? WHERE label_id = ?", (now_str, now_str, label_id))
    return True

def reorder_labels(user_id: Optional[int], ids: List[int]) -> List[Dict[str, Any]]:
    target_uid = user_id if user_id is not None else 0
    with transaction() as conn:
        now_str = now_utc_str()
        for pos, lid in enumerate(ids):
            conn.execute(
                "UPDATE labels SET position = ?, updated_at = ? WHERE id = ? AND (user_id = ? OR ? = 0)",
                (pos + 1, now_str, lid, target_uid, target_uid)
            )
    return list_labels(user_id)

def add_attachments(user_id: Optional[int], note_id: int, attachments: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    access = note_access(user_id, note_id)
    if access["role"] not in ("owner", "edit"):
        return None
    note = access["note"]
    with transaction() as conn:
        now_str = now_utc_str()
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(position), 0) as max_pos FROM note_attachments WHERE note_id = ?", (note_id,))
        max_p = cur.fetchone()["max_pos"]
        
        for idx, att in enumerate(attachments):
            att_url = str(att.get("url", "")).strip()
            # Security guard: must be valid local upload path
            if not att_url.startswith("/uploads/") or ".." in att_url:
                continue
            att_uuid = att.get("uuid") or secrets.token_hex(16)
            mime = att.get("mime")
            w = att.get("width")
            h = att.get("height")
            pos = float(att.get("position", max_p + idx + 1.0))
            name = att.get("name")
            size_bytes = att.get("size_bytes")
            preview_url = att.get("preview_url")
            if preview_url and not preview_url.startswith("/uploads/"):
                preview_url = None
            extracted_text = att.get("extracted_text")
            
            cur.execute(
                """INSERT INTO note_attachments (uuid, user_id, note_id, url, mime, width, height, position, name, size_bytes, preview_url, extracted_text, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (att_uuid, note["user_id"], note_id, att_url, mime, w, h, pos, name, size_bytes, preview_url, extracted_text, now_str, now_str)
            )
        conn.execute("UPDATE notes SET updated_at = ? WHERE id = ?", (now_str, note_id))

    return get_note(user_id, note_id)

def get_attachment_drawing(user_id: Optional[int], note_id: int, uuid: str) -> Optional[Dict[str, Any]]:
    access = note_access(user_id, note_id)
    if not access["role"]:
        return None
    row = query_one(
        "SELECT drawing FROM note_attachments WHERE note_id = ? AND uuid = ? AND deleted_at IS NULL",
        (note_id, uuid)
    )
    if not row or not row.get("drawing"):
        return None
    try:
        return json.loads(row["drawing"])
    except Exception:
        return {"strokes": []}

def update_attachment(user_id: Optional[int], note_id: int, uuid: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    access = note_access(user_id, note_id)
    if access["role"] not in ("owner", "edit"):
        return None
    row = query_one("SELECT * FROM note_attachments WHERE note_id = ? AND uuid = ? AND deleted_at IS NULL", (note_id, uuid))
    if not row:
        return None
        
    updates = []
    params = []
    if "preview_url" in patch:
        p_url = patch["preview_url"]
        if p_url and (not str(p_url).startswith("/uploads/") or ".." in str(p_url)):
            p_url = None
        updates.append("preview_url = ?")
        params.append(p_url)
        
    if "extracted_text" in patch:
        updates.append("extracted_text = ?")
        params.append(patch["extracted_text"])
        
    if "drawing" in patch:
        updates.append("drawing = ?")
        params.append(json.dumps(patch["drawing"]) if patch["drawing"] else None)
        
    if updates:
        updates.append("updated_at = ?")
        now_str = now_utc_str()
        params.append(now_str)
        params.extend([note_id, uuid])
        with transaction() as conn:
            conn.execute(f"UPDATE note_attachments SET {', '.join(updates)} WHERE note_id = ? AND uuid = ?", params)
            conn.execute("UPDATE notes SET updated_at = ? WHERE id = ?", (now_str, note_id))

    return get_note(user_id, note_id)

def delete_attachment(user_id: Optional[int], note_id: int, uuid: str) -> Optional[Dict[str, Any]]:
    access = note_access(user_id, note_id)
    if access["role"] not in ("owner", "edit"):
        return None
    with transaction() as conn:
        now_str = now_utc_str()
        conn.execute(
            "UPDATE note_attachments SET deleted_at = ?, updated_at = ? WHERE note_id = ? AND uuid = ?",
            (now_str, now_str, note_id, uuid)
        )
        conn.execute("UPDATE notes SET updated_at = ? WHERE id = ?", (now_str, note_id))
    return get_note(user_id, note_id)

def list_members(user_id: Optional[int], note_id: int) -> List[Dict[str, Any]]:
    access = note_access(user_id, note_id)
    if access["role"] != "owner":
        return []
    sql = """
        SELECT nm.user_id, nm.role, nm.created_at, u.username, u.full_name, u.avatar_url
        FROM note_members nm
        JOIN users u ON u.id = nm.user_id
        WHERE nm.note_id = ? AND nm.deleted_at IS NULL
    """
    return query_all(sql, (note_id,))

def add_member(user_id: Optional[int], note_id: int, username: str, role: str = "edit") -> Tuple[bool, Optional[str]]:
    access = note_access(user_id, note_id)
    if access["role"] != "owner":
        return False, "Only owner can share note"
        
    target_u = query_one("SELECT id, username FROM users WHERE lower(username) = lower(?)", (username.strip(),))
    if not target_u:
        return False, "User not found"
        
    if target_u["id"] == access["note"]["user_id"]:
        return False, "Cannot share with yourself"
        
    m_role = role if role in MEMBER_ROLES else "edit"
    now_str = now_utc_str()
    execute(
        """INSERT INTO note_members (note_id, user_id, role, added_by, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(note_id, user_id) DO UPDATE SET role = ?, deleted_at = NULL, updated_at = ?""",
        (note_id, target_u["id"], m_role, user_id, now_str, now_str, m_role, now_str)
    )
    execute("UPDATE notes SET updated_at = ? WHERE id = ?", (now_str, note_id))
    return True, None

def update_member(user_id: Optional[int], note_id: int, member_user_id: int, role: str) -> bool:
    access = note_access(user_id, note_id)
    if access["role"] != "owner":
        return False
    m_role = role if role in MEMBER_ROLES else "edit"
    now_str = now_utc_str()
    execute(
        "UPDATE note_members SET role = ?, updated_at = ? WHERE note_id = ? AND user_id = ? AND deleted_at IS NULL",
        (m_role, now_str, note_id, member_user_id)
    )
    execute("UPDATE notes SET updated_at = ? WHERE id = ?", (now_str, note_id))
    return True

def remove_member(user_id: Optional[int], note_id: int, member_user_id: int) -> bool:
    access = note_access(user_id, note_id)
    # Allowed if user is the note owner, or if member is removing themselves (leaving)
    if access["role"] != "owner" and user_id != member_user_id:
        return False
    now_str = now_utc_str()
    execute(
        "UPDATE note_members SET deleted_at = ?, updated_at = ? WHERE note_id = ? AND user_id = ?",
        (now_str, now_str, note_id, member_user_id)
    )
    execute("UPDATE notes SET updated_at = ? WHERE id = ?", (now_str, note_id))
    return True

def get_public_link(user_id: Optional[int], note_id: int) -> Optional[str]:
    access = note_access(user_id, note_id)
    if access["role"] != "owner":
        return None
    return access["note"].get("share_token")

def create_public_link(user_id: Optional[int], note_id: int) -> Optional[str]:
    access = note_access(user_id, note_id)
    if access["role"] != "owner":
        return None
    if access["note"].get("trashed_at"):
        return None
    token = access["note"].get("share_token")
    if not token:
        token = secrets.token_urlsafe(16)
        execute("UPDATE notes SET share_token = ?, updated_at = ? WHERE id = ?", (token, now_utc_str(), note_id))
    return token

def revoke_public_link(user_id: Optional[int], note_id: int) -> bool:
    access = note_access(user_id, note_id)
    if access["role"] != "owner":
        return False
    execute("UPDATE notes SET share_token = NULL, updated_at = ? WHERE id = ?", (now_utc_str(), note_id))
    return True

def get_public_note(token: str) -> Optional[Dict[str, Any]]:
    if not token or len(token) < 10:
        return None
    note = query_one(
        "SELECT * FROM notes WHERE share_token = ? AND trashed_at IS NULL AND deleted_at IS NULL",
        (token,)
    )
    if not note:
        return None
    # Public view carries only public fields: title, body_md, kind, items
    note_id = note["id"]
    items = query_all(
        "SELECT checked, text FROM checklist_items WHERE note_id = ? AND deleted_at IS NULL ORDER BY position ASC, id ASC",
        (note_id,)
    )
    for it in items:
        it["checked"] = bool(it["checked"])
        
    return {
        "title": note.get("title", ""),
        "body_md": note.get("body_md", ""),
        "kind": note.get("kind", "text"),
        "color": note.get("color"),
        "items": items,
        "created_at": note.get("created_at"),
        "updated_at": note.get("updated_at"),
    }

def tasks_due_count(user_id: Optional[int], today: Optional[str] = None) -> Dict[str, Any]:
    now_dt = datetime.now(timezone.utc)
    t_str = today if (today and re.match(r'^\d{4}-\d{2}-\d{2}$', today)) else now_dt.strftime("%Y-%m-%d")
    target_uid = user_id if user_id is not None else 0
    
    # Overdue and today tasks, only from un-archived, un-trashed, undeleted notes
    sql = """
        SELECT COUNT(*) as c
        FROM checklist_items ci
        JOIN notes n ON n.id = ci.note_id
        WHERE (n.user_id = ? OR ? = 0)
          AND n.archived = 0
          AND n.trashed_at IS NULL
          AND n.deleted_at IS NULL
          AND ci.deleted_at IS NULL
          AND ci.checked = 0
          AND ci.due_date IS NOT NULL
          AND ci.due_date <= ?
    """
    row = query_one(sql, (target_uid, target_uid, t_str))
    return {"tasksDue": row["c"] if row else 0, "today": t_str}

def list_note_titles(user_id: Optional[int]) -> List[Dict[str, Any]]:
    target_uid = user_id if user_id is not None else 0
    sql = """
        SELECT id, title
        FROM notes
        WHERE (user_id = ? OR ? = 0) AND deleted_at IS NULL AND trashed_at IS NULL
        ORDER BY updated_at DESC
    """
    return query_all(sql, (target_uid, target_uid))

def find_note_by_title(user_id: Optional[int], title: str) -> Optional[Dict[str, Any]]:
    target_uid = user_id if user_id is not None else 0
    sql = """
        SELECT id, title
        FROM notes
        WHERE (user_id = ? OR ? = 0) AND lower(title) = lower(?) AND deleted_at IS NULL AND trashed_at IS NULL
        LIMIT 1
    """
    return query_one(sql, (target_uid, target_uid, title.strip()))

def list_backlinks(user_id: Optional[int], note_id: int) -> List[Dict[str, Any]]:
    note = query_one("SELECT title FROM notes WHERE id = ?", (note_id,))
    if not note or not note.get("title"):
        return []
    title = note["title"]
    target_uid = user_id if user_id is not None else 0
    pattern = f"%[[{title}]]%"
    sql = """
        SELECT id, title
        FROM notes
        WHERE (user_id = ? OR ? = 0) AND id != ? AND body_md LIKE ? AND deleted_at IS NULL AND trashed_at IS NULL
        ORDER BY updated_at DESC
    """
    return query_all(sql, (target_uid, target_uid, note_id, pattern))

def list_versions(user_id: Optional[int], note_id: int) -> List[Dict[str, Any]]:
    access = note_access(user_id, note_id)
    if not access["role"]:
        return []
    return query_all(
        "SELECT * FROM note_versions WHERE note_id = ? ORDER BY id DESC",
        (note_id,)
    )

def restore_version(user_id: Optional[int], note_id: int, version_id: int) -> Optional[Dict[str, Any]]:
    access = note_access(user_id, note_id)
    if access["role"] not in ("owner", "edit"):
        return None
    v = query_one("SELECT * FROM note_versions WHERE id = ? AND note_id = ?", (version_id, note_id))
    if not v:
        return None
        
    with transaction() as conn:
        now_str = now_utc_str()
        # Snapshot current before restoring
        snapshot_version(access["note"], reason="restore")
        
        conn.execute(
            "UPDATE notes SET title = ?, body_md = ?, kind = ?, updated_at = ? WHERE id = ?",
            (v["title"], v["body_md"], v["kind"], now_str, note_id)
        )
        if v.get("items_json"):
            items = json.loads(v["items_json"])
            conn.execute("UPDATE checklist_items SET deleted_at = ?, updated_at = ? WHERE note_id = ?", (now_str, now_str, note_id))
            for it in items:
                u = it.get("uuid") or secrets.token_hex(16)
                conn.execute(
                    """INSERT INTO checklist_items (uuid, user_id, note_id, text, checked, position, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(uuid) DO UPDATE SET text = excluded.text, checked = excluded.checked, position = excluded.position, deleted_at = NULL, updated_at = excluded.updated_at""",
                    (u, access["note"]["user_id"], note_id, it.get("text", ""), 1 if it.get("checked") else 0, float(it.get("position", 1)), now_str, now_str)
                )

    return get_note(user_id, note_id)
def import_notes(user_id: Optional[int], notes_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(notes_list, list):
        return {"error": "Invalid notes list"}
        
    result = {"imported": 0, "skipped": 0, "labels_created": 0, "ids": []}
    target_uid = user_id if user_id is not None else 0
    label_map = {l["name"].lower(): l["id"] for l in list_labels(user_id)}
    now_str = now_utc_str()

    with transaction() as conn:
        cur = conn.cursor()
        for raw in notes_list[:IMPORT_BATCH_MAX]:
            result["ids"].append(None)
            if not raw or not isinstance(raw, dict):
                result["skipped"] += 1
                continue
                
            kind = raw.get("kind") if raw.get("kind") in NOTE_KINDS else "text"
            title = str(raw.get("title", "")).strip()
            body = str(raw.get("body_md", "")) if kind == "text" else ""
            
            raw_items = raw.get("items") or []
            items = [i for i in raw_items if i and str(i.get("text", "")).strip()][:2000] if kind == "checklist" else []
            has_files = bool(raw.get("files") and len(raw["files"]) > 0)
            
            if not title and not body.strip() and not items and not has_files:
                result["skipped"] += 1
                continue
                
            created = raw.get("created_at") or now_str
            updated = raw.get("updated_at") or created
            
            image_only = (not title and not body.strip() and not items)
            if not (image_only and not raw.get("created_at")):
                # Check duplicate
                cur.execute(
                    """SELECT 1 FROM notes
                       WHERE (user_id = ? OR ? = 0) AND deleted_at IS NULL
                         AND title = ? AND kind = ? AND body_md = ? AND created_at = ?
                       LIMIT 1""",
                    (target_uid, target_uid, title, kind, body, created)
                )
                if cur.fetchone():
                    result["skipped"] += 1
                    continue
                    
            color = sanitize_color(raw.get("color"))
            pinned = 1 if (raw.get("pinned") and not raw.get("archived") and not raw.get("trashed")) else 0
            archived = 1 if raw.get("archived") else 0
            in_tasks = 1 if (kind == "checklist" and (raw.get("in_tasks") or title.lower() == "tasks")) else 0
            trashed_at = now_str if raw.get("trashed") else None
            
            reminder_at = None
            reminder_rrule = None
            reminder_tz = None
            if raw.get("reminder_at"):
                parsed = parse_utc(raw["reminder_at"])
                if parsed:
                    reminder_at = parsed.strftime("%Y-%m-%d %H:%M:%S")
                    if raw.get("reminder_rrule") in REPEATS:
                        reminder_rrule = raw["reminder_rrule"]
                        reminder_tz = raw.get("reminder_tz")

            cur.execute(
                """INSERT INTO notes (user_id, title, body_md, kind, color, pinned, archived, in_tasks,
                                     trashed_at, reminder_at, reminder_rrule, reminder_tz, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, title, body, kind, color, pinned, archived, in_tasks,
                 trashed_at, reminder_at, reminder_rrule, reminder_tz, created, updated)
            )
            note_id = cur.lastrowid
            
            # Insert checklist items
            for idx, it in enumerate(items):
                item_uuid = it.get("uuid") or secrets.token_hex(16)
                cur.execute(
                    """INSERT INTO checklist_items (uuid, user_id, note_id, text, checked, position, due_date, due_repeat, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (item_uuid, user_id, note_id, it.get("text", ""), 1 if it.get("checked") else 0, float(it.get("position", idx + 1)),
                     it.get("due_date"), clean_task_repeat(it.get("due_repeat")), created, updated)
                )
                
            # Labels
            labels_raw = raw.get("labels") or []
            label_ids = []
            for lname in labels_raw:
                clean_name = str(lname or "").strip()[:60]
                if not clean_name:
                    continue
                k = clean_name.lower()
                if k not in label_map:
                    # Create label
                    cur.execute(
                        "INSERT INTO labels (user_id, name, position, created_at, updated_at) VALUES (?, ?, 0, ?, ?)",
                        (user_id, clean_name, now_str, now_str)
                    )
                    new_lid = cur.lastrowid
                    label_map[k] = new_lid
                    result["labels_created"] += 1
                label_ids.append(label_map[k])
                
            for lid in label_ids:
                cur.execute(
                    "INSERT OR IGNORE INTO note_labels (user_id, note_id, label_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (user_id, note_id, lid, created, updated)
                )
                
            result["ids"][-1] = note_id
            result["imported"] += 1

    return result
