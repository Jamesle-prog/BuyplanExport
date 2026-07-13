"""Web scanner — pure lookup/verify/count logic + the Starlette HTTP layer."""
from __future__ import annotations

import pytest

from po_extractor.store.po_store import POStore
from po_extractor.models.po_data import POData, POMetadata, SizeRow
from web_scan import app as webapp
from web_scan.app import lookup, verify, count


@pytest.fixture()
def store(tmp_path):
    s = POStore(str(tmp_path / "t.db"))
    po1 = POData(metadata=POMetadata(
        po_number="PO1", style="ST1", company="GIII",
        destination_code="UC", ship_to="ROSS DC PERRIS CA", buyer="ROSS"),
        size_rows=[
            SizeRow("PO1", "ST1", "BLACK", "M", 100, "700948471565"),
            SizeRow("PO1", "ST1", "BLACK", "L", 50, "700948471534"),
        ])
    po2 = POData(metadata=POMetadata(po_number="PO2", style="ST2", company="GIII"),
                 size_rows=[SizeRow("PO2", "ST2", "RED", "S", 7, "700948471565")])
    s.save_many_checked([po1, po2])
    return s


# ── pure logic ────────────────────────────────────────────────────────────────

def test_lookup_matched_and_unmatched(store):
    d = lookup(store, "700948471534")
    assert d["matched"] and d["count"] == 1
    assert d["rows"][0]["po_number"] == "PO1" and d["rows"][0]["size"] == "L"
    assert d["rows"][0]["warehouse"] == "UC" and d["rows"][0]["units"] == 50
    assert lookup(store, "000000000000")["matched"] is False
    assert lookup(store, "")["matched"] is False


def test_lookup_reports_multi_po(store):
    d = lookup(store, "700948471565")     # on PO1 (M) and PO2 (S)
    assert d["count"] == 2
    assert {r["po_number"] for r in d["rows"]} == {"PO1", "PO2"}


def test_verify_belongs_wrong_and_missing(store):
    ok = verify(store, "PO1", "700948471534")
    assert ok["ok"] and ok["rows"][0]["po_number"] == "PO1"
    wrong = verify(store, "PO1", "700948471565")   # exists but also PO2
    assert wrong["ok"] is True                       # it IS on PO1 too
    only2 = verify(store, "PO1", "700948471565")
    assert "PO2" in only2["other_pos"]
    notonpo = verify(store, "PO2", "700948471534")   # 534 only on PO1
    assert notonpo["ok"] is False and notonpo["matched"] is True
    assert notonpo["other_pos"] == ["PO1"]
    missing = verify(store, "PO1", "999")
    assert missing["ok"] is False and missing["matched"] is False


def test_count_increments_and_context(store):
    assert count(store, "700948471565", 1)["qty"] == 1
    r = count(store, "700948471565", 1)
    assert r["qty"] == 2 and r["known"] is True
    assert r["context"]["style"] in ("ST1", "ST2")
    assert count(store, "700948471565", -1)["qty"] == 1
    # unknown UPC still counts, flagged not-known
    u = count(store, "ZZZ", 1)
    assert u["qty"] == 1 and u["known"] is False and u["context"] is None
    # magnitude clamped to one unit per scan
    assert count(store, "ZZZ", 9)["delta"] == 1


# ── HTTP layer ────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(store, monkeypatch):
    from starlette.testclient import TestClient
    monkeypatch.setattr(webapp, "get_po_store", lambda: store)
    monkeypatch.setenv("PO_SCAN_PASSWORD", "secret")
    monkeypatch.delenv("PO_SCAN_COMPANIES", raising=False)
    return TestClient(webapp.app)


def _login(client):
    r = client.post("/login", data={"password": "secret"}, follow_redirects=False)
    assert r.status_code == 302
    return r


def test_healthz_is_public(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.text == "ok"


def test_unauthenticated_api_is_401_and_page_redirects(client):
    assert client.post("/api/lookup", json={"upc": "700948471565"}).status_code == 401
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/login"


def test_wrong_password_rejected(client):
    r = client.post("/login", data={"password": "nope"}, follow_redirects=False)
    assert r.status_code == 401
    # no session cookie issued
    assert "po_scan_session" not in r.cookies


def test_login_then_lookup_verify_count(client):
    _login(client)                                  # cookie now in the client jar
    r = client.post("/api/lookup", json={"upc": "700948471534"})
    assert r.status_code == 200 and r.json()["rows"][0]["po_number"] == "PO1"

    v = client.post("/api/verify", json={"po": "PO2", "upc": "700948471534"}).json()
    assert v["ok"] is False and v["other_pos"] == ["PO1"]

    c = client.post("/api/count", json={"upc": "700948471565", "dir": "add"}).json()
    assert c["qty"] == 1
    st = client.get("/api/stocktake").json()
    assert st["total"] == 1 and any(row["upc"] == "700948471565" for row in st["rows"])

    cleared = client.post("/api/stocktake/clear", json={}).json()
    assert cleared["cleared"] >= 1
    assert client.get("/api/stocktake").json()["rows"] == []


def test_pos_endpoint_lists_pos(client):
    _login(client)
    pos = client.get("/api/pos").json()["pos"]
    assert "PO1" in pos and "PO2" in pos


def test_empty_upc_is_400(client):
    _login(client)
    assert client.post("/api/lookup", json={"upc": "  "}).status_code == 400
