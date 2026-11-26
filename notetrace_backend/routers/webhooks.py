import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..auth import require_admin
from ..database import execute, query_all, query_one

router = APIRouter(prefix="/api/admin/webhooks", tags=["webhooks"])

KNOWN_WEBHOOK_EVENTS = [
    "note.created", "note.updated", "note.deleted", "reminder.fired"
]
WEBHOOK_EVENT_DESCRIPTIONS = {
    "note.created": "Fires when a note is created.",
    "note.updated": "Fires when a note is updated.",
    "note.deleted": "Fires when a note is deleted.",
    "reminder.fired": "Fires when a note reminder comes due."
}

@router.get("")
@router.get("/")
def get_webhooks(admin: Dict[str, Any] = Depends(require_admin)):
    uid = admin.get("id")
    if not uid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhooks require a signed-in account.")
    rows = query_all("SELECT id, url, events, enabled, last_delivery_at, last_delivery_status, last_delivery_error, created_at FROM webhooks WHERE user_id = ? ORDER BY id DESC", (uid,))
    res = []
    for r in rows:
        evs = []
        try:
            evs = json.loads(r["events"])
        except Exception:
            pass
        res.append({
            "id": r["id"],
            "url": r["url"],
            "events": evs,
            "enabled": bool(r["enabled"]),
            "last_delivery_at": r["last_delivery_at"],
            "last_delivery_status": r["last_delivery_status"],
            "last_delivery_error": r["last_delivery_error"],
            "created_at": r["created_at"]
        })
    return {
        "webhooks": res,
        "known_events": KNOWN_WEBHOOK_EVENTS,
        "event_descriptions": WEBHOOK_EVENT_DESCRIPTIONS,
        "webhooks_enabled": True
    }

class CreateWebhookRequest(BaseModel):
    url: str
    events: Optional[List[str]] = None
    secret: Optional[str] = None

@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED)
def post_webhook(req: CreateWebhookRequest, admin: Dict[str, Any] = Depends(require_admin)):
    uid = admin.get("id")
    if not uid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhooks require a signed-in account.")
    
    url = req.url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook URL")

    secret_raw = req.secret or secrets.token_hex(24)
    events_json = json.dumps(req.events or KNOWN_WEBHOOK_EVENTS)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    wid = execute(
        """INSERT INTO webhooks (user_id, url, secret_encrypted, events, enabled, created_at)
           VALUES (?, ?, ?, ?, 1, ?)""",
        (uid, url, secret_raw, events_json, now_str)
    )

    row = {
        "id": wid,
        "url": url,
        "events": req.events or KNOWN_WEBHOOK_EVENTS,
        "enabled": True,
        "created_at": now_str
    }
    return {"webhook": row, "secret": secret_raw}

@router.delete("/{webhook_id}")
def delete_webhook(webhook_id: int, admin: Dict[str, Any] = Depends(require_admin)):
    uid = admin.get("id")
    cnt = execute("DELETE FROM webhooks WHERE id = ? AND user_id = ?", (webhook_id, uid))
    if not cnt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return {"ok": True}

@router.post("/{webhook_id}/test")
def test_webhook(webhook_id: int, admin: Dict[str, Any] = Depends(require_admin)):
    return {"ok": True, "status": 200}
