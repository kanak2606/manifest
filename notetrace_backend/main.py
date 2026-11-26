import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .auth import (
    authenticate_request,
    lookup_raw_token,
    set_auth_cookie,
    setup_required,
    sign_token,
    verify_password,
)
from .config import BASE_URL, HOST, PORT, STATIC_DIR, UPLOADS_PATH
from .csrf import csrf_protect
from .database import init_db, query_one
from .routers import (
    ai,
    analytics,
    api_tokens,
    app_config,
    auth,
    data,
    display,
    focus,
    full_backup,
    habits,
    labels,
    link_preview,
    mcp,
    network,
    notes,
    notify,
    proxy,
    public_notes,
    settings,
    sync,
    updates,
    upload,
    webhooks,
)
from .scheduler import start_scheduler, stop_scheduler
from .utils.upload_paths import (
    UPLOAD_RESPONSE_HEADERS,
    is_private_upload_path,
    upload_disposition,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()

app = FastAPI(title="Manifest", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Authentication & CSRF & Setup Enforcement Middleware
@app.middleware("http")
async def main_middleware(request: Request, call_next):
    # 1. Attach user from Bearer or cookie
    await authenticate_request(request)
    
    path = request.url.path
    
    # 2. Check CSRF on state-changing requests
    if path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
        await csrf_protect(request)
        
    # 3. Setup enforcement gate: block data APIs until first user is created
    if path.startswith("/api/") and not path.startswith("/api/auth") and path != "/api/health" and not path.startswith("/api/n/") and not path.startswith("/api/system/network"):
        if setup_required():
            return Response(
                content='{"error": "Setup required", "setup_required": true}',
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                media_type="application/json"
            )

    response = await call_next(request)
    
    # Disable cache on all API routes
    if path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
        
    return response

# Health check
@app.get("/api/health")
def api_health():
    if setup_required():
        return {"ok": True, "setup_required": True}
    return {"ok": True}

# Uploaded files serving with security headers
@app.get("/uploads/{file_path:path}")
def serve_upload(file_path: str):
    if is_private_upload_path(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        
    full_path = os.path.join(UPLOADS_PATH, file_path)
    if not os.path.exists(full_path) or os.path.isdir(full_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    disp = upload_disposition(file_path)
    headers = {
        "Cache-Control": "public, max-age=3600",
        **UPLOAD_RESPONSE_HEADERS
    }
    if disp == "attachment":
        headers["Content-Disposition"] = "attachment"

    return FileResponse(full_path, headers=headers)

# Include All Routers
app.include_router(display.router)
app.include_router(auth.router)
app.include_router(notes.router)
app.include_router(labels.router)
app.include_router(sync.router)
app.include_router(settings.router)
app.include_router(app_config.router)
app.include_router(upload.router)
app.include_router(full_backup.router)
app.include_router(data.router)
app.include_router(public_notes.router)
app.include_router(api_tokens.router)
app.include_router(webhooks.router)
app.include_router(notify.router)
app.include_router(updates.router)
app.include_router(link_preview.router)
app.include_router(proxy.router)
app.include_router(mcp.router)
app.include_router(ai.router)
app.include_router(focus.router)
app.include_router(habits.router)
app.include_router(analytics.router)
app.include_router(network.router)

# Mount frontend assets directories if static exists
if os.path.exists(STATIC_DIR):
    for sub in ("assets", "fonts", "icons", "pdfjs", "audio"):
        sub_p = os.path.join(STATIC_DIR, sub)
        if os.path.exists(sub_p):
            app.mount(f"/{sub}", StaticFiles(directory=sub_p), name=sub)

# Rate limiting for auto-login: max 5 failed attempts per client IP per 60 seconds
_auto_login_failures: Dict[str, List[float]] = {}

def check_rate_limit(client_ip: str):
    now = time.time()
    attempts = _auto_login_failures.get(client_ip, [])
    attempts = [t for t in attempts if now - t < 60]
    _auto_login_failures[client_ip] = attempts
    if len(attempts) >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed auto-login attempts from this IP. Please wait 60 seconds."
        )

def record_login_failure(client_ip: str):
    now = time.time()
    attempts = _auto_login_failures.get(client_ip, [])
    attempts.append(now)
    _auto_login_failures[client_ip] = attempts

def record_login_success(client_ip: str):
    _auto_login_failures.pop(client_ip, None)

def sanitize_redirect_target(target: Optional[str]) -> str:
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return "/"
    return target

def process_auto_login(request: Request) -> Optional[Response]:
    qp = request.query_params
    username = qp.get("username") or qp.get("u")
    password = qp.get("password") or qp.get("p")
    token = qp.get("token") or qp.get("key") or qp.get("auth_token")

    # Only process if credentials or token are provided
    if not (username and password) and not token:
        return None

    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(client_ip)

    user_to_login = None

    # 1. Token-based login (API PAT token)
    if token:
        token_str = token.strip()
        if token_str.startswith("note_pat_"):
            pat_data = lookup_raw_token(token_str)
            if pat_data:
                user_to_login = query_one("SELECT * FROM users WHERE id = ?", (pat_data["id"],))
        if not user_to_login:
            record_login_failure(client_ip)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auto-login token")

    # 2. Username & Password login
    elif username and password:
        uname = username.strip().lower()
        user = query_one("SELECT * FROM users WHERE username = ?", (uname,))
        if user and user.get("password_hash") and verify_password(password, user["password_hash"]):
            user_to_login = user
        else:
            record_login_failure(client_ip)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    if user_to_login:
        record_login_success(client_ip)
        jwt_token = sign_token(user_to_login)
        target = sanitize_redirect_target(qp.get("redirect") or qp.get("target"))

        # Security: Return HTTP 303 See Other redirect to immediately strip credentials from URL/history
        resp = RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)
        set_auth_cookie(resp, jwt_token)
        return resp

    return None

# Read and template index.html dynamically so frontend rebuilds reflect immediately
_index_html_cache: str = ""
_index_html_mtime: float = 0.0

def get_templated_index() -> str:
    global _index_html_cache, _index_html_mtime
    index_file = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_file):
        return ""
    try:
        mtime = os.path.getmtime(index_file)
        if mtime != _index_html_mtime or not _index_html_cache:
            with open(index_file, "r", encoding="utf-8") as f:
                raw = f.read()
                clean_script = (
                    f'<script>window.__NOTE_CONFIG__ = {{ basePath: "{BASE_URL}" }};'
                    "if (window.location.search && (window.location.search.includes('p=') || window.location.search.includes('password='))) {"
                    " try { window.history.replaceState({}, document.title, window.location.pathname + window.location.hash); } catch (e) {}"
                    "}</script>"
                )
                _index_html_cache = raw.replace("</head>", clean_script + "</head>")
                _index_html_mtime = mtime
        return _index_html_cache
    except Exception:
        return _index_html_cache

# Dedicated auto-login endpoint
@app.get("/auto-login")
def auto_login_endpoint(request: Request):
    resp = process_auto_login(request)
    if resp:
        return resp
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Auto-login requires credentials (?username=...&password=... or ?token=...)"
    )

# SPA fallback & root route
@app.get("/{full_path:path}")
def spa_fallback(full_path: str, request: Request):
    # Check if a static file exists in STATIC_DIR (e.g. sw.js, manifest.webmanifest, etc.)
    potential_file = os.path.join(STATIC_DIR, full_path)
    if full_path and os.path.isfile(potential_file):
        headers = {}
        if full_path in ("sw.js", "manifest.webmanifest", "index.html") or full_path.endswith(".html"):
            headers = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
        return FileResponse(potential_file, headers=headers)

    # Check for GET auto-login parameters (?u=...&p=... or ?username=...&password=... or ?token=...)
    if full_path in ("", "login", "auto-login"):
        auto_resp = process_auto_login(request)
        if auto_resp:
            return auto_resp

    templated = get_templated_index()
    if templated:
        return HTMLResponse(
            content=templated,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
        )
    if os.path.exists(index_file):
        return FileResponse(
            index_file,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
        )
        
    return HTMLResponse("<h1>Manifest Server is running. Frontend static build not found.</h1>")
