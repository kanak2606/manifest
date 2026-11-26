import json
import re
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from ..auth import require_auth, user_mgmt_active
from ..database import execute, query_all, query_one, transaction
from ..events import notify_update

router = APIRouter(prefix="/api/settings", tags=["settings"])

SERVER_ONLY_KEYS = {
    'cooktraceUrl',
    'cooktraceToken',
    'cooktraceInfo',
    'cooktraceEnabled',
}

SERVER_ONLY_PATTERNS = [
    re.compile(r'_client_secret$', re.IGNORECASE),
    re.compile(r'_consumer_secret$', re.IGNORECASE),
    re.compile(r'_api_secret$', re.IGNORECASE),
    re.compile(r'_redirect_uri$', re.IGNORECASE),
    re.compile(r'_client_id$', re.IGNORECASE),
]

def is_server_only_key(key: str) -> bool:
    if key in SERVER_ONLY_KEYS:
        return True
    return any(p.search(key) for p in SERVER_ONLY_PATTERNS)

@router.get("")
@router.get("/")
def get_settings(user: Dict[str, Any] = Depends(require_auth)):
    if not user_mgmt_active() or not user or not user.get("id"):
        return {}
    rows = query_all("SELECT key, value FROM user_settings WHERE user_id = ? AND deleted_at IS NULL", (user["id"],))
    out = {}
    for r in rows:
        k = r["key"]
        if is_server_only_key(k):
            continue
        v = r["value"]
        try:
            out[k] = json.loads(v)
        except Exception:
            out[k] = v
    return out

class PutSettingRequest(BaseModel):
    key: str
    value: Any

@router.put("")
@router.put("/")
def put_setting(req_data: PutSettingRequest, user: Dict[str, Any] = Depends(require_auth)):
    if not user_mgmt_active() or not user or not user.get("id"):
        return {"ok": True}
    key = req_data.key
    if not key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="key required")
    if is_server_only_key(key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden key")
    
    val_json = json.dumps(req_data.value)
    execute(
        """INSERT INTO user_settings (user_id, key, value, updated_at) VALUES (?, ?, ?, datetime('now'))
           ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value, updated_at = datetime('now'), deleted_at = NULL""",
        (user["id"], key, val_json)
    )
    notify_update("settings_changed", {"key": key})
    return {"ok": True}

class BulkSettingsRequest(BaseModel):
    settings: Dict[str, Any]

@router.put("/bulk")
def put_settings_bulk(req_data: BulkSettingsRequest, user: Dict[str, Any] = Depends(require_auth)):
    if not user_mgmt_active() or not user or not user.get("id"):
        return {"ok": True}
        
    written = 0
    skipped = 0
    with transaction() as conn:
        for k, v in req_data.settings.items():
            if is_server_only_key(k):
                skipped += 1
                continue
            val_json = json.dumps(v)
            conn.execute(
                """INSERT INTO user_settings (user_id, key, value, updated_at) VALUES (?, ?, ?, datetime('now'))
                   ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value, updated_at = datetime('now'), deleted_at = NULL""",
                (user["id"], k, val_json)
            )
            written += 1
            
    notify_update("settings_changed", {})
    return {"ok": True, "written": written, "skipped": skipped}

@router.delete("")
@router.delete("/")
def delete_settings(user: Dict[str, Any] = Depends(require_auth)):
    if user_mgmt_active() and user and user.get("id"):
        execute(
            "UPDATE user_settings SET deleted_at = datetime('now'), updated_at = datetime('now') WHERE user_id = ?",
            (user["id"],)
        )
        notify_update("settings_changed", {})
    return {"ok": True}

@router.post("/claim-celebration")
def claim_celebration(payload: Dict[str, Any], user: Dict[str, Any] = Depends(require_auth)):
    date_str = payload.get("date") or datetime.now().strftime("%Y-%m-%d")
    uid = user.get("id") or 0
    key = f"celebration_{date_str}"
    row = query_one("SELECT value FROM user_settings WHERE user_id = ? AND key = ?", (uid, key))
    if row:
        return {"fired": False}
    execute("INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, '1')", (uid, key))
    return {"fired": True}

@router.post("/gotify-test")
def gotify_test(payload: Dict[str, Any]):
    return {"ok": True}

@router.post("/push-test")
def push_test(payload: Dict[str, Any]):
    return {"ok": True}

@router.post("/force-sync")
def force_sync(user: Dict[str, Any] = Depends(require_auth)):
    return {"ok": True}
