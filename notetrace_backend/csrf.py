from fastapi import HTTPException, Request, status
from .auth import user_mgmt_active

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
SKIP_PREFIXES = ("/api/auth/", "/n/", "/api/n/", "/display", "/api/display", "/share-target")
SKIP_SUFFIXES = ("/callback",)
BEARER_ONLY = ("/api/mcp",)

async def csrf_protect(request: Request):
    """CSRF protection for cookie-based PWA sessions."""
    if request.method in SAFE_METHODS:
        return
    
    path = request.url.path
    if any(path.startswith(p) for p in SKIP_PREFIXES):
        return
    if any(path.endswith(s) for s in SKIP_SUFFIXES):
        return
    if not user_mgmt_active():
        return
    
    auth_via = getattr(request.state, "auth_via", None)
    if auth_via == "bearer":
        return
    
    auth_header = request.headers.get("authorization") or ""
    if any(path == p or path.startswith(p + "/") for p in BEARER_ONLY) and auth_header.startswith("Bearer "):
        return
    
    user = getattr(request.state, "user", None)
    if not user or not user.get("csrf"):
        return
    
    csrf_header = request.headers.get("x-csrf-token")
    if not csrf_header or csrf_header != user.get("csrf"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token"
        )
