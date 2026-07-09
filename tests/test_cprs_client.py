"""Tests for the CPRS client (HTTP mocked; one optional live /health check)."""
from __future__ import annotations

import pytest

from po_extractor.utils.cprs_client import (
    CprsClient, cprs_from_settings, _norm, _as_bool,
)


class _Resp:
    def __init__(self, status=200, json_body=None, content=b""):
        self.status_code = status
        self._json = json_body if json_body is not None else {}
        self.content = content

    def json(self):
        return self._json


class _FakeRequests:
    """Minimal requests stand-in; scripted per (method, path-suffix)."""
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def _match(self, url):
        for suffix, resp in self.routes.items():
            if url.endswith(suffix):
                return resp
        return _Resp(404, {})

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("GET", url))
        return self._match(url)

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("POST", url, json))
        return self._match(url)


@pytest.fixture
def patched(monkeypatch):
    def _install(routes):
        fake = _FakeRequests(routes)
        import po_extractor.utils.cprs_client as mod
        monkeypatch.setitem(__import__("sys").modules, "requests", fake)
        return fake
    return _install


# ── construction / config ────────────────────────────────────────────────────

def test_base_url_normalized():
    assert CprsClient("http://h:3100/").base == "http://h:3100/api/v1"
    assert CprsClient("http://h:3100/api/v1").base == "http://h:3100/api/v1"


def test_cprs_from_settings_none_when_unconfigured():
    class S:
        def get(self, k, d=None): return ""
    assert cprs_from_settings(S()) is None


def test_cprs_from_settings_builds_when_url_set():
    class S:
        def get(self, k, d=None):
            return "http://h:3100" if "url" in k else "secret"
    c = cprs_from_settings(S())
    assert isinstance(c, CprsClient) and c.api_key == "secret"


# ── health ───────────────────────────────────────────────────────────────────

def test_health_ok(patched):
    patched({"/health": _Resp(200, {"status": "ok", "db": "ok"})})
    ok, msg = CprsClient("http://h:3100").health()
    assert ok and "OK" in msg


def test_health_no_url():
    ok, msg = CprsClient("").health()
    assert not ok and "base URL" in msg


# ── resolution + caching ─────────────────────────────────────────────────────

def test_resolve_client_fuzzy_and_cached(patched):
    fake = patched({"/clients": _Resp(200, [
        {"id": "a1", "name": "DKNY Sportswear"},
        {"id": "c3", "name": "Karl Lagerfeld Suits"},
    ])})
    c = CprsClient("http://h:3100", "k")
    assert c.resolve_client("DKNY Sportswear") == "a1"
    assert c.resolve_client("dkny") == "a1"          # containment
    # cached: /clients fetched once despite two resolves
    assert sum(1 for call in fake.calls if call[1].endswith("/clients")) == 1


def test_resolve_account_matches_catalog(patched):
    # Real API field names: account_code / account_name.
    patched({"/clients/a1/accounts": _Resp(200, [
        {"account_code": "MACYS", "account_name": "Macy's"},
        {"account_code": "ROSS", "account_name": "Ross Stores"},
    ])})
    c = CprsClient("http://h:3100", "k")
    assert c.resolve_account("MY MACY'S OMNI CHANNEL", "a1") == "MACYS"


def test_warehouse_flags_real_field_names(patched):
    # Real API: warehouse_code / rfid_default / msrp_required_default.
    patched({"/clients/a1/warehouses": _Resp(200, [
        {"warehouse_code": "UC", "rfid_default": True, "msrp_required_default": True},
        {"warehouse_code": "DN", "rfid_default": False, "msrp_required_default": False},
    ])})
    c = CprsClient("http://h:3100", "k")
    assert c.warehouse_flags("a1", "UC") == {"rfid": True, "msrp": True}
    assert c.warehouse_flags("a1", "DN") == {"rfid": False, "msrp": False}
    assert c.warehouse_flags("a1", "ZZ") == {"rfid": None, "msrp": None}


def test_resolve_client_matches_brand_field(patched):
    patched({"/clients": _Resp(200, [
        {"id": "a1", "name": "DKNY Sportswear", "brand": "DKNY"},
    ])})
    c = CprsClient("http://h:3100", "k")
    assert c.resolve_client("DKNY") == "a1"          # matches brand field


def test_carton_results_grouped_by_subtype(patched):
    patched({"/evaluate": _Resp(200, {"results": [
        {"domain": "carton", "subtype": "red_carton_sticker", "status": "confirmed"},
        {"domain": "carton", "subtype": "carton_marking", "status": "confirmed"},
        {"domain": "label", "subtype": "care", "status": "confirmed"},
    ]})})
    c = CprsClient("http://h:3100", "k")
    res = c.carton_results({"clientId": "a1", "warehouseCode": "UC"})
    assert set(res) == {"red_carton_sticker", "carton_marking"}


def test_get_failure_returns_empty_not_raise(patched):
    patched({"/clients": _Resp(500, {})})
    assert CprsClient("http://h:3100", "k").list_clients() == []


def test_manual_image_bytes(patched):
    patched({"/manual-images/ID_1/file": _Resp(200, content=b"\x89PNG...")})
    assert CprsClient("http://h:3100", "k").manual_image("ID_1") == b"\x89PNG..."


# ── helpers ──────────────────────────────────────────────────────────────────

def test_norm_and_bool():
    assert _norm("MY MACY'S  OMNI") == "MY MACY S OMNI"
    assert _as_bool("Yes") is True and _as_bool("no") is False and _as_bool(None) is None


# ── optional live check (skips if CPRS not running) ──────────────────────────

def test_live_health_if_available():
    import requests
    try:
        requests.get("http://localhost:3100/api/v1/health", timeout=2)
    except Exception:
        pytest.skip("CPRS not running locally")
    ok, msg = CprsClient("http://localhost:3100").health()
    assert ok, msg
