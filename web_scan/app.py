"""Web scanner — Starlette app + JSON API over po_history.db.

A PDA / handheld scanner acts as a keyboard: it types the UPC + Enter into the
always-focused scan box on the page. Three modes mirror the Streamlit UPC Check
tab:

  * lookup  — scan a UPC → PO / style / colour / size / warehouse / units
  * verify  — pick a PO, scan each UPC → does it belong to that PO?
  * count   — 盘点: scan to +1 / -1 a physical count per UPC

Auth: one shared password (``PO_SCAN_PASSWORD``) gates the page; a correct login
sets a session cookie tied to a per-process token. Trusted-LAN posture, matching
the rest of the app. Company scope is fixed by ``PO_SCAN_COMPANIES`` (there is no
per-user login here), default = all companies.

The core logic (:func:`lookup` / :func:`verify` / :func:`count`) is pure and
store-injectable so it is unit-tested without HTTP.
"""
from __future__ import annotations

import hmac
import html
import os
import secrets
import time
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import (HTMLResponse, JSONResponse, PlainTextResponse,
                                  RedirectResponse, Response)
from starlette.routing import Route

from po_extractor.store import get_fabric_presentation_store, get_po_store

_TEMPLATES = Path(__file__).parent / "templates"
_COOKIE = "po_scan_session"

# Session token minted once per process start; the shared password unlocks it.
# Restarting the server invalidates every outstanding cookie — acceptable for a
# floor tool, and means there is nothing long-lived to steal.
_SESSION_TOKEN = secrets.token_urlsafe(32)

_SCAN_HTML = (_TEMPLATES / "scan.html").read_text(encoding="utf-8")
_LOGIN_HTML = (_TEMPLATES / "login.html").read_text(encoding="utf-8")


# ── config from environment ───────────────────────────────────────────────────

def _password() -> str:
    """Shared gate password. Defaults to 'scan' with a warning (see __main__)."""
    return os.environ.get("PO_SCAN_PASSWORD", "").strip() or "scan"


def _companies() -> list[str] | None:
    raw = os.environ.get("PO_SCAN_COMPANIES", "").strip()
    return [c.strip() for c in raw.split(",") if c.strip()] or None


def _authed(request: Request) -> bool:
    return hmac.compare_digest(request.cookies.get(_COOKIE, ""), _SESSION_TOKEN)


# ── login throttle (per-IP, in-memory) ────────────────────────────────────────
# The gate is a single shared password; without a throttle it is brute-forceable
# by anyone on the LAN. Allow a burst, then lock the IP out for a window.
_LOGIN_FAILS: dict[str, list[float]] = {}
_MAX_FAILS = 8
_WINDOW = 900.0        # 15 minutes


def _recent_fails(ip: str) -> int:
    now = time.monotonic()
    fails = [ts for ts in _LOGIN_FAILS.get(ip, []) if now - ts < _WINDOW]
    if fails:
        _LOGIN_FAILS[ip] = fails
    else:
        _LOGIN_FAILS.pop(ip, None)
    return len(fails)


def _record_fail(ip: str) -> None:
    _LOGIN_FAILS.setdefault(ip, []).append(time.monotonic())


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


# ── core logic (pure — takes a store, returns plain dicts) ─────────────────────

def _row(r: dict) -> dict:
    """Flatten a find_by_upc row to the fields the page shows."""
    return {
        "po_number":  r.get("po_number"),
        "style":      r.get("style"),
        "color":      r.get("color"),
        "size":       r.get("size"),
        "units":      r.get("units"),
        "upc":        r.get("upc"),
        "company":    r.get("company"),
        "warehouse":  r.get("destination_code"),
        "destination": r.get("ship_to"),
        "buyer":      r.get("buyer") or r.get("customer"),
        "xfty_date":  r.get("xfty_date"),
    }


def lookup(store, upc: str, companies=None) -> dict:
    upc = str(upc or "").strip()
    rows = store.find_by_upc(upc, companies=companies) if upc else []
    return {"upc": upc, "matched": bool(rows), "count": len(rows),
            "rows": [_row(r) for r in rows]}


def verify(store, po: str, upc: str, companies=None) -> dict:
    upc = str(upc or "").strip()
    po = str(po or "").strip()
    rows = store.find_by_upc(upc, companies=companies) if upc else []
    here = [r for r in rows if str(r.get("po_number")) == po]
    return {
        "upc": upc, "po": po,
        "ok": bool(here), "matched": bool(rows),
        # show the matching PO's row when it belongs, else where it DID land
        "rows": [_row(r) for r in (here or rows)],
        "other_pos": sorted({str(r.get("po_number")) for r in rows
                             if str(r.get("po_number")) != po}),
    }


def count(store, upc: str, delta: int, companies=None) -> dict:
    upc = str(upc or "").strip()
    d = int(delta)
    # One physical unit per scan; an explicit 0 is a no-op (returns the current
    # count) rather than being coerced to +1.
    delta = 0 if d == 0 else (1 if d > 0 else -1)
    qty = store.adjust_stocktake(upc, delta) if upc else 0
    ctx = store.find_by_upc(upc, companies=companies) if upc else []
    return {"upc": upc, "qty": qty, "delta": delta,
            "known": bool(ctx), "context": _row(ctx[0]) if ctx else None}


# ── HTTP layer ────────────────────────────────────────────────────────────────

def _deny(request: Request):
    """Return a 401 JSONResponse when unauthenticated, else None."""
    return None if _authed(request) else JSONResponse(
        {"error": "unauthorized"}, status_code=401)


async def _json(request: Request) -> dict:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def page(request: Request) -> Response:
    if not _authed(request):
        return RedirectResponse("/login", status_code=302)
    return HTMLResponse(_SCAN_HTML)


async def login_page(request: Request) -> Response:
    if _authed(request):
        return RedirectResponse("/", status_code=302)
    return HTMLResponse(_LOGIN_HTML.replace("<!--ERR-->", ""))


async def login_submit(request: Request) -> Response:
    ip = _client_ip(request)
    if _recent_fails(ip) >= _MAX_FAILS:
        return HTMLResponse(
            _LOGIN_HTML.replace("<!--ERR-->",
                                "尝试过多，请稍后再试 / Too many attempts — wait a few minutes"),
            status_code=429)
    form = await request.form()
    if hmac.compare_digest(str(form.get("password", "")), _password()):
        _LOGIN_FAILS.pop(ip, None)
        resp = RedirectResponse("/", status_code=302)
        resp.set_cookie(_COOKIE, _SESSION_TOKEN, httponly=True,
                        samesite="lax", max_age=12 * 3600)
        return resp
    _record_fail(ip)
    return HTMLResponse(
        _LOGIN_HTML.replace("<!--ERR-->", "密码错误 / Wrong password"),
        status_code=401)


async def logout(request: Request) -> Response:
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie(_COOKIE)
    return resp


async def api_lookup(request: Request) -> Response:
    if (deny := _deny(request)):
        return deny
    upc = str((await _json(request)).get("upc", "")).strip()
    if not upc:
        return JSONResponse({"error": "empty upc"}, status_code=400)
    res = await run_in_threadpool(lambda: lookup(get_po_store(), upc, _companies()))
    return JSONResponse(res)


async def api_verify(request: Request) -> Response:
    if (deny := _deny(request)):
        return deny
    body = await _json(request)
    upc = str(body.get("upc", "")).strip()
    po = str(body.get("po", "")).strip()
    if not upc:
        return JSONResponse({"error": "empty upc"}, status_code=400)
    if not po:
        return JSONResponse({"error": "no po selected"}, status_code=400)
    res = await run_in_threadpool(lambda: verify(get_po_store(), po, upc, _companies()))
    return JSONResponse(res)


async def api_count(request: Request) -> Response:
    if (deny := _deny(request)):
        return deny
    body = await _json(request)
    upc = str(body.get("upc", "")).strip()
    if not upc:
        return JSONResponse({"error": "empty upc"}, status_code=400)
    if "delta" in body:
        delta = int(body.get("delta") or 0)
    else:
        delta = 1 if str(body.get("dir", "add")) == "add" else -1
    res = await run_in_threadpool(lambda: count(get_po_store(), upc, delta, _companies()))
    return JSONResponse(res)


async def api_pos(request: Request) -> Response:
    if (deny := _deny(request)):
        return deny

    def _pos():
        df = get_po_store().list_pos(_companies())
        if df is None or df.empty or "po_number" not in df.columns:
            return []
        return sorted(str(p) for p in df["po_number"].dropna().unique())

    return JSONResponse({"pos": await run_in_threadpool(_pos)})


async def api_stocktake(request: Request) -> Response:
    if (deny := _deny(request)):
        return deny
    rows = await run_in_threadpool(lambda: get_po_store().load_stocktake())
    total = sum(int(r.get("qty") or 0) for r in rows)
    return JSONResponse({"rows": rows, "total": total})


async def api_stocktake_clear(request: Request) -> Response:
    if (deny := _deny(request)):
        return deny
    removed = await run_in_threadpool(lambda: get_po_store().clear_stocktake())
    return JSONResponse({"cleared": removed})


# ── Fabric presentation sheets (面料推荐单) ─────────────────────────────────────
# Each generated sheet carries a QR code pointing here.  Opening it records the
# scan — that log is what makes a sheet's send date answerable later — and shows
# which fabrics were on it.
#
# The internal RMB/M cost is deliberately NOT shown: this page is reached by
# scanning a sheet that may be in a customer's hands, and the login gate is a
# single shared LAN password, so it is the wrong place to expose cost.

def _presentation_html(pres: dict, lines: list[dict], scans: list[dict]) -> str:
    first = scans[-1]["scanned_at"] if scans else "—"
    rows = "".join(
        "<tr><td>{no}</td><td>{q}</td><td>{d}</td><td>{c}</td>"
        "<td>{g}</td><td>{w}</td><td>{usd}</td></tr>".format(
            no=html.escape(str(l.get("line_no") or "")),
            q=html.escape(str(l.get("quality_no") or "")),
            d=html.escape(str(l.get("description") or "")),
            c=html.escape(str(l.get("content") or "")),
            g=html.escape(str(l.get("weight_gsm") or "")),
            w=html.escape(str(l.get("width_in") or "")),
            usd=("%.2f" % l["price_usd_y"]) if l.get("price_usd_y") else "—",
        ) for l in lines)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(pres.get('title') or 'Presentation')}</title>
<style>
 body{{font-family:system-ui,-apple-system,sans-serif;margin:0;padding:12px;
      background:#f6f7f9;color:#111}}
 h1{{font-size:1.1rem;margin:0 0 2px}}
 .meta{{font-size:.85rem;color:#555;margin-bottom:10px}}
 .meta b{{color:#111}}
 table{{border-collapse:collapse;width:100%;background:#fff;font-size:.8rem}}
 th,td{{border:1px solid #d5d8dc;padding:5px 6px;text-align:left}}
 th{{background:#1f3864;color:#fff;position:sticky;top:0}}
 .wrap{{overflow-x:auto}}
</style></head><body>
<h1>{html.escape(pres.get('title') or 'Fabric Presentation')}</h1>
<div class="meta">
 <b>Customer:</b> {html.escape(pres.get('customer') or '—')} &nbsp;·&nbsp;
 <b>Submitted:</b> {html.escape(pres.get('submission_date') or '—')} &nbsp;·&nbsp;
 <b>Type:</b> {html.escape(pres.get('fabric_type') or '—')}<br>
 <b>Sheet ID:</b> {html.escape(pres.get('token') or '')} &nbsp;·&nbsp;
 <b>First scanned:</b> {html.escape(first)} &nbsp;·&nbsp;
 <b>Scans:</b> {len(scans)}
</div>
<div class="wrap"><table>
<tr><th>NO.</th><th>HHN_Fabric#</th><th>Description</th><th>Content</th>
    <th>gsm</th><th>Width</th><th>USD/Y</th></tr>
{rows}
</table></div>
</body></html>"""


async def presentation_page(request: Request) -> Response:
    if not _authed(request):
        return RedirectResponse("/login", status_code=302)
    token = request.path_params.get("token", "")
    ip, ua = _client_ip(request), request.headers.get("user-agent", "")

    def _load():
        store = get_fabric_presentation_store()
        pres = store.log_scan(token, client_ip=ip, user_agent=ua)
        if not pres:
            return None, [], []
        return pres, store.lines(pres["id"]), store.scans(pres["id"])

    pres, lines, scans = await run_in_threadpool(_load)
    if not pres:
        return HTMLResponse(
            "<!doctype html><meta charset='utf-8'>"
            "<p style='font-family:system-ui;padding:20px'>"
            "未找到该推荐单 / Presentation sheet not found.</p>",
            status_code=404)
    return HTMLResponse(_presentation_html(pres, lines, scans))


routes = [
    Route("/", page),
    Route("/login", login_page, methods=["GET"]),
    Route("/login", login_submit, methods=["POST"]),
    Route("/logout", logout),
    Route("/healthz", lambda r: PlainTextResponse("ok")),
    Route("/p/{token}", presentation_page),
    Route("/api/lookup", api_lookup, methods=["POST"]),
    Route("/api/verify", api_verify, methods=["POST"]),
    Route("/api/count", api_count, methods=["POST"]),
    Route("/api/pos", api_pos, methods=["GET"]),
    Route("/api/stocktake", api_stocktake, methods=["GET"]),
    Route("/api/stocktake/clear", api_stocktake_clear, methods=["POST"]),
]

app = Starlette(routes=routes)
