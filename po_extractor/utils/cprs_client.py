"""CPRS (Client PO Requirements System) REST client.

Resolves what a GIII garment PO requires — carton marking, red-sticker code,
prepack ratio, pack-out, MSRP/RFID — from the CPRS knowledge base, for the
GIII buy-plan exporter. See docs/GIII_BuyPlan_Field_Mapping.md.

Design
------
* Pure backend (no Streamlit); construct with (base_url, api_key).
* Read-only, best-effort: every method returns ``None``/``[]`` on any failure
  (network, auth, bad JSON) rather than raising, so a buy-plan export never
  fails just because the KB is down — the caller fills blanks and logs.
  The one exception is :meth:`health`, which returns (ok, message) so the
  admin Test-connection button can show *why* it failed.
* Per-instance caching: reference lists and evaluations are memoised by their
  arguments, so a multi-row buy plan makes a handful of calls, not one per row.
"""
from __future__ import annotations

import re

from ..config import (
    CPRS_TIMEOUT_S, CPRS_EXPORT_TIMEOUT_S, CPRS_SUITE_TIMEOUT_S,
)


class CprsClient:
    def __init__(self, base_url: str, api_key: str = "",
                 timeout: float = CPRS_TIMEOUT_S):
        # Normalize to ".../api/v1" with no trailing slash.
        base = (base_url or "").strip().rstrip("/")
        if base and not base.endswith("/api/v1"):
            base = base + "/api/v1"
        self.base = base
        self.api_key = (api_key or "").strip()
        self.timeout = timeout
        self._cache: dict = {}

    # ── low-level ────────────────────────────────────────────────────────────

    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if self.api_key:
            h["x-api-key"] = self.api_key
        return h

    def _get(self, path: str, params: dict | None = None):
        """GET JSON; return parsed body or None on any failure."""
        if not self.base:
            return None
        try:
            import requests
            r = requests.get(self.base + path, params=params,
                             headers=self._headers(), timeout=self.timeout)
            if not (200 <= r.status_code < 300):
                return None
            return r.json()
        except Exception:
            return None

    def _post(self, path: str, body: dict):
        if not self.base:
            return None
        try:
            import requests
            r = requests.post(self.base + path, json=body,
                              headers={**self._headers(),
                                       "Content-Type": "application/json"},
                              timeout=self.timeout)
            # NestJS returns 201 for POST — accept any 2xx, not just 200.
            if not (200 <= r.status_code < 300):
                return None
            return r.json()
        except Exception:
            return None

    # ── health (surfaces errors for the admin test button) ───────────────────

    def health_info(self) -> dict:
        """Full health probe for the status indicator. Public endpoint (no key).

        Returns ``{ok, status, db, version, message}``. ``message`` is the exact
        human string :meth:`health` has always returned, so existing callers are
        unaffected. Never raises."""
        if not self.base:
            return {"ok": False, "status": "", "db": "", "version": "",
                    "message": "No CPRS base URL configured."}
        try:
            import requests
            r = requests.get(self.base + "/health", timeout=self.timeout)
            if r.status_code != 200:
                return {"ok": False, "status": "", "db": "", "version": "",
                        "message": f"CPRS returned HTTP {r.status_code}."}
            try:
                body = r.json()
            except Exception:
                body = {}
            if not isinstance(body, dict):
                body = {}
            status = body.get("status", "")
            ok = status == "ok"
            db = body.get("db", "?")
            return {"ok": ok, "status": status, "db": str(db),
                    "version": str(body.get("version", "")),
                    "message": (f"CPRS OK (db: {db})." if ok
                                else f"CPRS status: {status or 'unknown'}.")}
        except Exception as exc:
            return {"ok": False, "status": "", "db": "", "version": "",
                    "message": f"Could not reach CPRS: {exc}"}

    def health(self) -> tuple[bool, str]:
        """Return (ok, message). Public endpoint — no API key required."""
        info = self.health_info()
        return info["ok"], info["message"]

    # ── reference data (cached) ──────────────────────────────────────────────

    def list_clients(self) -> list[dict]:
        if "clients" not in self._cache:
            data = self._get("/clients", {"active": "true"})
            if data is None:
                return []      # transient failure — retry next call, don't poison
            self._cache["clients"] = data if isinstance(data, list) else []
        return self._cache["clients"]

    def resolve_client(self, brand_name: str) -> str | None:
        """Fuzzy-match a brand name to a clientId (e.g. 'DKNY Sportswear')."""
        target = _norm(brand_name)
        if not target:
            return None
        # Rank candidates instead of returning the first containment hit —
        # "DKNY" alone matches BOTH "DKNY Sportswear" and "DKNY Suits", and
        # list order from the API is arbitrary. Exact full-name match wins;
        # otherwise the containment hit with the FEWEST extra tokens (so bare
        # "DKNY" prefers "DKNY Sportswear" only if nothing shorter exists —
        # ties keep API order but are at least deterministic per ranking).
        scored: list[tuple[int, int, str]] = []
        for i, c in enumerate(self.list_clients()):
            cid = c.get("id")
            name = _norm(c.get("name", ""))
            brand = _norm(c.get("brand", ""))
            division = _norm(c.get("division", ""))
            # GIII PDFs often carry the DIVISION code (e.g. "DW"), not the
            # brand name — match it as strongly as the brand field.
            if target in (name, brand, division):
                score = 0 if target == name else 1
            elif name and (target in name or name in target):
                score = 2 + abs(len(name.split()) - len(target.split()))
            else:
                # Token tier — count matches, treating vowel-dropped
                # abbreviations as equal ("DKNY W/SPRTSWR" → SPORTSWEAR),
                # so more-matching names win deterministically.
                toks = [t for t in target.split() if len(t) > 1]
                names = name.split() + brand.split()
                hits = sum(1 for t in toks if any(
                    t == n or (len(t) >= 4 and _devowel(t) == _devowel(n))
                    for n in names))
                if not hits:
                    continue
                score = 10 - min(hits, 5)
            scored.append((score, i, cid))
        return min(scored)[2] if scored else None

    def list_warehouses(self, client_id: str) -> list[dict]:
        key = ("wh", client_id)
        if key not in self._cache:
            data = self._get(f"/clients/{client_id}/warehouses")
            if data is None:
                return []      # transient failure — don't cache the miss
            self._cache[key] = data if isinstance(data, list) else []
        return self._cache[key]

    def list_accounts(self, client_id: str) -> list[dict]:
        key = ("acct", client_id)
        if key not in self._cache:
            data = self._get(f"/clients/{client_id}/accounts")
            if data is None:
                return []      # transient failure — don't cache the miss
            self._cache[key] = data if isinstance(data, list) else []
        return self._cache[key]

    def resolve_account(self, buyer_text: str, client_id: str) -> str | None:
        """Fuzzy-match buyer text (e.g. 'MY MACY'S OMNI CHANNEL') to an
        accountCode from the brand's account catalog. App-side logic is only
        this match; the catalog itself is CPRS-sourced."""
        target = _norm(buyer_text)
        if not target:
            return None
        toks = set(target.split())
        best = None
        for a in self.list_accounts(client_id):
            code = a.get("account_code") or a.get("code") or a.get("accountCode")
            name = _norm(a.get("account_name", "") or a.get("name", ""))
            code_n = _norm(code or "")
            if code_n and code_n in target:
                return code
            if name and (name in target or target in name):
                return code
            if best is None and name and (toks & set(name.split())):
                best = code
        return best

    def resolve_warehouse(self, ship_to: str, client_id: str) -> str | None:
        if not (ship_to and ship_to.strip()):
            return None
        key = ("whres", client_id, ship_to.strip())
        if key not in self._cache:
            data = self._get("/warehouse-lookup/resolve",
                             {"ship_to": ship_to, "client_id": client_id})
            if data is None:
                return None        # transient failure — don't cache the miss
            code = None
            if isinstance(data, dict):
                code = (data.get("warehouse_code") or data.get("warehouseCode")
                        or data.get("code"))
            self._cache[key] = code
        return self._cache[key]

    def warehouse_flags(self, client_id: str, warehouse_code: str) -> dict:
        """Return {'rfid': bool|None, 'msrp': bool|None, 'region': str} for a
        warehouse code, from the brand's warehouse defaults (cols V/W + the
        destination country/region)."""
        wc = _norm(warehouse_code)
        for w in self.list_warehouses(client_id):
            code = w.get("warehouse_code") or w.get("code") or w.get("warehouseCode")
            if _norm(code or "") == wc:
                return {"rfid": _as_bool(w.get("rfid_default", w.get("rfid"))),
                        "msrp": _as_bool(w.get("msrp_required_default", w.get("msrp"))),
                        "region": str(w.get("region") or "").strip().upper()}
        return {"rfid": None, "msrp": None, "region": ""}

    # ── evaluation (cached per order key) ────────────────────────────────────

    def evaluate(self, order: dict) -> list[dict]:
        """POST /evaluate; return the list of per-requirement results (or []).

        The cache key includes nested dicts (contextFields!) — leaving them
        out returned the stale no-context result after the operator supplied
        a runtime value like dim_code.
        """
        def _freeze(v):
            if isinstance(v, dict):
                return tuple(sorted((k, _freeze(x)) for k, x in v.items()))
            return str(v)

        key = ("eval", tuple(sorted((k, _freeze(v)) for k, v in order.items())))
        if key not in self._cache:
            data = self._post("/evaluate", order)
            if data is None:
                return []      # transient failure — don't cache the empty miss
            results = data.get("results", []) if isinstance(data, dict) else []
            self._cache[key] = results if isinstance(results, list) else []
        return self._cache[key]

    def evaluate_po(self, raw_po: dict) -> dict | None:
        """POST /evaluate/po — CPRS's one-call PO intake: it DECODES the raw PO
        (brand→client, ship-to→warehouse, account text→account code, channel,
        COO) AND evaluates it, so the app never re-resolves any of that itself.

        Returns ``{"decoded": {...}, "evaluation": {...}}`` (or ``None`` on
        failure). ``decoded.warehouseInfo`` carries region / rfid_default /
        msrp_required_default; ``evaluation.results`` is the full requirement
        list. Cached per raw-PO so a multi-row buy plan makes one call per PO.
        """
        def _freeze(v):
            if isinstance(v, dict):
                return tuple(sorted((k, _freeze(x)) for k, x in v.items()))
            return str(v)

        key = ("evalpo", tuple(sorted((k, _freeze(v)) for k, v in raw_po.items())))
        if key not in self._cache:
            data = self._post("/evaluate/po", raw_po)
            if data is None:
                return None        # transient failure — don't cache the miss
            self._cache[key] = data if isinstance(data, dict) else {}
        return self._cache[key] or None

    def carton_results(self, order: dict) -> dict:
        """Return the carton-domain results keyed by subtype (for cols P/Q)."""
        out: dict[str, dict] = {}
        for r in self.evaluate(order):
            if r.get("domain") == "carton":
                out[r.get("subtype", "")] = r
        return out

    def prepack_spec(self, client_id: str, account_code: str) -> dict:
        """Return {"ratio": <alpha|numeric>, "pcs_box": <pieces_per_bag>} for an
        account's prepack, read from the ``pre_pack_ratio`` requirement's
        per-account ``ratios`` (which ``/evaluate`` can't hand over cleanly
        because the two tier-1 rules conflict without an account filter)."""
        key = ("ppr", client_id)
        if key not in self._cache:
            # v1.6.5+ returns slim search items — structured_output (where the
            # per-account ratios live) must be requested explicitly.
            data = self._get("/search/requirements",
                             {"clientId": client_id, "subtype": "pre_pack_ratio",
                              "limit": 10, "include": "structured_output"})
            if data is None:
                # transient failure — don't cache an empty ratios map (it would
                # stick until restart), just return the blank spec this time.
                return {"ratio": "", "pcs_box": ""}
            items = data.get("data") or data.get("items") or data.get("results") \
                if isinstance(data, dict) else (data if isinstance(data, list) else [])
            ratios: dict[str, dict] = {}
            for it in (items or []):
                so = (it or {}).get("structured_output") or {}
                for acct, spec in (so.get("ratios") or {}).items():
                    if isinstance(spec, dict):
                        ratios.setdefault(_norm(acct), spec)
            self._cache[key] = ratios
        ratios = self._cache[key]
        if not (ratios and account_code):
            return {"ratio": "", "pcs_box": ""}
        target = _norm(account_code)
        spec = ratios.get(target)
        if spec is None:                     # token-overlap fallback (MARMAXX, TK_MAXX…)
            toks = set(target.split())
            for k, v in ratios.items():
                if toks & set(k.split()):
                    spec = v
                    break
        if not spec:
            return {"ratio": "", "pcs_box": ""}
        return {"ratio": str(spec.get("alpha") or spec.get("numeric") or ""),
                "pcs_box": str(spec.get("pieces_per_bag") or "")}

    def export_requirements_doc(self, body: dict) -> dict | None:
        """POST /export/requirements-doc (CPRS ≥1.6.14) — the API-generated
        requirements document.

        *body* carries the same order context as ``/evaluate/po`` plus the
        document options (``variant``, ``pos``, ``notes``, ``includeImages``);
        CPRS decides everything about content and rendering — the app passes
        the context through and saves the returned HTML verbatim (same
        no-local-gates principle as ``evaluate_po``).

        Returns ``{"html": bytes, "run_id": str, "card_count": str,
        "image_count": str}`` or ``None`` on failure. Deliberately uncached —
        a document must reflect the knowledge base at generation time — and
        on a longer timeout: embedded images make this call much heavier than
        an evaluation (the API allows up to ~18 MB of them).
        """
        if not self.base:
            return None
        try:
            import requests
            r = requests.post(self.base + "/export/requirements-doc",
                              json=body, headers=self._headers(),
                              timeout=CPRS_EXPORT_TIMEOUT_S)
            if r.status_code != 200:
                return None
            return {
                "html": r.content,
                "run_id": r.headers.get("X-CPRS-Run-Id", ""),
                "card_count": r.headers.get("X-CPRS-Card-Count", ""),
                "image_count": r.headers.get("X-CPRS-Image-Count", ""),
            }
        except Exception:
            return None

    def export_doc_suite(self, body: dict) -> dict | None:
        """POST /export/doc-suite (CPRS ≥1.6.15) — the full document pack.

        One call returns a ZIP holding the factory requirements HTML, the
        bilingual packing cards, the rules-driven trim list (.xlsx), the
        internal (priced) requirements HTML, and a manifest.json. *body* is
        the same decoded /evaluate context + pos/notes/pending as
        :meth:`export_requirements_doc`; CPRS builds everything — the app
        stores the returned ZIP verbatim.

        Returns ``{"zip": bytes, "run_id": str, "card_count": str,
        "image_count": str}`` or ``None``. Uncached; generous timeout — the
        observed pack is ~13 MB with embedded images.
        """
        if not self.base:
            return None
        try:
            import requests
            r = requests.post(self.base + "/export/doc-suite",
                              json=body, headers=self._headers(),
                              timeout=CPRS_SUITE_TIMEOUT_S)
            if r.status_code != 200:
                return None
            return {
                "zip": r.content,
                "run_id": r.headers.get("X-CPRS-Run-Id", ""),
                "card_count": r.headers.get("X-CPRS-Card-Count", ""),
                "image_count": r.headers.get("X-CPRS-Image-Count", ""),
            }
        except Exception:
            return None

    def manual_image(self, image_id: str) -> bytes | None:
        """Fetch a requirement's illustrative artwork as raw bytes."""
        if not (self.base and image_id):
            return None
        # image_id goes into the URL path — allow only safe id characters so a
        # crafted value ("../health") can't redirect the request.
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", str(image_id)):
            return None
        try:
            import requests
            r = requests.get(f"{self.base}/manual-images/{image_id}/file",
                             headers=self._headers(), timeout=self.timeout)
            return r.content if r.status_code == 200 else None
        except Exception:
            return None


# ── helpers ──────────────────────────────────────────────────────────────────

def cprs_from_settings(store) -> "CprsClient | None":
    """Build a CprsClient from an app-settings store, or None if unconfigured.

    *store* is any object with ``.get(key, default)`` (the app-settings store).
    Returns None when no base URL is set, so callers can cleanly skip CPRS.
    """
    from ..store.app_settings_store import KEY_CPRS_BASE_URL, KEY_CPRS_API_KEY
    base = store.get(KEY_CPRS_BASE_URL, "")
    if not (base or "").strip():
        return None
    return CprsClient(base, store.get(KEY_CPRS_API_KEY, ""))


def _norm(s) -> str:
    """Uppercase, collapse to alphanumerics+spaces for fuzzy matching."""
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 ]", " ", str(s or "").upper())).strip()


def _devowel(s: str) -> str:
    """Vowel-dropped form for abbreviation matching (SPORTSWEAR → SPRTSWR)."""
    s = str(s or "")
    return (s[:1] + re.sub(r"[AEIOU]", "", s[1:])) if s else s


def _as_bool(v):
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("true", "yes", "y", "1", "required"):
        return True
    if s in ("false", "no", "n", "0", "not required", ""):
        return False
    return None
