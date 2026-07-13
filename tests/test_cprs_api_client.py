"""Generated CPRS API client — models + HTTP layer (mocked transport)."""
from __future__ import annotations

import json

import pytest

from po_extractor.cprs import CprsApiClient, CprsError, models as M


# ── models ────────────────────────────────────────────────────────────────────

def test_nested_from_dict_builds_models_and_keeps_extra():
    run = M.EvaluationRunResponseDto.from_dict({
        "evaluationRunId": "r1", "orderContextId": "o1", "status": "done",
        "summary": {"total": 3, "confirmed": 2, "pending_input": 1, "conflict": 0,
                    "not_applicable": 0, "missing_mandatory_context": 0},
        "results": [{"domain": "carton", "subtype": "mark", "status": "confirmed",
                     "extraField": "keep"}],
        "topLevelUnknown": "x",
    })
    assert isinstance(run.summary, M.EvaluationSummaryDto)
    assert run.summary.confirmed == 2
    assert isinstance(run.results[0], M.EvaluationResultItemDto)
    assert run.results[0].extra["extraField"] == "keep"   # undocumented field kept
    assert run.extra["topLevelUnknown"] == "x"


def test_to_dict_merges_extra_and_drops_none():
    oc = M.CreateOrderContextDto(clientId="c1", channel="WHOLESALE",
                                 extra={"customField": 1})
    assert oc.to_dict() == {"clientId": "c1", "channel": "WHOLESALE", "customField": 1}


def test_undocumented_dto_carries_everything_via_extra():
    lg = M.LoginDto(extra={"email": "a@b.c", "password": "x"})
    assert lg.to_dict() == {"email": "a@b.c", "password": "x"}


def test_all_29_models_exported():
    assert len([n for n in M.__all__ if n != "CprsModel"]) == 29


# ── mocked HTTP layer ─────────────────────────────────────────────────────────

class _FakeResp:
    def __init__(self, status=200, body=None, content=b"", text=""):
        self.status_code = status
        self._body = body
        self.content = content if content else (
            json.dumps(body).encode() if body is not None else b"")
        self.text = text or (json.dumps(body) if body is not None else "")

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


@pytest.fixture()
def calls(monkeypatch):
    """Capture requests.request calls; each test sets the response via .resp."""
    recorded = {"args": None, "kwargs": None, "resp": _FakeResp(200, {})}

    def fake_request(method, url, **kwargs):
        recorded["args"] = (method, url)
        recorded["kwargs"] = kwargs
        r = recorded["resp"]
        if isinstance(r, Exception):
            raise r
        return r

    import requests
    monkeypatch.setattr(requests, "request", fake_request)
    return recorded


def test_groups_and_method_count():
    c = CprsApiClient("http://localhost:3100", api_key="k")
    groups = [a for a in dir(c) if not a.startswith("_") and a not in ("base", "set_token")]
    assert len(groups) == 19
    total = sum(len([m for m in dir(getattr(c, g)) if not m.startswith("_")])
                for g in groups)
    assert total == 98


def test_path_and_query_and_auth_header(calls):
    calls["resp"] = _FakeResp(200, [{"warehouse_code": "UC"}])
    c = CprsApiClient("http://localhost:3100", api_key="secret")
    out = c.clients.get_warehouses("client-123")
    method, url = calls["args"]
    assert method == "GET"
    assert url == "http://localhost:3100/api/v1/clients/client-123/warehouses"
    assert calls["kwargs"]["headers"]["x-api-key"] == "secret"
    assert out == [{"warehouse_code": "UC"}]


def test_query_params_drop_none(calls):
    calls["resp"] = _FakeResp(200, {"data": []})
    c = CprsApiClient("http://localhost:3100")
    c.evaluation.list(clientId="c1")
    # status/page/limit were None → dropped before the request
    assert calls["kwargs"]["params"] == {"clientId": "c1"}


def test_body_model_is_serialized(calls):
    calls["resp"] = _FakeResp(201, {"evaluationRunId": "r", "orderContextId": "o",
                                    "status": "ok",
                                    "summary": {"total": 0, "confirmed": 0,
                                                "pending_input": 0, "conflict": 0,
                                                "not_applicable": 0,
                                                "missing_mandatory_context": 0},
                                    "results": []})
    c = CprsApiClient("http://localhost:3100", api_key="k")
    run = c.evaluation.evaluate(M.CreateOrderContextDto(clientId="c1", channel="WHOLESALE"))
    assert calls["kwargs"]["json"] == {"clientId": "c1", "channel": "WHOLESALE"}
    assert isinstance(run, M.EvaluationRunResponseDto)   # typed response
    assert run.evaluationRunId == "r"


def test_body_dict_passthrough(calls):
    calls["resp"] = _FakeResp(200, {"warehouseCode": "UC"})
    c = CprsApiClient("http://localhost:3100")
    c.warehouse_lookup.resolve_post({"ship_to": "ROSS DC", "client_id": "c1"})
    assert calls["kwargs"]["json"] == {"ship_to": "ROSS DC", "client_id": "c1"}


def test_binary_endpoint_returns_bytes(calls):
    calls["resp"] = _FakeResp(200, body=None, content=b"PK\x03\x04xlsx")
    c = CprsApiClient("http://localhost:3100", api_key="k")
    data = c.export.download_excel("run-1")
    method, url = calls["args"]
    assert url.endswith("/export/runs/run-1/excel")
    assert isinstance(data, bytes) and data.startswith(b"PK")


def test_non_2xx_raises_cprserror(calls):
    calls["resp"] = _FakeResp(404, {"message": "client not found"})
    c = CprsApiClient("http://localhost:3100", api_key="k")
    with pytest.raises(CprsError) as ei:
        c.clients.find_one("nope")
    assert ei.value.status == 404 and "client not found" in ei.value.message


def test_network_error_raises_cprserror(calls):
    import requests
    calls["resp"] = requests.RequestException("connection refused")
    c = CprsApiClient("http://localhost:3100")
    with pytest.raises(CprsError) as ei:
        c.health.check()
    assert ei.value.status == 0


def test_bearer_token_attached(calls):
    calls["resp"] = _FakeResp(200, {"ok": True})
    c = CprsApiClient("http://localhost:3100")
    c.set_token("jwt-abc")
    c.auth.me()
    assert calls["kwargs"]["headers"]["Authorization"] == "Bearer jwt-abc"


def test_no_base_url_raises():
    c = CprsApiClient("")
    with pytest.raises(CprsError):
        c.health.check()
