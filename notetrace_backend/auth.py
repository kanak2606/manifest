import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
try:
    import bcrypt
    _HAS_BCRYPT = True
except ImportError:
    bcrypt = None
    _HAS_BCRYPT = False
import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import DEFAULT_SESSION_HOURS, JWT_SECRET, MAX_SESSION_HOURS
from .database import execute, query_one

security = HTTPBearer(auto_error=False)

def user_mgmt_active() -> bool:
    """Returns True if user management is active (at least one user exists)."""
    return query_one("SELECT 1 FROM users LIMIT 1") is not None

def setup_required() -> bool:
    """Returns True if this is a fresh install needing setup."""
    if user_mgmt_active():
        return False
    row = query_one("SELECT value FROM app_config WHERE key = 'single_user_mode'")
    return row is None or row.get("value") != "1"

def hash_password(password: str) -> str:
    if _HAS_BCRYPT and bcrypt is not None:
        salt = bcrypt.gensalt(12)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    salt = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"pbkdf2:sha256:{salt}:{derived.hex()}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        if hashed_password.startswith("pbkdf2:sha256:"):
            parts = hashed_password.split(":")
            if len(parts) == 4:
                salt = parts[2]
                target_hex = parts[3]
                derived = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), 100_000)
                return secrets.compare_digest(derived.hex(), target_hex)
        if _HAS_BCRYPT and bcrypt is not None:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        return False
    except Exception:
        return False

def get_session_hours() -> int:
    row = query_one("SELECT value FROM app_config WHERE key = 'session_hours'")
    if row and row.get("value"):
        try:
            val = int(row["value"])
            return min(val, MAX_SESSION_HOURS) if val > 0 else MAX_SESSION_HOURS
        except ValueError:
            pass
    return DEFAULT_SESSION_HOURS

def sign_token(user: Dict[str, Any]) -> str:
    hours = get_session_hours()
    now_utc = datetime.now(timezone.utc)
    csrf_token = secrets.token_hex(16)
    payload = {
        "id": user["id"],
        "username": user["username"],
        "role": user.get("role", "user"),
        "csrf": csrf_token,
        "iat": int(now_utc.timestamp()),
    }
    if hours > 0:
        payload["exp"] = int((now_utc + timedelta(hours=hours)).timestamp())
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def set_auth_cookie(response: Response, token: str):
    hours = get_session_hours()
    max_age = hours * 3600
    response.set_cookie(
        key="note_token",
        value=token,
        max_age=max_age,
        httponly=True,
        path="/",
        samesite="lax",
        secure=False  # Allow local Wi-Fi HTTP on LAN
    )

def lookup_raw_token(raw: str) -> Optional[Dict[str, Any]]:
    if not raw or not raw.startswith("note_pat_"):
        return None
    thash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    row = query_one(
        """SELECT t.id, t.user_id, t.name, t.scopes, t.expires_at,
                  u.username, u.full_name, u.role
           FROM api_tokens t
           JOIN users u ON u.id = t.user_id
           WHERE t.token_hash = ?""",
        (thash,)
    )
    if not row:
        return None

    if row.get("expires_at"):
        try:
            exp_dt = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00")).astimezone(timezone.utc)
            if exp_dt < datetime.now(timezone.utc):
                return None
        except Exception:
            pass

    try:
        execute("UPDATE api_tokens SET last_used_at = ? WHERE id = ?", (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), row["id"]))
    except Exception:
        pass

    return {
        "id": row["user_id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "role": row["role"],
        "token_id": row["id"]
    }

def decode_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

async def authenticate_request(request: Request) -> Optional[Dict[str, Any]]:
    """Checks Bearer token or note_token cookie and attaches user + auth_via."""
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token.startswith("note_pat_"):
            pat_user = lookup_raw_token(token)
            if pat_user:
                request.state.user = pat_user
                request.state.auth_via = "bearer"
                return pat_user
            request.state.user = None
            request.state.auth_via = None
            return None

        user_data = decode_token(token)
        if user_data:
            live_user = query_one("SELECT id, username, role, full_name FROM users WHERE id = ?", (user_data["id"],))
            if not live_user and user_data.get("username"):
                live_user = query_one("SELECT id, username, role, full_name FROM users WHERE username = ?", (user_data["username"],))
            if live_user:
                user_data["id"] = live_user["id"]
                user_data["role"] = live_user["role"]
                request.state.user = user_data
                request.state.auth_via = "bearer"
                return user_data
        request.state.user = None
        request.state.auth_via = None
        return None
    
    cookie_token = request.cookies.get("note_token")
    if cookie_token:
        user_data = decode_token(cookie_token)
        if user_data:
            live_user = query_one("SELECT id, username, role, full_name FROM users WHERE id = ?", (user_data["id"],))
            if not live_user and user_data.get("username"):
                live_user = query_one("SELECT id, username, role, full_name FROM users WHERE username = ?", (user_data["username"],))
            if live_user:
                user_data["id"] = live_user["id"]
                user_data["role"] = live_user["role"]
                request.state.user = user_data
                request.state.auth_via = "cookie"
                return user_data
    
    request.state.user = None
    request.state.auth_via = None
    return None

def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    return getattr(request.state, "user", None)

def require_auth(request: Request) -> Optional[Dict[str, Any]]:
    if not user_mgmt_active():
        # Single-user mode: allow everything
        return getattr(request.state, "user", None) or {"id": None, "username": "single_user", "role": "admin"}
    
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user

def require_admin(request: Request) -> Optional[Dict[str, Any]]:
    user = require_auth(request)
    if not user_mgmt_active():
        return user
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user
