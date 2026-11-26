import html
import os
from typing import Any, Dict
from urllib.parse import urlencode
from fastapi import APIRouter, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse

from ..config import BASE_URL, STATIC_DIR
from ..notes_logic import get_public_note

router = APIRouter(tags=["public-notes"])

STALE_PAGE_RECOVERY_JS = """(async () => {
  const app = document.getElementById('app');
  const say = (text) => { if (app) app.textContent = text; };
  const KEY = 'notetrace:public-link-retry';
  let again = !!(history.state && history.state.notetraceRetry);
  try { again = again || sessionStorage.getItem(KEY) === location.href; } catch {}
  const controller = navigator.serviceWorker && navigator.serviceWorker.controller;
  if (again || !controller) {
    try { sessionStorage.removeItem(KEY); } catch {}
    say('This link could not be opened. Reload the page to try again.');
    return;
  }
  say('Opening...');
  try { history.replaceState(Object.assign({}, history.state, { notetraceRetry: 1 }), ''); } catch {}
  try { sessionStorage.setItem(KEY, location.href); } catch {}
  try {
    const reg = await navigator.serviceWorker.getRegistration();
    if (reg && reg.active && reg.active.scriptURL === controller.scriptURL) await reg.unregister();
  } catch {}
  location.reload();
})();
"""

@router.get("/api/n/{token}")
def get_public_note_json(token: str):
    note = get_public_note(token)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note

@router.get("/n/assets/{rest:path}")
def get_stale_assets(rest: str):
    if not (rest.endswith(".js") or rest.endswith(".mjs")):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return Response(
        content=STALE_PAGE_RECOVERY_JS,
        media_type="text/javascript; charset=utf-8",
        headers={"Cache-Control": "no-store"}
    )

@router.get("/n/{token}")
def get_public_note_html(token: str, request: Request):
    index_path = os.path.join(STATIC_DIR, "index.html")
    raw_html = ""
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            raw_html = f.read()

    base_tag = f'<head>\n  <base href="{BASE_URL}/" />'
    templated = raw_html.replace("<head>", base_tag).replace("<HEAD>", base_tag)
    templated = templated.replace(
        "</head>",
        f'<script>window.__NOTE_CONFIG__ = {{ basePath: "{BASE_URL}" }};</script></head>'
    )

    note = get_public_note(token)
    if not note:
        return HTMLResponse(content=templated, status_code=404, headers={"Cache-Control": "no-store"})

    title = note.get("title") or "Untitled note"
    esc_title = html.escape(title)
    
    desc = note.get("body_md") or ""
    if note.get("items"):
        desc = " ".join(f"{'☑' if i.get('checked') else '☐'} {i.get('text', '')}" for i in note["items"])
    esc_desc = html.escape(desc[:200])

    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "localhost:8000"
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
    origin = f"{proto}://{host}"
    page_url = f"{origin}{BASE_URL}/n/{token}"

    head_tags = f"""
    <title>{esc_title}</title>
    <meta name="robots" content="noindex, nofollow" />
    <meta name="referrer" content="no-referrer" />
    <meta property="og:type" content="article" />
    <meta property="og:site_name" content="NoteTrace" />
    <meta property="og:title" content="{esc_title}" />
    <meta property="og:description" content="{esc_desc}" />
    <meta property="og:url" content="{page_url}" />
    <meta property="og:image" content="{origin}{BASE_URL}/icons/icon-512.png" />
    """

    swapped = templated.replace("<title>NoteTrace</title>", "").replace("</head>", f"{head_tags}\n</head>")

    return HTMLResponse(
        content=swapped,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Robots-Tag": "noindex, nofollow"
        }
    )

def _share_redirect(fields: Dict[str, Any]) -> RedirectResponse:
    params = {"share": "1"}
    for k in ("title", "text", "url"):
        val = fields.get(k)
        if val and isinstance(val, str):
            params[k] = val[:20000]
    return RedirectResponse(url=f"{BASE_URL}/#/?{urlencode(params)}", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/share-target")
def get_share_target(request: Request):
    return _share_redirect(dict(request.query_params))

@router.post("/share-target")
async def post_share_target(request: Request):
    form = await request.form()
    return _share_redirect(dict(form))
