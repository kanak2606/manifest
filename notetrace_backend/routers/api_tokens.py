import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..auth import require_admin, require_auth
from ..database import execute, query_all, query_one

router = APIRouter(prefix="/api/admin/api-tokens", tags=["api-tokens"])

KNOWN_SCOPES = ["mcp:read", "mcp:write", "mcp:destroy"]
SCOPE_DESCRIPTIONS = {
    "mcp:read": "MCP: read notes, checklists, and reminders.",
    "mcp:write": "MCP: create and edit notes, add and check off checklist items, set reminders and labels.",
    "mcp:destroy": "MCP: move notes to the trash. Requires every call to include confirm=true."
}

def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

@router.get("")
@router.get("/")
def get_tokens(admin: Dict[str, Any] = Depends(require_admin)):
    uid = admin.get("id")
    if not uid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="API tokens require a signed-in account.")
        
    rows = query_all("SELECT id, name, scopes, expires_at, last_used_at, created_at FROM api_tokens WHERE user_id = ? ORDER BY id DESC", (uid,))
    tokens = []
    for r in rows:
        sc = []
        try:
            sc = json.loads(r["scopes"])
        except Exception:
            pass
        tokens.append({
            "id": r["id"],
            "name": r["name"],
            "scopes": sc,
            "expires_at": r["expires_at"],
            "last_used_at": r["last_used_at"],
            "created_at": r["created_at"],
        })
        
    return {
        "tokens": tokens,
        "known_scopes": KNOWN_SCOPES,
        "scope_descriptions": SCOPE_DESCRIPTIONS,
        "mcp_state": {"enabled": True, "write": True, "destroy": True}
    }

class CreateTokenRequest(BaseModel):
    name: str
    scopes: Optional[List[str]] = None
    expires_at: Optional[str] = None

@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED)
def post_token(req: CreateTokenRequest, admin: Dict[str, Any] = Depends(require_admin)):
    uid = admin.get("id")
    if not uid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="API tokens require a signed-in account.")
        
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token name required")
        
    raw_token = f"note_pat_{secrets.token_urlsafe(32)}"
    thash = hash_token(raw_token)
    scopes_json = json.dumps(req.scopes or [])
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    tid = execute(
        """INSERT INTO api_tokens (user_id, name, token_hash, scopes, expires_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (uid, name, thash, scopes_json, req.expires_at, now_str)
    )

    row = {
        "id": tid,
        "name": name,
        "scopes": req.scopes or [],
        "expires_at": req.expires_at,
        "created_at": now_str,
    }
    return {"token": row, "raw": raw_token}

@router.delete("/{token_id}")
def delete_token(token_id: int, admin: Dict[str, Any] = Depends(require_admin)):
    uid = admin.get("id")
    cnt = execute("DELETE FROM api_tokens WHERE id = ? AND user_id = ?", (token_id, uid))
    if not cnt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return {"ok": True}
