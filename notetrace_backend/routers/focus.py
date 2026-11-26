from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from ..auth import require_auth
from ..database import execute, query_all, query_one
from ..events import notify_update

router = APIRouter(prefix="/api/focus", tags=["focus"])

def get_uid(user: Dict[str, Any]) -> int:
    return user.get("id") or 0

def parse_iso(ts_str: str) -> datetime:
    s = ts_str.replace("Z", "+00:00")
    if "+" not in s and "-" not in s[10:]:
        s += "+00:00"
    return datetime.fromisoformat(s)

class StartFocusRequest(BaseModel):
    session_type: str = "focus"  # 'focus', 'short_break', 'long_break'
    duration_min: int = 25
    note_id: Optional[int] = None
    item_uuid: Optional[str] = None
    notes: Optional[str] = None

class AssignFocusTaskRequest(BaseModel):
    session_id: Optional[int] = None
    note_id: Optional[int] = None
    item_uuid: Optional[str] = None
    notes: Optional[str] = None

class CompleteFocusRequest(BaseModel):
    session_id: Optional[int] = None
    actual_sec: Optional[int] = None
    notes: Optional[str] = None

class StopFocusRequest(BaseModel):
    actual_sec: Optional[int] = None
    save_time: bool = True

@router.get("/active")
def get_active_focus_session(user: Dict[str, Any] = Depends(require_auth)):
    uid = get_uid(user)
    row = query_one(
        """SELECT fs.*, n.title as note_title, n.color as note_color, ci.text as item_text, ci.checked as item_checked
           FROM focus_sessions fs
           LEFT JOIN notes n ON n.id = fs.note_id AND n.deleted_at IS NULL
           LEFT JOIN checklist_items ci ON ci.uuid = fs.item_uuid AND ci.deleted_at IS NULL
           WHERE fs.user_id = ? AND fs.status IN ('active', 'paused')
           ORDER BY fs.id DESC LIMIT 1""",
        (uid,)
    )
    if not row:
        return {"active": False, "session": None}

    now = datetime.now(timezone.utc)
    if row["status"] == "active" and row.get("target_end_at"):
        try:
            target = parse_iso(row["target_end_at"])
            rem = int((target - now).total_seconds())
            row["remaining_sec"] = max(0, rem)
        except Exception:
            pass

    return {"active": True, "session": row}

@router.post("/start")
def start_focus_session(req: StartFocusRequest, user: Dict[str, Any] = Depends(require_auth)):
    uid = get_uid(user)
    now = datetime.now(timezone.utc)

    # Automatically save elapsed time on any lingering active/paused sessions so time is never lost
    lingering = query_all(
        "SELECT * FROM focus_sessions WHERE user_id = ? AND status IN ('active', 'paused')",
        (uid,)
    )
    for old in lingering:
        total_sec = (old.get("duration_min") or 25) * 60
        rem = old.get("remaining_sec")
        if old.get("status") == "active" and old.get("target_end_at"):
            try:
                target = parse_iso(old["target_end_at"])
                rem = max(0, int((target - now).total_seconds()))
            except Exception:
                rem = 0
        elif rem is None:
            rem = 0
        elapsed = max(0, total_sec - rem)
        if elapsed >= 1:
            execute(
                """UPDATE focus_sessions
                   SET status = 'completed', actual_sec = ?, remaining_sec = 0, completed_at = ?
                   WHERE id = ?""",
                (elapsed, now.isoformat(), old["id"])
            )
        else:
            execute("UPDATE focus_sessions SET status = 'cancelled' WHERE id = ?", (old["id"],))

    dur = max(1, min(180, req.duration_min))
    target_end = now + timedelta(minutes=dur)
    started_iso = now.isoformat()
    target_iso = target_end.isoformat()

    execute(
        """INSERT INTO focus_sessions
           (user_id, note_id, item_uuid, session_type, duration_min, actual_sec, status, started_at, target_end_at, remaining_sec, notes)
           VALUES (?, ?, ?, ?, ?, 0, 'active', ?, ?, ?, ?)""",
        (uid, req.note_id, req.item_uuid, req.session_type, dur, started_iso, target_iso, dur * 60, req.notes)
    )

    new_session = query_one(
        """SELECT fs.*, n.title as note_title, n.color as note_color, ci.text as item_text, ci.checked as item_checked
           FROM focus_sessions fs
           LEFT JOIN notes n ON n.id = fs.note_id
           LEFT JOIN checklist_items ci ON ci.uuid = fs.item_uuid
           WHERE fs.user_id = ? AND fs.status = 'active'
           ORDER BY fs.id DESC LIMIT 1""",
        (uid,)
    )

    notify_update("focus_updated", {
        "action": "started",
        "session_type": req.session_type,
        "note_id": req.note_id,
        "session": new_session
    })

    return {"active": True, "session": new_session}

@router.post("/pause")
def pause_focus_session(user: Dict[str, Any] = Depends(require_auth)):
    uid = get_uid(user)
    row = query_one(
        "SELECT * FROM focus_sessions WHERE user_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
        (uid,)
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active focus session to pause")

    now = datetime.now(timezone.utc)
    remaining_sec = row.get("remaining_sec") or (row["duration_min"] * 60)
    if row.get("target_end_at"):
        try:
            target = parse_iso(row["target_end_at"])
            remaining_sec = max(0, int((target - now).total_seconds()))
        except Exception:
            pass

    execute(
        "UPDATE focus_sessions SET status = 'paused', remaining_sec = ? WHERE id = ?",
        (remaining_sec, row["id"])
    )

    notify_update("focus_updated", {
        "action": "paused",
        "session_id": row["id"],
        "remaining_sec": remaining_sec
    })

    return {"ok": True, "remaining_sec": remaining_sec}

@router.post("/resume")
def resume_focus_session(user: Dict[str, Any] = Depends(require_auth)):
    uid = get_uid(user)
    row = query_one(
        "SELECT * FROM focus_sessions WHERE user_id = ? AND status = 'paused' ORDER BY id DESC LIMIT 1",
        (uid,)
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No paused focus session to resume")

    now = datetime.now(timezone.utc)
    rem_sec = row.get("remaining_sec") or (row["duration_min"] * 60)
    target_end = now + timedelta(seconds=rem_sec)
    target_iso = target_end.isoformat()

    execute(
        "UPDATE focus_sessions SET status = 'active', target_end_at = ? WHERE id = ?",
        (target_iso, row["id"])
    )

    notify_update("focus_updated", {
        "action": "resumed",
        "session_id": row["id"],
        "target_end_at": target_iso,
        "remaining_sec": rem_sec
    })

    return {"ok": True, "target_end_at": target_iso, "remaining_sec": rem_sec}

@router.post("/stop")
def stop_focus_session(req: Optional[StopFocusRequest] = None, user: Dict[str, Any] = Depends(require_auth)):
    uid = get_uid(user)
    now = datetime.now(timezone.utc)
    save_time = req.save_time if req else True
    explicit_sec = req.actual_sec if req else None

    row = query_one(
        "SELECT * FROM focus_sessions WHERE user_id = ? AND status IN ('active', 'paused') ORDER BY id DESC LIMIT 1",
        (uid,)
    )
    if not row:
        return {"ok": True, "actual_sec": 0}

    actual_sec = 0
    if save_time:
        if explicit_sec is not None:
            actual_sec = max(0, explicit_sec)
        else:
            total_sec = (row.get("duration_min") or 25) * 60
            rem = row.get("remaining_sec")
            if row["status"] == "active" and row.get("target_end_at"):
                try:
                    target = parse_iso(row["target_end_at"])
                    rem = max(0, int((target - now).total_seconds()))
                except Exception:
                    rem = 0
            elif rem is None:
                rem = 0
            actual_sec = max(0, total_sec - rem)

    if save_time and actual_sec >= 1:
        execute(
            """UPDATE focus_sessions
               SET status = 'completed', completed_at = ?, actual_sec = ?, remaining_sec = 0
               WHERE id = ?""",
            (now.isoformat(), actual_sec, row["id"])
        )
    else:
        execute(
            "UPDATE focus_sessions SET status = 'cancelled', remaining_sec = 0 WHERE id = ?",
            (row["id"],)
        )

    notify_update("focus_updated", {
        "action": "stopped",
        "session_id": row["id"],
        "saved_as_completed": (save_time and actual_sec >= 1),
        "actual_sec": actual_sec
    })
    notify_update("analytics_updated", {})
    return {"ok": True, "saved_as_completed": (save_time and actual_sec >= 1), "actual_sec": actual_sec, "session_id": row["id"]}

@router.post("/assign")
def assign_focus_task(req: AssignFocusTaskRequest, user: Dict[str, Any] = Depends(require_auth)):
    uid = get_uid(user)

    target_session = None
    if req.session_id:
        target_session = query_one(
            "SELECT * FROM focus_sessions WHERE id = ? AND user_id = ?",
            (req.session_id, uid)
        )
        if not target_session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Focus session {req.session_id} not found")
    else:
        # 1. Try active or paused session
        target_session = query_one(
            "SELECT * FROM focus_sessions WHERE user_id = ? AND status IN ('active', 'paused') ORDER BY id DESC LIMIT 1",
            (uid,)
        )
        # 2. Fall back to most recent completed session (allows assigning right after completing)
        if not target_session:
            target_session = query_one(
                "SELECT * FROM focus_sessions WHERE user_id = ? AND status = 'completed' ORDER BY id DESC LIMIT 1",
                (uid,)
            )

    if not target_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No focus session found to assign")

    execute(
        "UPDATE focus_sessions SET note_id = ?, item_uuid = ?, notes = ? WHERE id = ?",
        (req.note_id, req.item_uuid, req.notes, target_session["id"])
    )

    updated = query_one(
        """SELECT fs.*, n.title as note_title, n.color as note_color, ci.text as item_text, ci.checked as item_checked
           FROM focus_sessions fs
           LEFT JOIN notes n ON n.id = fs.note_id
           LEFT JOIN checklist_items ci ON ci.uuid = fs.item_uuid
           WHERE fs.id = ?""",
        (target_session["id"],)
    )

    notify_update("focus_updated", {
        "action": "assigned",
        "session_id": target_session["id"],
        "note_id": req.note_id,
        "item_uuid": req.item_uuid,
        "notes": req.notes,
        "session": updated
    })
    notify_update("analytics_updated", {})
    return {"ok": True, "session": updated}

@router.post("/sessions/{session_id}/assign")
def assign_specific_focus_session(session_id: int, req: AssignFocusTaskRequest, user: Dict[str, Any] = Depends(require_auth)):
    req.session_id = session_id
    return assign_focus_task(req, user)

@router.delete("/sessions/{session_id}")
def delete_focus_session(session_id: int, user: Dict[str, Any] = Depends(require_auth)):
    uid = get_uid(user)
    row = query_one("SELECT id FROM focus_sessions WHERE id = ? AND user_id = ?", (session_id, uid))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Focus session {session_id} not found")
    execute("DELETE FROM focus_sessions WHERE id = ? AND user_id = ?", (session_id, uid))
    notify_update("focus_updated", {"action": "deleted", "session_id": session_id})
    notify_update("analytics_updated", {})
    return {"ok": True, "deleted_id": session_id}

@router.post("/complete")
def complete_focus_session(req: CompleteFocusRequest, user: Dict[str, Any] = Depends(require_auth)):
    uid = get_uid(user)
    if req.session_id:
        row = query_one(
            "SELECT * FROM focus_sessions WHERE id = ? AND user_id = ?",
            (req.session_id, uid)
        )
    else:
        row = query_one(
            "SELECT * FROM focus_sessions WHERE user_id = ? AND status IN ('active', 'paused') ORDER BY id DESC LIMIT 1",
            (uid,)
        )

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active or paused session to complete")

    now = datetime.now(timezone.utc)
    total_sec = (row.get("duration_min") or 25) * 60
    rem = row.get("remaining_sec") if row["status"] == "paused" else 0
    actual_sec = req.actual_sec if req.actual_sec is not None else max(1, total_sec - rem)

    execute(
        """UPDATE focus_sessions
           SET status = 'completed', completed_at = ?, actual_sec = ?, remaining_sec = 0, notes = COALESCE(?, notes)
           WHERE id = ?""",
        (now.isoformat(), actual_sec, req.notes, row["id"])
    )

    completed_session = query_one(
        """SELECT fs.*, n.title as note_title, n.color as note_color, ci.text as item_text, ci.checked as item_checked
           FROM focus_sessions fs
           LEFT JOIN notes n ON n.id = fs.note_id
           LEFT JOIN checklist_items ci ON ci.uuid = fs.item_uuid
           WHERE fs.id = ?""",
        (row["id"],)
    )

    notify_update("focus_updated", {
        "action": "completed",
        "session_id": row["id"],
        "session_type": row["session_type"],
        "actual_sec": actual_sec,
        "session": completed_session
    })
    notify_update("analytics_updated", {})

    return {"ok": True, "actual_sec": actual_sec, "session": completed_session}

@router.get("/unassigned")
def get_unassigned_sessions(user: Dict[str, Any] = Depends(require_auth)):
    uid = get_uid(user)
    rows = query_all(
        """SELECT fs.*, n.title as note_title, ci.text as item_text
           FROM focus_sessions fs
           LEFT JOIN notes n ON n.id = fs.note_id
           LEFT JOIN checklist_items ci ON ci.uuid = fs.item_uuid
           WHERE fs.user_id = ? AND fs.status = 'completed'
             AND (fs.note_id IS NULL AND fs.item_uuid IS NULL AND (fs.notes IS NULL OR trim(fs.notes) = ''))
           ORDER BY fs.id DESC""",
        (uid,)
    )
    total_sec = sum(r.get("actual_sec") or 0 for r in rows)
    return {
        "unassigned": rows,
        "count": len(rows),
        "total_unassigned_sec": total_sec,
        "total_unassigned_min": round(total_sec / 60, 1)
    }

@router.get("/summary")
def get_focus_summary(user: Dict[str, Any] = Depends(require_auth)):
    uid = get_uid(user)
    total_row = query_one(
        "SELECT COALESCE(SUM(actual_sec), 0) as total_sec, COUNT(*) as count FROM focus_sessions WHERE user_id = ? AND status = 'completed'",
        (uid,)
    )
    unassigned_row = query_one(
        """SELECT COALESCE(SUM(actual_sec), 0) as total_sec, COUNT(*) as count FROM focus_sessions
           WHERE user_id = ? AND status = 'completed'
             AND (note_id IS NULL AND item_uuid IS NULL AND (notes IS NULL OR trim(notes) = ''))""",
        (uid,)
    )
    item_rows = query_all(
        """SELECT fs.item_uuid, ci.text as item_text, ci.note_id, n.title as note_title,
                  COALESCE(SUM(fs.actual_sec), 0) as total_sec, COUNT(fs.id) as session_count
           FROM focus_sessions fs
           JOIN checklist_items ci ON ci.uuid = fs.item_uuid
           LEFT JOIN notes n ON n.id = ci.note_id
           WHERE fs.user_id = ? AND fs.status = 'completed' AND fs.item_uuid IS NOT NULL
           GROUP BY fs.item_uuid, ci.text, ci.note_id, n.title""",
        (uid,)
    )
    note_rows = query_all(
        """SELECT fs.note_id, n.title as note_title, n.color as note_color,
                  COALESCE(SUM(fs.actual_sec), 0) as total_sec, COUNT(fs.id) as session_count
           FROM focus_sessions fs
           JOIN notes n ON n.id = fs.note_id
           WHERE fs.user_id = ? AND fs.status = 'completed' AND fs.note_id IS NOT NULL
           GROUP BY fs.note_id, n.title, n.color""",
        (uid,)
    )
    items_map = {
        r["item_uuid"]: {
            "total_sec": r["total_sec"],
            "total_min": round(r["total_sec"] / 60, 1),
            "session_count": r["session_count"],
            "text": r["item_text"],
            "note_title": r["note_title"]
        }
        for r in item_rows
    }
    notes_map = {
        r["note_id"]: {
            "total_sec": r["total_sec"],
            "total_min": round(r["total_sec"] / 60, 1),
            "session_count": r["session_count"],
            "title": r["note_title"],
            "color": r["note_color"]
        }
        for r in note_rows
    }

    total_sec = total_row["total_sec"] if total_row else 0
    unassigned_sec = unassigned_row["total_sec"] if unassigned_row else 0

    return {
        "total_sec": total_sec,
        "total_min": round(total_sec / 60, 1),
        "total_count": total_row["count"] if total_row else 0,
        "unassigned_sec": unassigned_sec,
        "unassigned_min": round(unassigned_sec / 60, 1),
        "unassigned_count": unassigned_row["count"] if unassigned_row else 0,
        "assigned_sec": max(0, total_sec - unassigned_sec),
        "assigned_min": round(max(0, total_sec - unassigned_sec) / 60, 1),
        "by_item": items_map,
        "by_note": notes_map
    }

@router.get("/history")
def get_focus_history(user: Dict[str, Any] = Depends(require_auth), unassigned_only: bool = Query(False), limit: int = Query(100)):
    uid = get_uid(user)
    where_extra = ""
    if unassigned_only:
        where_extra = " AND (fs.note_id IS NULL AND fs.item_uuid IS NULL AND (fs.notes IS NULL OR trim(fs.notes) = ''))"

    lim = max(1, min(200, limit))
    rows = query_all(
        f"""SELECT fs.*, n.title as note_title, n.color as note_color, ci.text as item_text, ci.checked as item_checked
           FROM focus_sessions fs
           LEFT JOIN notes n ON n.id = fs.note_id
           LEFT JOIN checklist_items ci ON ci.uuid = fs.item_uuid
           WHERE fs.user_id = ? AND fs.status = 'completed'{where_extra}
           ORDER BY fs.id DESC LIMIT ?""",
        (uid, lim)
    )
    for r in rows:
        is_assigned = bool(r.get("note_id") or r.get("item_uuid") or (r.get("notes") and str(r["notes"]).strip()))
        r["is_assigned"] = is_assigned

    return {"history": rows}

