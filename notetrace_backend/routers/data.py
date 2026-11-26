from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends

from ..auth import require_auth
from ..database import execute, query_all
from .settings import is_server_only_key

router = APIRouter(prefix="/api/data", tags=["data"])

@router.delete("")
@router.delete("/")
def delete_all_data(user: Dict[str, Any] = Depends(require_auth)):
    u = user.get("id")
    if u is None:
        execute("UPDATE notes SET deleted_at = datetime('now'), updated_at = datetime('now') WHERE deleted_at IS NULL")
    else:
        execute("UPDATE notes SET deleted_at = datetime('now'), updated_at = datetime('now') WHERE user_id = ? AND deleted_at IS NULL", (u,))
    return {"ok": True}

@router.get("/export")
def export_user_data(user: Dict[str, Any] = Depends(require_auth)):
    u = user.get("id")
    out = {"exportedAt": datetime.now(timezone.utc).isoformat()}
    
    tables_soft = ["notes", "user_settings", "labels", "checklist_items", "note_labels", "note_attachments"]
    for t in tables_soft:
        if u is None:
            out[t] = query_all(f"SELECT * FROM {t} WHERE deleted_at IS NULL")
        else:
            out[t] = query_all(f"SELECT * FROM {t} WHERE user_id = ? AND deleted_at IS NULL", (u,))
            
    if out.get("user_settings"):
        out["user_settings"] = [r for r in out["user_settings"] if not is_server_only_key(r["key"])]
        
    # Note versions
    if u is None:
        out["note_versions"] = query_all(
            "SELECT v.* FROM note_versions v JOIN notes n ON n.id = v.note_id WHERE n.deleted_at IS NULL"
        )
    else:
        out["note_versions"] = query_all(
            "SELECT v.* FROM note_versions v JOIN notes n ON n.id = v.note_id WHERE n.user_id = ? AND n.deleted_at IS NULL",
            (u,)
        )
        
    # Hard delete tables: ai_chat_history
    if u is None:
        out["ai_chat_history"] = query_all("SELECT * FROM ai_chat_history")
    else:
        out["ai_chat_history"] = query_all("SELECT * FROM ai_chat_history WHERE user_id = ?", (u,))
        
    return out
