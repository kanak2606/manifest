from typing import Any, Dict
from fastapi import APIRouter, Header, HTTPException, Request, status

from ..database import query_one
from ..notes_logic import create_note, get_note, list_notes, tasks_due_count
from .api_tokens import hash_token

router = APIRouter(prefix="/api/mcp", tags=["mcp"])

def authenticate_mcp(auth_header: str) -> Dict[str, Any]:
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token required")
    raw_token = auth_header[7:].strip()
    thash = hash_token(raw_token)
    tok = query_one("SELECT * FROM api_tokens WHERE token_hash = ?", (thash,))
    if not tok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    u = query_one("SELECT * FROM users WHERE id = ?", (tok["user_id"],))
    return {"token": tok, "user": u}

@router.post("")
@router.post("/")
def handle_mcp(payload: Dict[str, Any], authorization: str = Header(None)):
    auth_data = authenticate_mcp(authorization)
    uid = auth_data["user"]["id"] if auth_data["user"] else None
    
    method = payload.get("method")
    req_id = payload.get("id")
    
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {"name": "list_notes", "description": "List or search notes", "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}}},
                    {"name": "get_note", "description": "Get note by ID", "inputSchema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}},
                    {"name": "create_note", "description": "Create a new note", "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "body_md": {"type": "string"}}}}
                ]
            }
        }
    elif method == "tools/call":
        params = payload.get("params") or {}
        tool_name = params.get("name")
        args = params.get("arguments") or {}
        
        if tool_name == "list_notes":
            notes = list_notes(uid, q=args.get("q", ""))
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": str(notes)}]}}
        elif tool_name == "get_note":
            n = get_note(uid, args["id"])
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": str(n)}]}}
        elif tool_name == "create_note":
            n = create_note(uid, args)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": str(n)}]}}

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}}
