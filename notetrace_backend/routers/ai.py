from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..auth import require_auth
from ..database import execute, query_all

router = APIRouter(prefix="/api/ai", tags=["ai"])

@router.get("/history")
def get_ai_history(user: Dict[str, Any] = Depends(require_auth)):
    uid = user.get("id")
    if uid is None:
        rows = query_all("SELECT role, content, created_at FROM ai_chat_history WHERE user_id IS NULL ORDER BY created_at ASC, id ASC LIMIT 100")
    else:
        rows = query_all("SELECT role, content, created_at FROM ai_chat_history WHERE user_id = ? ORDER BY created_at ASC, id ASC LIMIT 100", (uid,))
    return rows

class HistoryEntry(BaseModel):
    role: str
    content: str

@router.post("/history")
def add_ai_history(req: HistoryEntry, user: Dict[str, Any] = Depends(require_auth)):
    uid = user.get("id")
    if uid is None:
        execute("INSERT INTO ai_chat_history (user_id, role, content) VALUES (NULL, ?, ?)", (req.role, req.content))
    else:
        execute("INSERT INTO ai_chat_history (user_id, role, content) VALUES (?, ?, ?)", (uid, req.role, req.content))
    return {"ok": True}

@router.delete("/history")
def clear_ai_history(user: Dict[str, Any] = Depends(require_auth)):
    uid = user.get("id")
    if uid is None:
        execute("DELETE FROM ai_chat_history WHERE user_id IS NULL")
    else:
        execute("DELETE FROM ai_chat_history WHERE user_id = ?", (uid,))
    return {"ok": True}

@router.post("/chat")
def post_chat(payload: Dict[str, Any], user: Dict[str, Any] = Depends(require_auth)):
    return {"content": "Trace AI Assistant is ready."}

@router.post("/transcribe")
def post_transcribe(payload: Dict[str, Any], user: Dict[str, Any] = Depends(require_auth)):
    return {"text": "", "segments": []}

@router.post("/read-image")
def post_read_image(payload: Dict[str, Any], user: Dict[str, Any] = Depends(require_auth)):
    return {"text": ""}

@router.post("/relay")
def post_relay(payload: Dict[str, Any], user: Dict[str, Any] = Depends(require_auth)):
    return {"ok": True}
