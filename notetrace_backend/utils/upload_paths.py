import os
from pathlib import Path
from urllib.parse import unquote
from typing import Optional
from ..config import UPLOADS_PATH

PRIVATE_SUBDIRS = ['backups']

EXT_BY_KIND = {
    'image': ['jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'heif', 'avif', 'bmp'],
    'audio': ['webm', 'weba', 'ogg', 'oga', 'opus', 'm4a', 'mp4', 'mp3', 'wav', 'aac', 'flac', 'amr', 'awb', '3gp', '3gpp'],
    'video': ['mp4', 'm4v', 'webm', 'mov', 'ogv', '3gp'],
}

EXT_BY_MIME = {
    'image/jpeg': 'jpg', 'image/png': 'png', 'image/gif': 'gif', 'image/webp': 'webp',
    'image/heic': 'heic', 'image/heif': 'heif', 'image/avif': 'avif', 'image/bmp': 'bmp',
    'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/opus': 'opus', 'audio/mp4': 'm4a',
    'audio/x-m4a': 'm4a', 'audio/mpeg': 'mp3', 'audio/mp3': 'mp3', 'audio/wav': 'wav',
    'audio/x-wav': 'wav', 'audio/wave': 'wav', 'audio/aac': 'aac', 'audio/flac': 'flac',
    'audio/amr': 'amr', 'audio/amr-wb': 'awb', 'audio/3gpp': '3gp',
    'video/mp4': 'mp4', 'video/webm': 'webm', 'video/quicktime': 'mov', 'video/ogg': 'ogv',
    'video/3gpp': '3gp',
}

DOCUMENT_EXTS = {
    'pdf', 'txt', 'md', 'markdown', 'csv', 'tsv', 'json', 'rtf', 'log', 'tex',
    'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'odt', 'ods', 'odp', 'odg',
    'pages', 'numbers', 'key', 'epub', 'mobi', 'azw3',
    'zip', '7z', 'rar', 'gz', 'tgz', 'tar', 'bz2', 'xz',
    'ics', 'vcf', 'gpx', 'kml', 'kmz', 'eml',
    'psd', 'ai', 'sketch', 'fig', 'xd', 'stl', '3mf', 'obj', 'step', 'stp', 'dwg', 'dxf',
    'ttf', 'otf', 'woff', 'woff2',
}

MEDIA_EXTS = {ext for exts in EXT_BY_KIND.values() for ext in exts}

def is_private_upload_path(req_path: str) -> bool:
    if not isinstance(req_path, str):
        return True
    try:
        decoded = unquote(req_path)
    except Exception:
        return True
    if '\0' in decoded:
        return True
    
    clean_path = decoded.lstrip('/')
    root = os.path.abspath(UPLOADS_PATH)
    abs_path = os.path.abspath(os.path.join(root, clean_path))
    
    lower_abs = abs_path.lower()
    for sub in PRIVATE_SUBDIRS:
        sub_dir = os.path.join(root, sub).lower()
        if lower_abs == sub_dir or lower_abs.startswith(sub_dir + os.sep):
            return True
    return False

def safe_upload_extension(mimetype: Optional[str], originalname: Optional[str]) -> str:
    mime = str(mimetype or '').lower().split(';')[0].strip()
    kind = mime.split('/')[0] if '/' in mime else ''
    
    orig = str(originalname or '').strip()
    own_ext = Path(orig).suffix.lower().lstrip('.')
    
    if kind in EXT_BY_KIND and own_ext in EXT_BY_KIND[kind]:
        return f".{own_ext}"
    if mime in EXT_BY_MIME:
        return f".{EXT_BY_MIME[mime]}"
    if own_ext in DOCUMENT_EXTS:
        return f".{own_ext}"
    return '.bin'

def upload_disposition(file_name: str) -> str:
    ext = Path(str(file_name)).suffix.lower().lstrip('.')
    return 'inline' if ext in MEDIA_EXTS else 'attachment'

UPLOAD_RESPONSE_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'Content-Security-Policy': "default-src 'none'; img-src 'self' data:; media-src 'self'; style-src 'unsafe-inline'; sandbox",
}
