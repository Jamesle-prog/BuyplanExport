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


class CprsClient:
    def __init__(self, base_url: str, api_key: str = "", timeout: float = 8.0):
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
            if r.status_code != 200:
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
            if r.status_code != 200:
                return None
            return r.json()
        except Exception:
            return None

    # ── health (surfaces errors for the admin test button) ───────────────────

    def health(self) -> tuple[bool, str]:
        """Return (ok, message). Public endpoint — no API key required."""
        if not self.base:
            return False, "No CPRS base URL configured."
        try:
            import requests
            r = requests.get(self.base + "/health", timeout=self.timeout)
            if r.status_code != 200:
                return False, f"CPRS returned HTTP {r.status_code}."
            body = r.json()
            if body.get("status") == "ok":
                return True, f"CPRS OK (db: {body.get('db', '?')})."
            return False, f"CPRS status: {body.get('status', 'unknown')}."
        except Exception as exc:
            return False, f"Could not reach CPRS: {exc}"

    # ── reference data (cached) ──────────────────────────────────────────────

    def list_clients(self) -> list[dict]:
        if "clients" not in self._cache:
            data = self._get("/clients", {"active": "true"})
            self._cache["clients"] = data if isinstance(data, list) else []
        return self._cache["clients"]

    def resolve_client(self, brand_name: str) -> str | None:
        """Fuzzy-match a brand name to a clientId (e.g. 'DKNY Sportswear')."""
        target = _norm(brand_name)
        if not target:
            return None
        best = None
        for c in self.list_clients():
            names = [_norm(c.get("name", "")), _norm(c.get("brand", ""))]
            for name in filter(None, names):
                if name == target or target in name or name in target:
                    return c.get("id")   # exact/containment hit wins
                if best is None and (set(target.split()) & set(name.split())):
                    best = c.get("id")
        return best

    def list_warehouses(self, client_id: str) -> list[dict]:
        key = ("wh", client_id)
        if key not in self._cache:
            data = self._get(f"/clients/{client_id}/warehouses")
            self._cache[key] = data if isinstance(data, list) else []
        return self._cache[key]

    def list_accounts(self, client_id: str) -> list[dict]:
        key = ("acct", client_id)
        if key not in self._cache:
            data = self._get(f"/clients/{client_id}/accounts")
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
        data = self._get("/warehouse-lookup/resolve",
                         {"ship_to": ship_to, "client_id": client_id})
        if isinstance(data, dict):
            return (data.get("warehouse_code") or data.get("warehouseCode")
                    or data.get("code"))
        return None

    def warehouse_flags(self, client_id: str, warehouse_code: str) -> dict:
        """Return {'rfid': bool|None, 'msrp': bool|None} for a warehouse code,
        from the brand's warehouse defaults (drives cols V/W)."""
        wc = _norm(warehouse_code)
        for w in self.list_warehouses(client_id):
            code = w.get("warehouse_code") or w.get("code") or w.get("warehouseCode")
            if _norm(code or "") == wc:
                return {"rfid": _as_bool(w.get("rfid_default", w.get("rfid"))),
                        "msrp": _as_bool(w.get("msrp_required_default", w.get("msrp")))}
        return {"rfid": None, "msrp": None}

    # ── evaluation (cached per order key) ────────────────────────────────────

    def evaluate(self, order: dict) -> list[dict]:
        """POST /evaluate; return the list of per-requirement results (or [])."""
        key = ("eval", tuple(sorted(
            (k, str(v)) for k, v in order.items() if not isinstance(v, dict))))
        if key not in self._cache:
            data = self._post("/evaluate", order)
            results = data.get("results", []) if isinstance(data, dict) else []
            self._cache[key] = results if isinstance(results, list) else []
        return self._cache[key]

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
            data = self._get("/search/requirements",
                             {"clientId": client_id, "subtype": "pre_pack_ratio",
                              "limit": 10})
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

    def manual_image(self, image_id: str) -> bytes | None:
        """Fetch a requirement's illustrative artwork as raw bytes."""
        if not (self.base and image_id):
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
