import urllib.parse
from fastapi import APIRouter, HTTPException, Query, Response, status
import httpx
from ..utils.ssrf import is_safe_url

router = APIRouter(prefix="/api/proxy", tags=["proxy"])

IMG_ALLOWED = [
    'external-content.duckduckgo.com', 'i5.walmartimages.com', 'images.openfoodfacts.org',
    'i.imgur.com', 'upload.wikimedia.org', 'www.kroger.com', 'target.scene7.com'
]

def host_matches(hostname: str, allowed: str) -> bool:
    return hostname == allowed or hostname.endswith('.' + allowed)

@router.get("")
@router.get("/")
async def proxy_url(url: str = Query(...)):
    if not url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="url required")
    
    safe, err = is_safe_url(url)
    if not safe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Domain or target not allowed")

    try:
        parsed = urllib.parse.urlparse(url)
        is_img_host = any(host_matches(parsed.hostname or "", h) for h in IMG_ALLOWED)
        
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "NoteTrace/1.0"})
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=f"Upstream {resp.status_code}")
                
            content_type = resp.headers.get("content-type", "image/jpeg").lower()
            return Response(
                content=resp.content,
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "X-Content-Type-Options": "nosniff",
                    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox"
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
