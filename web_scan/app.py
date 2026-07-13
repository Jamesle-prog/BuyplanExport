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
import os
import secrets
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import (HTMLResponse, JSONResponse, PlainTextResponse,
                                  RedirectResponse, Response)
from starlette.routing import Route

from po_extractor.store import get_po_store

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
    delta = 1 if int(delta) >= 0 else -1        # one physical unit per scan
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
    form = await request.form()
    if hmac.compare_digest(str(form.get("password", "")), _password()):
        resp = RedirectResponse("/", status_code=302)
        resp.set_cookie(_COOKIE, _SESSION_TOKEN, httponly=True,
                        samesite="lax", max_age=12 * 3600)
        return resp
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
