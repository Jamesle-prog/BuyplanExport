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
per-user LOGIN here), default = all companies.

Login also asks for a name -- not a second credential, just who is holding the
scanner. It rides in its own cookie, is shown on the scan page, and is stamped
onto stocktake adjustments (``upc_stocktake.updated_by``) and stocktake clears
(the shared ``change_log`` table) so a count that looks wrong can be traced to
a person. Blank names are refused at login; there is no way to skip it and get
an unattributed session.

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
from urllib.parse import quote, unquote

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import (HTMLResponse, JSONResponse, PlainTextResponse,
                                  RedirectResponse, Response)
from starlette.routing import Route

from po_extractor.store import get_po_store

_TEMPLATES = Path(__file__).parent / "templates"
_COOKIE = "po_scan_session"
_NAME_COOKIE = "po_scan_name"

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


def _operator_name(request: Request) -> str:
    """The name typed at login, for attribution -- not an identity check.
    '' if somehow absent (there is no way to reach an authed session without
    one, but a caller must never crash over a cookie the browser dropped).

    Percent-decoded: the cookie carries the name quote()-encoded, because
    HTTP headers are latin-1 and the operators this page exists for type
    姓名 in Chinese -- a raw CJK name in set_cookie raised UnicodeEncodeError
    and 500'd the login. unquote() of a value that was never encoded is a
    no-op for the names that worked before, so old cookies stay valid."""
    return unquote(request.cookies.get(_NAME_COOKIE, "")).strip()[:60]


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
    """The address the login throttle keys on.

    Through the Cloudflare tunnel every visitor reaches this process from
    loopback, which would collapse the per-IP throttle into one shared
    bucket -- one person mistyping the password _MAX_FAILS times would lock
    the whole warehouse out, and an attacker's failures would land in
    everyone's bucket. Cloudflare stamps the real visitor address in
    CF-Connecting-IP, so use that instead -- but ONLY when the request
    really did arrive via the local tunnel (peer is loopback). A LAN device
    hitting :8502 directly could otherwise spoof the header and rotate
    throttle buckets at will.
    """
    peer = request.client.host if request.client else "?"
    if peer in ("127.0.0.1", "::1"):
        cf = request.headers.get("CF-Connecting-IP", "").strip()
        if cf:
            return cf
    return peer


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


def count(store, upc: str, delta: int, companies=None, operator: str = "") -> dict:
    upc = str(upc or "").strip()
    d = int(delta)
    # One physical unit per scan; an explicit 0 is a no-op (returns the current
    # count) rather than being coerced to +1.
    delta = 0 if d == 0 else (1 if d > 0 else -1)
    qty = store.adjust_stocktake(upc, delta, operator) if upc else 0
    ctx = store.find_by_upc(upc, companies=companies) if upc else []
    return {"upc": upc, "qty": qty, "delta": delta,
            "known": bool(ctx), "context": _row(ctx[0]) if ctx else None}


# ── HTTP layer ────────────────────────────────────────────────────────────────

def _page(body: str, status_code: int = 200) -> HTMLResponse:
    """An HTML page that is never served from cache. Cheap PDA browsers cache
    aggressively; after an update, a cached copy of the OLD login page (no
    name field) kept showing until someone cleared the device -- 'still not
    working' with the fix already deployed. These pages are tiny; re-fetching
    them every time costs nothing."""
    return HTMLResponse(body, status_code=status_code,
                        headers={"Cache-Control": "no-store"})


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
    # The name is free text someone typed at login, not a fixed server string
    # like the login page's <!--ERR-->, so it MUST be escaped before landing
    # in raw HTML -- unlike ERR, this is a genuine injection point.
    name = html.escape(_operator_name(request))
    return _page(_SCAN_HTML.replace("<!--OPERATOR-->", name))


def _login_html(err: str = "", name: str = "") -> str:
    """Render the login page. *name* round-trips a wrong-password retry so
    the operator doesn't have to retype it -- it is free text someone typed,
    so (like the scan page's operator display) it MUST be escaped; <!--ERR-->
    only ever holds a fixed string from this module, never user input."""
    return (_LOGIN_HTML.replace("<!--ERR-->", err)
                       .replace("<!--NAME-->", html.escape(name)))


async def login_page(request: Request) -> Response:
    if _authed(request):
        return RedirectResponse("/", status_code=302)
    return _page(_login_html())


async def login_submit(request: Request) -> Response:
    ip = _client_ip(request)
    if _recent_fails(ip) >= _MAX_FAILS:
        return _page(
            _login_html("尝试过多，请稍后再试 / Too many attempts — wait a few minutes"),
            status_code=429)
    form = await request.form()
    name = str(form.get("name", "")).strip()[:60]
    if not hmac.compare_digest(str(form.get("password", "")), _password()):
        _record_fail(ip)
        return _page(
            _login_html("密码错误 / Wrong password", name), status_code=401)
    if not name:
        # Not a password guess -- this doesn't count toward the throttle.
        # Attribution is compulsory: there is no way to reach a session
        # without a name, matching how 船样要求 refuses a blank answer.
        return _page(
            _login_html("请输入姓名 / Enter your name"), status_code=400)
    _LOGIN_FAILS.pop(ip, None)
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie(_COOKIE, _SESSION_TOKEN, httponly=True,
                    samesite="lax", max_age=12 * 3600)
    # quote(): see _operator_name -- a Chinese name raw in a cookie header
    # is a UnicodeEncodeError, i.e. a 500 at login.
    resp.set_cookie(_NAME_COOKIE, quote(name, safe=""), httponly=True,
                    samesite="lax", max_age=12 * 3600)
    return resp


async def logout(request: Request) -> Response:
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie(_COOKIE)
    resp.delete_cookie(_NAME_COOKIE)
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
    operator = _operator_name(request)
    res = await run_in_threadpool(
        lambda: count(get_po_store(), upc, delta, _companies(), operator))
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


def _log_stocktake_clear(operator: str, removed: int) -> None:
    """Record who wiped the shared stocktake. Never raises -- an audit
    hiccup must not undermine the clear it describes (see ChangeLogStore).

    The one write this module makes worth a log row: unlike a single scan
    (routine, instantly reversible the other direction), a clear wipes every
    UPC's count at once and cannot be undone from the PDA. A single ordinary
    scan is not logged here for the same reason a Sky East upload logs one
    summary row, not one per item -- see change_log_store's own docstring.
    """
    if not removed:
        return
    try:
        from po_extractor.store import get_change_log_store
        from po_extractor.store.change_log_store import ACTION_DELETE, ENTITY_STOCKTAKE
        get_change_log_store().record(
            ENTITY_STOCKTAKE, "upc_stocktake", ACTION_DELETE,
            detail=f"{removed} stocktake count(s) cleared", username=operator)
    except Exception:
        pass


async def api_stocktake_clear(request: Request) -> Response:
    if (deny := _deny(request)):
        return deny
    operator = _operator_name(request)
    removed = await run_in_threadpool(lambda: get_po_store().clear_stocktake())
    _log_stocktake_clear(operator, removed)
    return JSONResponse({"cleared": removed})


routes = [
    Route("/", page),
    Route("/login", login_page, methods=["GET"]),
    Route("/login", login_submit, methods=["POST"]),
    Route("/logout", logout),
    Route("/healthz", lambda r: PlainTextResponse("ok")),
    Route("/api/lookup", api_lookup, methods=["POST"]),
    Route("/api/verify", api_verify, methods=["POST"]),
    Route("/api/count", api_count, methods=["POST"]),
    Route("/api/pos", api_pos, methods=["GET"]),
    Route("/api/stocktake", api_stocktake, methods=["GET"]),
    Route("/api/stocktake/clear", api_stocktake_clear, methods=["POST"]),
]

app = Starlette(routes=routes)
