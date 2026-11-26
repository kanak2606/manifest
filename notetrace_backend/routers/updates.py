from typing import Any, Dict
from fastapi import APIRouter, Depends
from ..auth import require_admin

router = APIRouter(prefix="/api/updates", tags=["updates"])

APP_VERSION = "1.1.2"

@router.get("/check")
def check_updates(admin: Dict[str, Any] = Depends(require_admin)):
    return {
        "current": APP_VERSION,
        "latest": APP_VERSION,
        "update_available": False,
        "channel": "stable",
        "release_notes": "NoteTrace Termux Android Edition",
        "release_url": "https://github.com/TraceApps/notetrace/releases",
        "published_at": None,
        "checked_at": None,
        "source": "cache",
        "update_check_enabled": True
    }

@router.get("/status")
def updates_status():
    return {
        "current": APP_VERSION,
        "update_check_enabled": True,
        "update_check_answered": True,
        "env_locked": False,
    }

@router.post("/dismiss")
def dismiss_update(admin: Dict[str, Any] = Depends(require_admin)):
    return {"ok": True}
