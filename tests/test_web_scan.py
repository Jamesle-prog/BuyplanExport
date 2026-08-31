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


def test_count_attributes_the_adjustment_to_the_operator(store):
    """updated_by answers 'who touched this count last' -- overwritten each
    scan, not a history, same contract as any other 'last edited by' column."""
    count(store, "700948471565", 1, operator="Angel")
    row = [r for r in store.load_stocktake() if r["upc"] == "700948471565"][0]
    assert row["updated_by"] == "Angel"

    count(store, "700948471565", 1, operator="Bob")
    row = [r for r in store.load_stocktake() if r["upc"] == "700948471565"][0]
    assert row["updated_by"] == "Bob"          # overwritten, not appended


def test_count_with_no_operator_leaves_the_column_blank(store):
    """The Streamlit UPC Check tab shares this same store/table but has no
    operator concept -- must not crash or coerce a missing name into text
    like 'None'."""
    count(store, "700948471565", 1)
    row = [r for r in store.load_stocktake() if r["upc"] == "700948471565"][0]
    assert row["updated_by"] == ""


# ── HTTP layer ────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(store, monkeypatch):
    from starlette.testclient import TestClient
    monkeypatch.setattr(webapp, "get_po_store", lambda: store)
    monkeypatch.setenv("PO_SCAN_PASSWORD", "secret")
    monkeypatch.delenv("PO_SCAN_COMPANIES", raising=False)
    return TestClient(webapp.app)


def _login(client, name="Tester"):
    r = client.post("/login", data={"password": "secret", "name": name},
                    follow_redirects=False)
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
    r = client.post("/login", data={"password": "nope", "name": "Tester"},
                    follow_redirects=False)
    assert r.status_code == 401
    # no session cookie issued
    assert "po_scan_session" not in r.cookies
    assert "po_scan_name" not in r.cookies


# ── operator name: attribution, not a second credential ─────────────────────

def test_login_requires_a_name(client):
    """Correct password, blank name -- refused. There is no way to reach a
    session without one; a stocktake adjustment must always be attributable."""
    r = client.post("/login", data={"password": "secret", "name": "  "},
                    follow_redirects=False)
    assert r.status_code == 400
    assert "po_scan_session" not in r.cookies
    assert "po_scan_name" not in r.cookies
    assert "姓名" in r.text or "name" in r.text.lower()


def test_a_blank_name_does_not_count_toward_the_login_throttle(client):
    """Forgetting your name is a UX slip, not a password guess -- it must not
    burn one of the attempts that guards against brute-forcing the shared
    password."""
    webapp._LOGIN_FAILS.clear()
    for _ in range(webapp._MAX_FAILS):
        client.post("/login", data={"password": "secret", "name": ""},
                    follow_redirects=False)
    # every one of those was password-correct-name-blank; the throttle must
    # still be untouched, so a real login now succeeds rather than 429s
    r = _login(client)
    assert r.status_code == 302
    webapp._LOGIN_FAILS.clear()


def test_successful_login_sets_both_cookies(client):
    r = _login(client, name="Angel")
    assert r.cookies.get("po_scan_session")
    assert r.cookies.get("po_scan_name")


def test_scan_page_shows_the_operator_name(client):
    _login(client, name="Angel Chen")
    page = client.get("/", follow_redirects=False)
    assert page.status_code == 200
    assert "Angel Chen" in page.text


def test_scan_page_escapes_a_malicious_name(client):
    """The name is free text a person typed, not a fixed server string --
    unlike the login page's error slot, it must be escaped before it lands in
    the page every subsequent visitor of THIS session sees."""
    _login(client, name="<script>alert(1)</script>")
    page = client.get("/", follow_redirects=False)
    assert "<script>alert(1)</script>" not in page.text
    assert "&lt;script&gt;" in page.text


def test_wrong_password_retry_round_trips_the_name(client):
    """A typo'd password shouldn't also cost the operator their typed name."""
    r = client.post("/login", data={"password": "nope", "name": "Angel"},
                    follow_redirects=False)
    assert r.status_code == 401
    assert "Angel" in r.text


def test_wrong_password_retry_escapes_the_name_too(client):
    r = client.post("/login",
                    data={"password": "nope", "name": '"><script>x</script>'},
                    follow_redirects=False)
    assert "<script>x</script>" not in r.text


def test_a_chinese_name_logs_in_and_shows_on_the_scan_page(client):
    """The operators this page exists for type 姓名 in Chinese. The name rides
    in a cookie, and HTTP headers are latin-1 -- raw CJK in set_cookie raised
    UnicodeEncodeError, a 500 on the login of exactly the people meant to use
    it. (Found in the field, of course: every check before shipping used an
    ASCII name.) The cookie now carries the name percent-encoded."""
    r = _login(client, name="陈晓")
    assert r.status_code == 302
    # the cookie itself must be pure ASCII or a real browser may drop it
    assert r.headers["set-cookie"].encode("ascii")
    page = client.get("/", follow_redirects=False)
    assert page.status_code == 200
    assert "陈晓" in page.text


def test_a_chinese_name_attributes_the_stocktake_too(client):
    _login(client, name="陈晓")
    client.post("/api/count", json={"upc": "700948471565", "dir": "add"})
    row = [r for r in client.get("/api/stocktake").json()["rows"]
          if r["upc"] == "700948471565"][0]
    assert row["updated_by"] == "陈晓"


def test_a_chinese_name_survives_a_wrong_password_retry(client):
    r = client.post("/login", data={"password": "nope", "name": "陈晓"},
                    follow_redirects=False)
    assert r.status_code == 401
    assert "陈晓" in r.text


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


def test_count_delta_zero_is_noop(store):
    assert count(store, "700948471565", 1)["qty"] == 1
    r = count(store, "700948471565", 0)            # explicit 0 → no change
    assert r["qty"] == 1 and r["delta"] == 0


def test_login_is_rate_limited(client):
    webapp._LOGIN_FAILS.clear()
    for _ in range(webapp._MAX_FAILS):
        assert client.post("/login", data={"password": "wrong"},
                           follow_redirects=False).status_code == 401
    # further attempts are locked out, even with the CORRECT password
    r = client.post("/login", data={"password": "secret"}, follow_redirects=False)
    assert r.status_code == 429
    webapp._LOGIN_FAILS.clear()


def test_successful_login_clears_fail_counter(client):
    webapp._LOGIN_FAILS.clear()
    client.post("/login", data={"password": "wrong", "name": "Tester"},
               follow_redirects=False)
    _login(client)                                   # success (name + password)
    assert webapp._LOGIN_FAILS == {}


def test_a_correct_password_with_no_name_does_not_clear_the_fail_counter(client):
    """Getting the password right but forgetting your name is not a real
    login -- it must not quietly forgive a prior failed password guess."""
    webapp._LOGIN_FAILS.clear()
    client.post("/login", data={"password": "wrong", "name": "Tester"},
               follow_redirects=False)
    r = client.post("/login", data={"password": "secret"}, follow_redirects=False)
    assert r.status_code == 400
    assert webapp._LOGIN_FAILS != {}
    webapp._LOGIN_FAILS.clear()


# ── stocktake clear: the one write here worth an audit-trail entry ──────────

def test_clearing_stocktake_logs_who_cleared_it(client):
    from po_extractor.store import get_change_log_store

    _login(client, name="Angel")
    client.post("/api/count", json={"upc": "700948471565", "dir": "add"})
    cleared = client.post("/api/stocktake/clear", json={}).json()["cleared"]
    assert cleared >= 1

    df = get_change_log_store().list_recent()
    row = df[df["entity"] == "upc_stocktake"].iloc[0]
    assert row["username"] == "Angel"
    assert row["action"] == "delete"
    assert str(cleared) in row["detail"]


def test_clearing_an_already_empty_stocktake_logs_nothing(client):
    """Nothing removed, nothing to say -- same rule as every other audit hook
    in this app (see ChangeLogStore / SkyEastStore's own tests)."""
    from po_extractor.store import get_change_log_store

    _login(client, name="Angel")
    cleared = client.post("/api/stocktake/clear", json={}).json()["cleared"]
    assert cleared == 0
    assert get_change_log_store().list_recent().empty


def test_api_count_attributes_the_adjustment_to_the_logged_in_operator(client):
    _login(client, name="Angel")
    client.post("/api/count", json={"upc": "700948471565", "dir": "add"})
    row = [r for r in client.get("/api/stocktake").json()["rows"]
          if r["upc"] == "700948471565"][0]
    assert row["updated_by"] == "Angel"


# ── throttle identity behind the Cloudflare tunnel ──────────────────────────

class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeRequest:
    def __init__(self, peer, headers=None):
        self.client = _FakeClient(peer)
        self.headers = headers or {}


def test_throttle_uses_the_real_visitor_ip_behind_the_tunnel():
    """Via the tunnel every request's peer is loopback; without this, the
    per-IP throttle is one shared bucket and one person's typos lock the
    whole warehouse out."""
    r = _FakeRequest("127.0.0.1", {"CF-Connecting-IP": "203.0.113.9"})
    assert webapp._client_ip(r) == "203.0.113.9"


def test_a_lan_device_cannot_spoof_the_throttle_key():
    """CF-Connecting-IP is only believable when the request really came
    through the local tunnel. A LAN peer sending it directly must keep its
    own address, or it could rotate throttle buckets at will."""
    r = _FakeRequest("192.168.0.77", {"CF-Connecting-IP": "203.0.113.9"})
    assert webapp._client_ip(r) == "192.168.0.77"


def test_a_plain_lan_request_keys_on_its_own_address():
    assert webapp._client_ip(_FakeRequest("192.168.0.77")) == "192.168.0.77"
    assert webapp._client_ip(_FakeRequest("127.0.0.1")) == "127.0.0.1"
