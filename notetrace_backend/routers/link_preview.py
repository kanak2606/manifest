import re
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
import httpx

from ..auth import require_auth
from ..database import execute, query_one
from ..utils.ssrf import is_safe_url

router = APIRouter(prefix="/api/link-preview", tags=["link-preview"])

@router.get("")
@router.get("/")
async def get_link_preview(url: str = Query(...), user: Dict[str, Any] = Depends(require_auth)):
    clean_url = str(url).strip()
    if not clean_url or len(clean_url) > 2048:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="url required")

    # Check cache
    cached = query_one("SELECT * FROM link_previews WHERE url = ?", (clean_url,))
    if cached:
        if not cached.get("ok"):
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        return {
            "url": cached["url"],
            "title": cached["title"],
            "description": cached["description"],
            "site": cached["site"],
            "image": cached["image_url"],
            "icon": cached["icon_url"],
        }

    safe, err = is_safe_url(clean_url)
    if not safe:
        execute("INSERT OR REPLACE INTO link_previews (url, ok) VALUES (?, 0)", (clean_url,))
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(clean_url, headers={"User-Agent": "NoteTrace/1.0"})
            if resp.status_code >= 400:
                execute("INSERT OR REPLACE INTO link_previews (url, ok) VALUES (?, 0)", (clean_url,))
                return Response(status_code=status.HTTP_204_NO_CONTENT)

            text = resp.text
            title_m = re.search(r'<meta property="og:title" content="([^"]+)"', text, re.I) or re.search(r'<title>([^<]+)</title>', text, re.I)
            desc_m = re.search(r'<meta property="og:description" content="([^"]+)"', text, re.I) or re.search(r'<meta name="description" content="([^"]+)"', text, re.I)
            img_m = re.search(r'<meta property="og:image" content="([^"]+)"', text, re.I)
            site_m = re.search(r'<meta property="og:site_name" content="([^"]+)"', text, re.I)

            title = title_m.group(1).strip() if title_m else None
            desc = desc_m.group(1).strip() if desc_m else None
            img = img_m.group(1).strip() if img_m else None
            site = site_m.group(1).strip() if site_m else None

            execute(
                """INSERT OR REPLACE INTO link_previews (url, ok, title, description, site, image_url, icon_url)
                   VALUES (?, 1, ?, ?, ?, ?, NULL)""",
                (clean_url, title, desc, site, img)
            )

            return {
                "url": clean_url,
                "title": title,
                "description": desc,
                "site": site,
                "image": img,
                "icon": None
            }
    except Exception:
        execute("INSERT OR REPLACE INTO link_previews (url, ok) VALUES (?, 0)", (clean_url,))
        return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/image")
async def get_preview_image(url: str = Query(...)):
    cached = query_one("SELECT image_url FROM link_previews WHERE url = ? AND ok = 1", (url,))
    if not cached or not cached.get("image_url"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
        
    img_url = cached["image_url"]
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            r = await client.get(img_url, headers={"User-Agent": "NoteTrace/1.0"})
            return Response(
                content=r.content,
                media_type=r.headers.get("content-type", "image/jpeg"),
                headers={
                    "Cache-Control": "public, max-age=604800",
                    "X-Content-Type-Options": "nosniff",
                    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox"
                }
            )
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not reachable")

@router.get("/icon")
async def get_preview_icon(url: str = Query(...)):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Icon not found")
