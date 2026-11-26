import os
import secrets
import time
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from ..auth import require_auth
from ..config import UPLOADS_PATH
from ..utils.image_localizer import detect_image_type
from ..utils.upload_paths import safe_upload_extension

router = APIRouter(prefix="/api/upload", tags=["upload"])

@router.post("")
@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(require_auth)
):
    if not file or not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file uploaded")
        
    content = await file.read()
    orig_name = file.filename or ""
    mimetype = file.content_type or "application/octet-stream"
    
    ext = safe_upload_extension(mimetype, orig_name)
    
    # If claims to be image, verify magic bytes
    if mimetype.startswith("image/"):
        detected = detect_image_type(content)
        if not detected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is not a supported image (JPEG, PNG, WebP, GIF, HEIC, AVIF, BMP)."
            )
            
    filename = f"{int(time.time() * 1000)}-{secrets.token_hex(6)}{ext}"
    target_path = os.path.join(UPLOADS_PATH, filename)
    with open(target_path, "wb") as f:
        f.write(content)
        
    return {
        "url": f"/uploads/{filename}",
        "mime": mimetype,
        "size": len(content)
    }

@router.post("/audio")
async def upload_audio(
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(require_auth)
):
    if not file or not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file uploaded")
        
    content = await file.read()
    orig_name = file.filename or "audio.webm"
    mimetype = file.content_type or "audio/webm"
    ext = safe_upload_extension(mimetype, orig_name)
    
    filename = f"{int(time.time() * 1000)}-{secrets.token_hex(6)}{ext}"
    target_path = os.path.join(UPLOADS_PATH, filename)
    with open(target_path, "wb") as f:
        f.write(content)
        
    return {
        "url": f"/uploads/{filename}",
        "mime": mimetype,
        "duration_ms": 0
    }

@router.post("/split")
async def split_audio(payload: Dict[str, Any], user: Dict[str, Any] = Depends(require_auth)):
    return {"pieces": []}

@router.get("/capabilities")
async def get_capabilities(user: Dict[str, Any] = Depends(require_auth)):
    return {"audio_convert": False}
