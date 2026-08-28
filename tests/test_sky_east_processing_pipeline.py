"""End-to-end execution of the Sky East upload pipeline.

This is the test the v2.137.1 incident proved was missing. Between v2.132.0
and v2.137.0 EVERY Sky East upload failed instantly -- an i18n sweep added a
module-level `from ui.i18n import t` to ui/sky_east/processing.py while an
older, once-correct local re-import of the same name stayed behind in the
function's except block, making `t` local to the whole function and turning
the first t() read (the "Parsing {name}..." line) into an UnboundLocalError.

The 1672-test suite did not notice, because nothing executed
`_run_sky_east_processing`. Its feature tests covered the pure helper
(_se_distinct_brands, tests/test_sky_east_new_brand_prompt.py) on one side
and BoatSampleStore on the other -- both endpoints green, the 250 lines of
wiring between them never run. So these tests deliberately execute the REAL
function body, faking only the Streamlit chrome, the parse seam, and the
stores.

Fakes follow existing house precedent: _FakeStatus/_FakeUpload shapes from
tests/test_giii_tmpdir_cleanup.py, the plain-dict session_state from
tests/test_new_brand_boat_sample.py, and the contract builders from
tests/test_sky_east_store.py.
"""
from __future__ import annotations

import pytest

pytest.importorskip("streamlit", reason="streamlit not installed in this test env")

import ui.sky_east.processing as proc                      # noqa: E402
from auth.companies import COMPANY_SKY_EAST                # noqa: E402
from ui.session_keys import SK                             # noqa: E402


class _FakeStatus:
    """st.status returns a real status object only inside a script run."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def update(self, *a, **k):
        pass


class _FakeTracker:
    """ProgressTracker.__init__ calls st.progress/st.empty, which need a
    running Streamlit script -- so it is replaced wholesale."""

    def __init__(self, total):
        self.total = total

    def step(self, label: str = ""):
        pass

    def done(self):
        pass


class _FakeUpload:
    """The two attributes the pipeline touches on an uploaded file."""

    def __init__(self, name: str, data: bytes = b"not a real xlsx"):
        self.name = name
        self._data = data

    def getbuffer(self):
        return self._data


def _make_item(**over):
    from po_extractor.models.sky_east_data import SkyEastItem
    base = dict(
        pc_no="PC1", zalando_po="PO1", style="ST1", config_sku="SKU-1",
        article_name="A", brand="Anna Field", color_name="Blue",
        colour_code="Q11", launch_date="", fabric_item_no="HHP-JS-12345",
        fabrication="", contract_no="", sizes={"S": 1}, total_qty=1,
        fob_usd=1.0, total_cost_usd=1.0,
    )
    base.update(over)
    return SkyEastItem(**base)


def _make_contract(items, **over):
    from po_extractor.models.sky_east_data import SkyEastContract
    base = dict(pc_no="PC1", pc_date="2026-01-01", buyer="B", seller="S",
                currency="USD", payment_terms="TT", trade_term="FOB")
    base.update(over)
    return SkyEastContract(items=items, **base)


@pytest.fixture
def pipeline(monkeypatch, tmp_path):
    """Real _run_sky_east_processing, scratch stores, no Streamlit runtime.

    Returns (session, po_store, se_store, bs_store).
    """
    from po_extractor.store.boat_sample_store import BoatSampleStore
    from po_extractor.store.po_store import POStore
    from po_extractor.store.sky_east_store import SkyEastStore

    SkyEastStore._checked_paths.clear()
    po_store = POStore(str(tmp_path / "po.db"))
    se_store = SkyEastStore(str(tmp_path / "se.db"))
    bs_store = BoatSampleStore(str(tmp_path / "bs.db"))

    session: dict = {}

    # -- Streamlit chrome (module-level imports on the processing module) --
    monkeypatch.setattr(proc.st, "session_state", session)
    monkeypatch.setattr(proc.st, "status", lambda *a, **k: _FakeStatus())
    monkeypatch.setattr(proc, "ProgressTracker", _FakeTracker)

    # -- Store factories (module-level imports, processing.py:18) ----------
    monkeypatch.setattr(proc, "get_store", lambda: po_store)
    monkeypatch.setattr(proc, "get_sky_east_store", lambda: se_store)
    monkeypatch.setattr(proc, "get_boat_sample_store", lambda: bs_store)

    # -- Disk side effects -------------------------------------------------
    monkeypatch.setattr(proc, "save_images_to_disk", lambda *a, **k: None)

    # -- Call-time LOCAL imports: patch the SOURCE module, which the local
    #    import re-resolves on every call. Without these the run would read
    #    the real progress DB and prune the real extracted-images folder.
    monkeypatch.setattr("ui.sky_east._shared.get_progress_lookup",
                        lambda source=None: None)
    monkeypatch.setattr("ui.memory.prune_extracted_images", lambda *a, **k: 0)
    monkeypatch.setattr("ui.memory.trim_image_cache", lambda *a, **k: 0)

    return session, po_store, se_store, bs_store


def _patch_parse(monkeypatch, result):
    """Patch the parse seam at its SOURCE module.

    processing.py:303 does `from po_extractor.parsers import
    parse_sky_east_order as se_parse` INSIDE the function, so there is no
    `se_parse` attribute on the processing module to patch -- but the local
    import re-resolves the attribute off po_extractor.parsers on every call,
    which is what makes patching the source work.
    """
    if isinstance(result, BaseException):
        def _fake(path, processed_by=""):
            raise result
    else:
        def _fake(path, processed_by=""):
            return result
    monkeypatch.setattr("po_extractor.parsers.parse_sky_east_order", _fake)


def test_unseen_brand_run_completes_and_queues_the_prompt(pipeline, monkeypatch):
    """The regression test for the v2.137.1 crash.

    With the shadowing local `from ui.i18n import t` reintroduced into the
    outer except block, the UnboundLocalError fires on the first t() read
    and that except converts it into the failure-state contract (SE_RESULTS
    None + a "❌ ..." log line) -- so every assertion here trips and the
    captured log surfaces the real error text in the pytest output.
    """
    session, _po, se_store, _bs = pipeline
    _patch_parse(monkeypatch, _make_contract([_make_item(brand="Brand New GmbH")]))

    proc._run_sky_east_processing([_FakeUpload("order.xlsx")], None, None)

    log = "\n".join(session.get(SK.SE_LOG, []))
    assert session.get(SK.SE_RESULTS) is not None, (
        "pipeline fell into its outer except -- log:\n" + log)
    assert "❌" not in log, log
    # The inner try at the new-brand block would swallow a failure there.
    assert "New-brand shipping-sample check skipped" not in log, log

    assert session[SK.SE_NEW_BRAND_PENDING] == ["Brand New GmbH"]
    # Logged immediately after the once-crashing t() call.
    assert "1 new brand(s) need a shipping sample requirement" in log
    assert not se_store.list_items(["PC1"]).empty


def test_already_known_brand_queues_nothing(pipeline, monkeypatch):
    """A brand already carrying a 船样要求 must not raise the prompt."""
    session, _po, _se, bs_store = pipeline
    bs_store.upsert(COMPANY_SKY_EAST, "Brand New GmbH", "M码齐色2套")
    _patch_parse(monkeypatch, _make_contract([_make_item(brand="Brand New GmbH")]))

    proc._run_sky_east_processing([_FakeUpload("order.xlsx")], None, None)

    log = "\n".join(session.get(SK.SE_LOG, []))
    assert session.get(SK.SE_RESULTS) is not None, log
    assert SK.SE_NEW_BRAND_PENDING not in session
    assert "need a shipping sample requirement" not in log


def test_parser_failure_is_logged_and_queued_not_raised(pipeline, monkeypatch):
    """A corrupt file must not take the upload down: the per-file except
    logs it and queues it to the shared exception table, then the run ends
    cleanly with no results."""
    session, po_store, _se, _bs = pipeline
    _patch_parse(monkeypatch, ValueError("corrupt workbook"))

    proc._run_sky_east_processing([_FakeUpload("bad.xlsx")], None, None)

    log = "\n".join(session[SK.SE_LOG])
    assert "corrupt workbook" in log
    # The no-contracts early return writes SE_LOG only.
    assert SK.SE_RESULTS not in session

    exc_df = po_store.list_exceptions()
    assert len(exc_df) == 1
    assert "Sky East parse failed" in exc_df.iloc[0]["reason"]
