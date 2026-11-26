from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..auth import require_auth
from ..events import notify_update
from ..notes_logic import (
    create_label,
    delete_label,
    list_labels,
    reorder_labels,
    update_label,
)

router = APIRouter(prefix="/api/labels", tags=["labels"])

def get_uid(user: Dict[str, Any]) -> Optional[int]:
    return user.get("id")

@router.get("")
@router.get("/")
def get_all_labels(user: Dict[str, Any] = Depends(require_auth)):
    return list_labels(get_uid(user))

@router.post("")
@router.post("/", status_code=status.HTTP_201_CREATED)
def post_label(data: Dict[str, Any], user: Dict[str, Any] = Depends(require_auth)):
    res = create_label(get_uid(user), data)
    if res.get("error"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=res["error"])
    notify_update("labels_changed", {})
    return res

class ReorderLabelsRequest(BaseModel):
    ids: List[int]

@router.put("/order")
def put_reorder_labels(req: ReorderLabelsRequest, user: Dict[str, Any] = Depends(require_auth)):
    res = reorder_labels(get_uid(user), req.ids)
    notify_update("labels_changed", {})
    return res

@router.patch("/{label_id}")
def patch_label(label_id: int, data: Dict[str, Any], user: Dict[str, Any] = Depends(require_auth)):
    res = update_label(get_uid(user), label_id, data)
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found")
    if res.get("error"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=res["error"])
    notify_update("labels_changed", {})
    return res

@router.delete("/{label_id}")
def delete_label_route(label_id: int, user: Dict[str, Any] = Depends(require_auth)):
    ok = delete_label(get_uid(user), label_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found")
    notify_update("labels_changed", {})
    return {"ok": True}
