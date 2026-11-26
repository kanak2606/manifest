import base64
import os
import re
import secrets
import time
from typing import Optional
from ..config import UPLOADS_PATH

DATA_URL_RE = re.compile(r'^data:image\/(jpeg|jpg|png|webp|gif|avif);base64,', re.IGNORECASE)
MAX_EMBEDDED_BYTES = 12 * 1024 * 1024

def detect_image_type(data: bytes) -> Optional[str]:
    if len(data) < 8:
        return None
    if data.startswith(b'\xff\xd8\xff'):
        return 'jpg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if data.startswith(b'GIF87a') or data.startswith(b'GIF89a'):
        return 'gif'
    if len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp'
    return None

def localize_data_url(value: Optional[str], subdir: str = "") -> Optional[str]:
    if not isinstance(value, str) or not DATA_URL_RE.match(value):
        return value
        
    parts = value.split(',', 1)
    if len(parts) != 2:
        return value
        
    head, b64_str = parts
    m = re.search(r'^data:image\/([a-z]+);', head, re.IGNORECASE)
    ext = m.group(1).lower().replace('jpeg', 'jpg') if m else 'jpg'
    
    try:
        data = base64.b64decode(b64_str)
    except Exception:
        return value
        
    if not data or len(data) > MAX_EMBEDDED_BYTES:
        return value
        
    detected = detect_image_type(data)
    if not detected:
        # Fallback to declared ext if valid image ext
        if ext not in ('jpg', 'png', 'gif', 'webp'):
            return value
    else:
        ext = detected
        
    target_dir = os.path.join(UPLOADS_PATH, subdir) if subdir else UPLOADS_PATH
    os.makedirs(target_dir, exist_ok=True)
    
    filename = f"{int(time.time() * 1000)}-{secrets.token_hex(6)}.{ext}"
    target_file = os.path.join(target_dir, filename)
    with open(target_file, "wb") as f:
        f.write(data)
        
    prefix = f"{subdir}/" if subdir else ""
    return f"/uploads/{prefix}{filename}"
