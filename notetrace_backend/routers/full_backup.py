import json
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..auth import require_admin, require_auth
from ..config import BACKUPS_PATH, UPLOADS_PATH
from ..database import get_connection, query_all, query_one, rebuild_fts_index, transaction

router = APIRouter(prefix="/api/full-backup", tags=["full-backup"])

TABLES_TO_DUMP = [
    "users", "user_settings", "app_config", "ai_chat_history", "notes",
    "labels", "checklist_items", "note_labels", "note_versions",
    "note_members", "note_attachments", "api_tokens", "webhooks",
    "oidc_providers", "user_oidc_links"
]

def dump_database() -> Dict[str, Any]:
    dump = {}
    conn = get_connection()
    for t in TABLES_TO_DUMP:
        try:
            dump[t] = query_all(f"SELECT * FROM {t}")
        except Exception:
            dump[t] = []
    return dump

def restore_database_from_dict(dump: Dict[str, Any]):
    with transaction() as conn:
        for t in reversed(TABLES_TO_DUMP):
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass

        for t in TABLES_TO_DUMP:
            rows = dump.get(t) or []
            if not rows:
                continue
            cols = list(rows[0].keys())
            ph = ", ".join("?" for _ in cols)
            sql = f"INSERT OR REPLACE INTO {t} ({', '.join(cols)}) VALUES ({ph})"
            for r in rows:
                conn.execute(sql, [r[c] for c in cols])
                
    rebuild_fts_index()

def create_backup_zip() -> Dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    filename = f"notetrace-backup-{timestamp}.zip"
    dest_path = os.path.join(BACKUPS_PATH, filename)
    
    db_dump = dump_database()
    db_json_bytes = json.dumps(db_dump, indent=2).encode("utf-8")
    
    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("database.json", db_json_bytes)
        
        # Add uploads
        if os.path.exists(UPLOADS_PATH):
            for root, dirs, files in os.walk(UPLOADS_PATH):
                # Skip backups subdirectory
                if os.path.abspath(root).startswith(os.path.abspath(BACKUPS_PATH)):
                    continue
                for f in files:
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, UPLOADS_PATH)
                    zf.write(full_p, arcname=f"images/{rel_p.replace(os.sep, '/')}")
                    
    stat = os.stat(dest_path)
    return {
        "filename": filename,
        "size": stat.st_size,
        "createdAt": datetime.now(timezone.utc).isoformat()
    }

def restore_from_zip(zip_path: str):
    with zipfile.ZipFile(zip_path, "r") as zf:
        # 1. Restore database.json
        if "database.json" in zf.namelist():
            raw = zf.read("database.json").decode("utf-8")
            data = json.loads(raw)
            restore_database_from_dict(data)
            
        # 2. Extract images
        for member in zf.infolist():
            if member.filename.startswith("images/") and not member.is_dir():
                rel_name = member.filename[7:] # strip images/
                target_file = os.path.join(UPLOADS_PATH, rel_name)
                os.makedirs(os.path.dirname(target_file), exist_ok=True)
                with zf.open(member) as src, open(target_file, "wb") as dst:
                    shutil.copyfileobj(src, dst)

@router.post("")
@router.post("/")
def create_backup(admin: Dict[str, Any] = Depends(require_admin)):
    return create_backup_zip()

@router.get("")
@router.get("/")
def list_backups(admin: Dict[str, Any] = Depends(require_admin)):
    if not os.path.exists(BACKUPS_PATH):
        return []
    res = []
    for f in os.listdir(BACKUPS_PATH):
        if f.startswith("notetrace-backup-") and f.endswith(".zip"):
            p = os.path.join(BACKUPS_PATH, f)
            stat = os.stat(p)
            res.append({
                "filename": f,
                "size": stat.st_size,
                "createdAt": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
            })
    res.sort(key=lambda x: x["filename"], reverse=True)
    return res

@router.get("/schedule")
def get_schedule(admin: Dict[str, Any] = Depends(require_admin)):
    return {
        "schedule": "off",
        "time": "03:00",
        "retention": 7,
        "lastAutoRun": None,
        "lastAutoError": None,
        "envLocked": False,
    }

@router.put("/schedule")
def update_schedule(payload: Dict[str, Any], admin: Dict[str, Any] = Depends(require_admin)):
    return {
        "schedule": payload.get("schedule", "off"),
        "time": payload.get("time", "03:00"),
        "retention": payload.get("retention", 7),
        "lastAutoRun": None,
        "lastAutoError": None,
        "envLocked": False,
    }

@router.get("/{name}/download")
def download_backup(name: str, admin: Dict[str, Any] = Depends(require_admin)):
    clean_name = os.path.basename(name)
    p = os.path.join(BACKUPS_PATH, clean_name)
    if not os.path.exists(p):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    return FileResponse(p, filename=clean_name, media_type="application/zip")

@router.delete("/{name}")
def delete_backup(name: str, admin: Dict[str, Any] = Depends(require_admin)):
    clean_name = os.path.basename(name)
    p = os.path.join(BACKUPS_PATH, clean_name)
    if os.path.exists(p):
        os.unlink(p)
    return {"ok": True}

@router.post("/{name}/restore")
def restore_backup(name: str, admin: Dict[str, Any] = Depends(require_admin)):
    clean_name = os.path.basename(name)
    p = os.path.join(BACKUPS_PATH, clean_name)
    if not os.path.exists(p):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    restore_from_zip(p)
    return {"ok": True}

@router.post("/upload-restore")
async def upload_restore(backup: UploadFile = File(...), admin: Dict[str, Any] = Depends(require_admin)):
    temp_path = os.path.join(BACKUPS_PATH, f"tmp-restore-{secrets.token_hex(6)}.zip")
    try:
        content = await backup.read()
        with open(temp_path, "wb") as f:
            f.write(content)
        restore_from_zip(temp_path)
        return {"ok": True}
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
