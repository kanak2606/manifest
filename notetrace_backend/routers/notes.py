from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from ..auth import require_auth
from ..events import notify_update
from ..notes_logic import (
    add_attachments,
    add_item,
    add_member,
    convert_note,
    create_note,
    create_public_link,
    delete_attachment,
    delete_item,
    delete_note_forever,
    empty_trash,
    find_note_by_title,
    get_attachment_drawing,
    get_note,
    get_public_link,
    import_notes,
    list_backlinks,
    list_members,
    list_note_titles,
    list_notes,
    list_versions,
    remove_member,
    reorder_items,
    restore_note,
    restore_version,
    revoke_public_link,
    tasks_due_count,
    trash_note,
    update_attachment,
    update_item,
    update_member,
    update_note,
)

router = APIRouter(prefix="/api/notes", tags=["notes"])

def get_uid(user: Dict[str, Any]) -> Optional[int]:
    return user.get("id")

@router.get("")
@router.get("/")
def get_notes(
    view: str = Query("notes"),
    label: Optional[int] = Query(None),
    q: str = Query(""),
    kind: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(require_auth)
):
    return list_notes(get_uid(user), view=view, label_id=label, q=q, kind=kind)

@router.post("")
@router.post("/")
def post_note(data: Dict[str, Any], user: Dict[str, Any] = Depends(require_auth)):
    note = create_note(get_uid(user), data)
    notify_update("note_created", {"id": note["id"]})
    return note

@router.post("/import")
def post_import_notes(payload: Dict[str, Any], user: Dict[str, Any] = Depends(require_auth)):
    notes_list = payload.get("notes")
    if not isinstance(notes_list, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expected array of notes")
    res = import_notes(get_uid(user), notes_list)
    notify_update("notes_imported", {})
    return res

@router.get("/counts")
def get_note_counts(today: Optional[str] = Query(None), user: Dict[str, Any] = Depends(require_auth)):
    return tasks_due_count(get_uid(user), today)

@router.get("/titles")
def get_note_titles(user: Dict[str, Any] = Depends(require_auth)):
    return list_note_titles(get_uid(user))

@router.get("/by-title")
def get_note_by_title(title: str = Query(""), user: Dict[str, Any] = Depends(require_auth)):
    note = find_note_by_title(get_uid(user), title)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note

@router.delete("/trash")
def delete_all_trash(user: Dict[str, Any] = Depends(require_auth)):
    cnt = empty_trash(get_uid(user))
    notify_update("trash_emptied", {})
    return {"deleted": cnt}

@router.get("/{note_id}")
def get_single_note(note_id: int, user: Dict[str, Any] = Depends(require_auth)):
    note = get_note(get_uid(user), note_id)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note

@router.patch("/{note_id}")
def patch_note(note_id: int, patch: Dict[str, Any], user: Dict[str, Any] = Depends(require_auth)):
    note = update_note(get_uid(user), note_id, patch)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    notify_update("note_updated", {"id": note_id})
    return note

class ConvertRequest(BaseModel):
    kind: str

@router.post("/{note_id}/convert")
def post_convert_note(note_id: int, req: ConvertRequest, user: Dict[str, Any] = Depends(require_auth)):
    note = convert_note(get_uid(user), note_id, req.kind)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    notify_update("note_converted", {"id": note_id})
    return note

@router.delete("/{note_id}")
def delete_note_trash(note_id: int, user: Dict[str, Any] = Depends(require_auth)):
    ok = trash_note(get_uid(user), note_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    notify_update("note_trashed", {"id": note_id})
    return {"ok": True}

@router.post("/{note_id}/restore")
def post_restore_note(note_id: int, user: Dict[str, Any] = Depends(require_auth)):
    ok = restore_note(get_uid(user), note_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    notify_update("note_restored", {"id": note_id})
    return {"ok": True}

@router.delete("/{note_id}/forever")
def delete_note_permanent(note_id: int, user: Dict[str, Any] = Depends(require_auth)):
    ok = delete_note_forever(get_uid(user), note_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    notify_update("note_deleted", {"id": note_id})
    return {"ok": True}

@router.post("/{note_id}/items")
def post_checklist_item(note_id: int, data: Dict[str, Any], user: Dict[str, Any] = Depends(require_auth)):
    note = add_item(get_uid(user), note_id, data)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    notify_update("item_added", {"note_id": note_id})
    return note

class ReorderItemsRequest(BaseModel):
    uuids: List[str]

@router.put("/{note_id}/items/order")
def put_reorder_items(note_id: int, req: ReorderItemsRequest, user: Dict[str, Any] = Depends(require_auth)):
    note = reorder_items(get_uid(user), note_id, req.uuids)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    notify_update("items_reordered", {"note_id": note_id})
    return note

@router.patch("/{note_id}/items/{uuid}")
def patch_checklist_item(note_id: int, uuid: str, patch: Dict[str, Any], user: Dict[str, Any] = Depends(require_auth)):
    note = update_item(get_uid(user), note_id, uuid, patch)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note or item not found")
    notify_update("item_updated", {"note_id": note_id, "uuid": uuid})
    return note

@router.delete("/{note_id}/items/{uuid}")
def delete_checklist_item(note_id: int, uuid: str, user: Dict[str, Any] = Depends(require_auth)):
    note = delete_item(get_uid(user), note_id, uuid)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note or item not found")
    notify_update("item_deleted", {"note_id": note_id, "uuid": uuid})
    return note

@router.get("/{note_id}/backlinks")
def get_backlinks(note_id: int, user: Dict[str, Any] = Depends(require_auth)):
    return list_backlinks(get_uid(user), note_id)

class AttachmentsRequest(BaseModel):
    attachments: List[Dict[str, Any]]

@router.post("/{note_id}/attachments")
def post_attachments(note_id: int, req: AttachmentsRequest, user: Dict[str, Any] = Depends(require_auth)):
    note = add_attachments(get_uid(user), note_id, req.attachments)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    notify_update("attachment_added", {"note_id": note_id})
    return note

@router.get("/{note_id}/attachments/{uuid}/drawing")
def get_drawing(note_id: int, uuid: str, user: Dict[str, Any] = Depends(require_auth)):
    data = get_attachment_drawing(get_uid(user), note_id, uuid)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Drawing not found")
    return data

@router.patch("/{note_id}/attachments/{uuid}")
def patch_attachment(note_id: int, uuid: str, patch: Dict[str, Any], user: Dict[str, Any] = Depends(require_auth)):
    note = update_attachment(get_uid(user), note_id, uuid, patch)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    notify_update("attachment_updated", {"note_id": note_id, "uuid": uuid})
    return note

@router.delete("/{note_id}/attachments/{uuid}")
def delete_attachment_route(note_id: int, uuid: str, user: Dict[str, Any] = Depends(require_auth)):
    note = delete_attachment(get_uid(user), note_id, uuid)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    notify_update("attachment_deleted", {"note_id": note_id, "uuid": uuid})
    return note

@router.get("/{note_id}/members")
def get_members(note_id: int, user: Dict[str, Any] = Depends(require_auth)):
    return {"members": list_members(get_uid(user), note_id)}

class AddMemberRequest(BaseModel):
    username: str
    role: Optional[str] = "edit"

@router.post("/{note_id}/members")
def post_member(note_id: int, req: AddMemberRequest, user: Dict[str, Any] = Depends(require_auth)):
    ok, err = add_member(get_uid(user), note_id, req.username, req.role or "edit")
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND if err == "User not found" else status.HTTP_400_BAD_REQUEST, detail=err or "Cannot add member")
    return {"members": list_members(get_uid(user), note_id)}

class UpdateMemberRequest(BaseModel):
    role: str

@router.patch("/{note_id}/members/{member_user_id}")
def patch_member(note_id: int, member_user_id: int, req: UpdateMemberRequest, user: Dict[str, Any] = Depends(require_auth)):
    ok = update_member(get_uid(user), note_id, member_user_id, req.role)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot update member")
    return {"ok": True}

@router.delete("/{note_id}/members/{member_user_id}")
def delete_member(note_id: int, member_user_id: int, user: Dict[str, Any] = Depends(require_auth)):
    ok = remove_member(get_uid(user), note_id, member_user_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove member")
    return {"ok": True}

@router.get("/{note_id}/public-link")
def get_public_link_route(note_id: int, user: Dict[str, Any] = Depends(require_auth)):
    note = get_note(get_uid(user), note_id)
    if not note or note.get("share_role") != "owner":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    tok = get_public_link(get_uid(user), note_id)
    return {"token": tok}

@router.post("/{note_id}/public-link")
def post_public_link(note_id: int, user: Dict[str, Any] = Depends(require_auth)):
    note = get_note(get_uid(user), note_id)
    if not note or note.get("share_role") != "owner":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    if note.get("trashed_at"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot share trashed note")
    tok = create_public_link(get_uid(user), note_id)
    return {"token": tok}

@router.delete("/{note_id}/public-link")
def delete_public_link(note_id: int, user: Dict[str, Any] = Depends(require_auth)):
    note = get_note(get_uid(user), note_id)
    if not note or note.get("share_role") != "owner":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    revoke_public_link(get_uid(user), note_id)
    return {"token": None}

@router.get("/{note_id}/versions")
def get_versions(note_id: int, user: Dict[str, Any] = Depends(require_auth)):
    return list_versions(get_uid(user), note_id)

@router.post("/{note_id}/versions/{version_id}/restore")
def post_restore_version(note_id: int, version_id: int, user: Dict[str, Any] = Depends(require_auth)):
    note = restore_version(get_uid(user), note_id, version_id)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    notify_update("version_restored", {"note_id": note_id})
    return note
