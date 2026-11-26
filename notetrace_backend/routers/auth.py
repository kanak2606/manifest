import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from ..auth import (
    decode_token,
    get_current_user,
    get_session_hours,
    hash_password,
    require_admin,
    require_auth,
    set_auth_cookie,
    setup_required,
    sign_token,
    user_mgmt_active,
    verify_password,
)
from ..config import BASE_URL
from ..database import execute, get_connection, query_all, query_one, transaction
from ..utils.image_localizer import localize_data_url

router = APIRouter(prefix="/api/auth", tags=["auth"])

def safe_user(u: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not u:
        return None
    d = dict(u)
    pw = d.pop("password_hash", None)
    d["has_password"] = bool(pw)
    d["linked_providers"] = []
    return d

def get_instance_id() -> str:
    row = query_one("SELECT value FROM app_config WHERE key = 'instance_id'")
    if row and row.get("value"):
        return row["value"]
    new_id = secrets.token_hex(16)
    execute("INSERT OR IGNORE INTO app_config (key, value) VALUES ('instance_id', ?)", (new_id,))
    return new_id

def claim_anonymous_data(user_id: int):
    tables = ['notes', 'labels', 'checklist_items', 'note_labels', 'note_attachments', 'ai_chat_history', 'notification_log']
    with transaction() as conn:
        for t in tables:
            conn.execute(f"UPDATE {t} SET user_id = ? WHERE user_id IS NULL", (user_id,))
        conn.execute("DELETE FROM app_config WHERE key = 'single_user_mode'")

@router.get("/status")
def auth_status():
    active = user_mgmt_active()
    single_user = query_one("SELECT value FROM app_config WHERE key = 'single_user_mode'")
    is_single_user = (single_user is not None and single_user.get("value") == "1")
    
    return {
        "active": active,
        "setup_required": setup_required(),
        "single_user_mode": is_single_user,
        "oidc": {
            "providers": [],
            "enable_email_password_login": True
        },
        "password_policy": "standard",
        "password_min_score": 0,
        "secure_cookies": False,
        "instance_id": get_instance_id(),
        "sync_version": 2,
    }

@router.get("/me")
def get_me(request: Request):
    user = get_current_user(request)
    if not user:
        return {"user": None, "csrf": None}
    db_u = query_one("SELECT * FROM users WHERE id = ?", (user["id"],))
    return {
        "user": safe_user(db_u),
        "csrf": user.get("csrf")
    }

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login")
def login(req_data: LoginRequest, response: Response):
    if setup_required():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This server isn't set up yet. Open it in a browser to create the first account."
        )
    username = req_data.username.strip().lower()
    user = query_one("SELECT * FROM users WHERE username = ?", (username,))
    if not user or not user.get("password_hash") or not verify_password(req_data.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    token = sign_token(user)
    set_auth_cookie(response, token)
    return {"user": safe_user(user), "token": token}

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("note_token", path="/")
    return {"ok": True}

class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None
    nickname: Optional[str] = None
    birthday: Optional[str] = None
    gender: Optional[str] = None
    role: Optional[str] = "user"
    email: Optional[str] = None

@router.post("/register")
def register(req_data: RegisterRequest, request: Request, response: Response):
    is_first = not user_mgmt_active()
    curr_user = get_current_user(request)
    
    if not is_first and (not curr_user or curr_user.get("role") != "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    username = req_data.username.strip().lower()
    if not username or not req_data.password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username and password required")

    existing = query_one("SELECT id FROM users WHERE username = ?", (username,))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")

    assigned_role = "admin" if is_first else ("admin" if req_data.role == "admin" else "user")
    p_hash = hash_password(req_data.password)
    email_clean = req_data.email.strip().lower() if req_data.email else None

    user_id = execute(
        """INSERT INTO users (username, password_hash, full_name, nickname, birthday, gender, role, email)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (username, p_hash, req_data.full_name, req_data.nickname, req_data.birthday, req_data.gender, assigned_role, email_clean)
    )

    created_user = query_one("SELECT * FROM users WHERE id = ?", (user_id,))
    if is_first:
        claim_anonymous_data(user_id)
        token = sign_token(created_user)
        set_auth_cookie(response, token)
        return {"user": safe_user(created_user), "token": token}

    return {"user": safe_user(created_user)}

class ProfileRequest(BaseModel):
    full_name: Optional[str] = None
    nickname: Optional[str] = None
    birthday: Optional[str] = None
    gender: Optional[str] = None
    avatar_url: Optional[str] = None
    email: Optional[str] = None

@router.put("/profile")
def update_profile(req_data: ProfileRequest, user: Dict[str, Any] = Depends(require_auth)):
    avatar = localize_data_url(req_data.avatar_url)
    email_clean = req_data.email.strip().lower() if req_data.email else None
    
    execute(
        """UPDATE users
           SET full_name = ?, nickname = ?, birthday = ?, gender = ?, avatar_url = ?, email = ?
           WHERE id = ?""",
        (req_data.full_name, req_data.nickname, req_data.birthday, req_data.gender, avatar, email_clean, user["id"])
    )
    updated = query_one("SELECT * FROM users WHERE id = ?", (user["id"],))
    return {"user": safe_user(updated)}

class PasswordRequest(BaseModel):
    current_password: Optional[str] = None
    new_password: str

@router.put("/password")
def change_password(req_data: PasswordRequest, response: Response, user: Dict[str, Any] = Depends(require_auth)):
    db_u = query_one("SELECT * FROM users WHERE id = ?", (user["id"],))
    if db_u.get("password_hash"):
        if not req_data.current_password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password required")
        if not verify_password(req_data.current_password, db_u["password_hash"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")

    p_hash = hash_password(req_data.new_password)
    execute("UPDATE users SET password_hash = ? WHERE id = ?", (p_hash, user["id"]))
    updated = query_one("SELECT * FROM users WHERE id = ?", (user["id"],))
    token = sign_token(updated)
    set_auth_cookie(response, token)
    return {"ok": True}

@router.get("/users/list")
def list_peers(user: Dict[str, Any] = Depends(require_auth)):
    if not user_mgmt_active():
        return []
    rows = query_all("SELECT id, full_name, username FROM users WHERE id != ? ORDER BY full_name, username", (user["id"],))
    return [{"id": r["id"], "name": r.get("full_name") or r["username"], "username": r["username"]} for r in rows]

@router.get("/users")
def admin_list_users(admin: Dict[str, Any] = Depends(require_admin)):
    rows = query_all("SELECT * FROM users ORDER BY created_at")
    return [safe_user(r) for r in rows]

@router.delete("/me")
def delete_own_account(response: Response, user: Dict[str, Any] = Depends(require_auth)):
    uid = user["id"]
    if user.get("role") == "admin":
        admins_cnt = query_one("SELECT COUNT(*) as c FROM users WHERE role = 'admin'")
        if admins_cnt and admins_cnt["c"] <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete the only admin account. Transfer admin to another user first.")

    execute("DELETE FROM users WHERE id = ?", (uid,))
    response.delete_cookie("note_token", path="/")
    return {"ok": True}

@router.delete("/users/{target_id}")
def admin_delete_user(target_id: int, admin: Dict[str, Any] = Depends(require_admin)):
    if target_id == admin["id"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself")
    execute("DELETE FROM users WHERE id = ?", (target_id,))
    return {"ok": True}

class UserPasswordReset(BaseModel):
    new_password: str

@router.put("/users/{target_id}/password")
def admin_reset_password(target_id: int, req_data: UserPasswordReset, admin: Dict[str, Any] = Depends(require_admin)):
    p_hash = hash_password(req_data.new_password)
    execute("UPDATE users SET password_hash = ? WHERE id = ?", (p_hash, target_id))
    return {"ok": True}

class PatchUserRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None

@router.patch("/users/{target_id}")
def admin_patch_user(target_id: int, req_data: PatchUserRequest, admin: Dict[str, Any] = Depends(require_admin)):
    target = query_one("SELECT id FROM users WHERE id = ?", (target_id,))
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
    updates = []
    params = []
    if req_data.full_name is not None:
        updates.append("full_name = ?")
        params.append(req_data.full_name.strip() or None)
        
    if req_data.email is not None:
        em = req_data.email.strip().lower()
        if em:
            dup = query_one("SELECT id FROM users WHERE email = ? AND id != ?", (em, target_id))
            if dup:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That email is already in use")
        updates.append("email = ?")
        params.append(em or None)

    if updates:
        params.append(target_id)
        execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)

    u = query_one("SELECT id, username, full_name, email, role, created_at FROM users WHERE id = ?", (target_id,))
    return {"ok": True, "user": u}

class UserRoleRequest(BaseModel):
    role: str

@router.put("/users/{target_id}/role")
def admin_change_role(target_id: int, req_data: UserRoleRequest, admin: Dict[str, Any] = Depends(require_admin)):
    if req_data.role not in ("admin", "user"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
    if target_id == admin["id"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot change your own role")
        
    if req_data.role != "admin":
        target = query_one("SELECT role FROM users WHERE id = ?", (target_id,))
        if target and target.get("role") == "admin":
            admins_cnt = query_one("SELECT COUNT(*) as c FROM users WHERE role = 'admin'")
            if admins_cnt and admins_cnt["c"] <= 1:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot demote the only admin. Promote another user to admin first.")

    execute("UPDATE users SET role = ? WHERE id = ?", (req_data.role, target_id))
    return {"ok": True}

@router.delete("/management")
def disable_user_management(response: Response, admin: Dict[str, Any] = Depends(require_admin)):
    with transaction() as conn:
        conn.execute("DELETE FROM users")
        conn.execute("INSERT INTO app_config (key, value) VALUES ('single_user_mode', '1') ON CONFLICT(key) DO UPDATE SET value = '1'")
    response.delete_cookie("note_token", path="/")
    return {"ok": True}

class RecoverRequest(BaseModel):
    token: str

@router.post("/recover")
def recover_single_user(req_data: RecoverRequest, response: Response):
    recovery_token = os.getenv("RECOVERY_TOKEN")
    if not recovery_token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Recovery not available. Set RECOVERY_TOKEN environment variable.")
    if req_data.token != recovery_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid recovery token.")
        
    with transaction() as conn:
        conn.execute("DELETE FROM users")
        conn.execute("INSERT INTO app_config (key, value) VALUES ('single_user_mode', '1') ON CONFLICT(key) DO UPDATE SET value = '1'")
    response.delete_cookie("note_token", path="/")
    return {"ok": True}

class ForgotPasswordRequest(BaseModel):
    email: str

@router.post("/forgot-password")
def forgot_password(req_data: ForgotPasswordRequest):
    # Constant response to prevent user enumeration
    user = query_one("SELECT id FROM users WHERE lower(email) = lower(?)", (req_data.email.strip(),))
    if user:
        execute("UPDATE password_reset_tokens SET used = 1 WHERE user_id = ?", (user["id"],))
        token = secrets.token_hex(32)
        expires = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        execute("INSERT INTO password_reset_tokens (token, user_id, expires_at) VALUES (?, ?, ?)", (token, user["id"], expires))
    return {"ok": True}

class ResetPasswordRequest(BaseModel):
    token: str
    password: str

@router.post("/reset-password")
def reset_password(req_data: ResetPasswordRequest, response: Response):
    row = query_one("SELECT * FROM password_reset_tokens WHERE token = ?", (req_data.token,))
    if not row or row.get("used"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset link")
    
    exp = parse_utc(row.get("expires_at"))
    if not exp or exp < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reset link has expired")

    p_hash = hash_password(req_data.password)
    execute("UPDATE users SET password_hash = ? WHERE id = ?", (p_hash, row["user_id"]))
    execute("UPDATE password_reset_tokens SET used = 1 WHERE token = ?", (req_data.token,))
    user = query_one("SELECT * FROM users WHERE id = ?", (row["user_id"],))
    token = sign_token(user)
    set_auth_cookie(response, token)
    return {"user": safe_user(user)}

class InviteRequest(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = "user"

@router.post("/invite")
def create_invite(req_data: InviteRequest, request: Request, admin: Dict[str, Any] = Depends(require_admin)):
    email_clean = req_data.email.strip().lower() if req_data.email else None
    if email_clean:
        existing = query_one("SELECT username FROM users WHERE lower(email) = ?", (email_clean,))
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"An account with that email already exists (username: {existing['username']})."
            )

    token = secrets.token_hex(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    execute(
        "INSERT INTO invite_tokens (token, email, role, created_by, expires_at) VALUES (?, ?, ?, ?, ?)",
        (token, email_clean, req_data.role or "user", admin["id"], expires)
    )

    host = request.headers.get("host") or "localhost:8000"
    proto = request.headers.get("x-forwarded-proto") or "http"
    base = f"{proto}://{host}{BASE_URL}"
    invite_url = f"{base}/#/accept-invite?token={token}"

    return {"ok": True, "sent": False, "inviteUrl": invite_url}

@router.get("/invites")
def list_invites(admin: Dict[str, Any] = Depends(require_admin)):
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows = query_all(
        "SELECT token, email, role, expires_at, created_by FROM invite_tokens WHERE used = 0 AND expires_at > ? ORDER BY expires_at DESC",
        (now_str,)
    )
    return rows

@router.delete("/invites/{token}")
def revoke_invite(token: str, admin: Dict[str, Any] = Depends(require_admin)):
    cnt = execute("DELETE FROM invite_tokens WHERE token = ?", (token,))
    return {"ok": True}

class AcceptInviteRequest(BaseModel):
    token: str
    username: str
    password: str
    full_name: Optional[str] = None

@router.post("/accept-invite")
def accept_invite(req_data: AcceptInviteRequest, response: Response):
    row = query_one("SELECT * FROM invite_tokens WHERE token = ?", (req_data.token,))
    if not row or row.get("used"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or already used invite link")
        
    exp = parse_utc(row.get("expires_at"))
    if not exp or exp < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite link has expired")

    username = req_data.username.strip().lower()
    dup = query_one("SELECT id FROM users WHERE username = ?", (username,))
    if dup:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")

    p_hash = hash_password(req_data.password)
    user_id = execute(
        "INSERT INTO users (username, password_hash, full_name, role, email) VALUES (?, ?, ?, ?, ?)",
        (username, p_hash, req_data.full_name, row.get("role", "user"), row.get("email"))
    )
    execute("UPDATE invite_tokens SET used = 1 WHERE token = ?", (req_data.token,))

    user = query_one("SELECT * FROM users WHERE id = ?", (user_id,))
    token = sign_token(user)
    set_auth_cookie(response, token)
    return {"user": safe_user(user)}

@router.get("/validate-token")
def validate_token(token: str, type: str):
    if type == "reset":
        row = query_one("SELECT * FROM password_reset_tokens WHERE token = ?", (token,))
        if not row or row.get("used"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired link")
        exp = parse_utc(row.get("expires_at"))
        if not exp or exp < datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired link")
        u = query_one("SELECT username FROM users WHERE id = ?", (row["user_id"],))
        return {"ok": True, "username": u.get("username") if u else None}
        
    elif type == "invite":
        row = query_one("SELECT * FROM invite_tokens WHERE token = ?", (token,))
        if not row or row.get("used"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired link")
        exp = parse_utc(row.get("expires_at"))
        if not exp or exp < datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired link")
        return {"ok": True, "email": row.get("email"), "role": row.get("role")}
        
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown token type")
