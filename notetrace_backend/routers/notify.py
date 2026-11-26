from typing import Any, Dict
from fastapi import APIRouter, Depends
from ..auth import require_auth

router = APIRouter(prefix="/api/notify", tags=["notify"])

@router.post("/test")
def post_notify_test(payload: Dict[str, Any], user: Dict[str, Any] = Depends(require_auth)):
    return {"ok": True}

@router.post("")
@router.post("/")
def post_notify(payload: Dict[str, Any], user: Dict[str, Any] = Depends(require_auth)):
    return {"ok": True}
