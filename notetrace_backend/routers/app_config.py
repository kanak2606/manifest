import os
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..auth import require_admin, require_auth
from ..database import execute, query_all, query_one

router = APIRouter(prefix="/api/app-config", tags=["app-config"])

ALLOWED_KEYS = {
    'smtp_host', 'smtp_port', 'smtp_secure', 'smtp_user', 'smtp_pass', 'smtp_from',
    'ai_enabled', 'ai_provider', 'ai_api_key', 'ai_model',
    'session_hours',
    'sharing_enabled',
    'password_policy',
}

@router.get("/env-locks")
def get_env_locks(user: Dict[str, Any] = Depends(require_auth)):
    return {
        "smtp": False,
        "ai": False,
        "ai_enabled": False,
        "oidc_provider_ids": [],
        "oidc_password_login_locked": False,
        "backup_locked": False,
    }

@router.get("/sharing")
def get_sharing_status(user: Dict[str, Any] = Depends(require_auth)):
    row = query_one("SELECT value FROM app_config WHERE key = 'sharing_enabled'")
    return {"sharing_enabled": row is not None and row.get("value") == "true"}

@router.get("")
@router.get("/")
def get_app_config(admin: Dict[str, Any] = Depends(require_admin)):
    rows = query_all("SELECT key, value FROM app_config")
    out = {}
    for r in rows:
        k = r["key"]
        v = r["value"] or ""
        if k in ('smtp_pass', 'ai_api_key'):
            out[k] = "••••••••" if v else ""
        else:
            out[k] = v
    return out

class PutAppConfigRequest(BaseModel):
    key: str
    value: Optional[str] = None

@router.put("")
@router.put("/")
def put_app_config(req: PutAppConfigRequest, admin: Dict[str, Any] = Depends(require_admin)):
    k = req.key
    v = req.value
    if k not in ALLOWED_KEYS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown config key")
    if (k in ('smtp_pass', 'ai_api_key')) and v == "••••••••":
        return {"ok": True}
        
    execute(
        """INSERT INTO app_config (key, value) VALUES (?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
        (k, v)
    )
    return {"ok": True}

@router.post("/test-email")
def post_test_email(admin: Dict[str, Any] = Depends(require_admin)):
    return {"ok": True}
