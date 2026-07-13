"""Tests for the 'Auto' extraction method — regex first, AI only when the
regex parse is low-confidence / unparsed."""
from __future__ import annotations

from po_extractor.models.po_data import POData, POMetadata, SizeRow
import ui.giii.extraction as ext


def _po(confidence=100, status="valid", rows=1):
    meta = POMetadata(po_number="PO1", style="ST1")
    meta.parse_confidence = confidence
    meta.validation_status = status
    size_rows = [SizeRow("PO1", "ST1", "BLACK", "M", 10, "U")] * rows
    return POData(metadata=meta, size_rows=size_rows)


def test_low_confidence_detection():
    assert not ext._regex_low_confidence(_po(100, "valid", 1))     # clean
    assert ext._regex_low_confidence(_po(100, "valid", 0))         # no rows
    assert ext._regex_low_confidence(_po(50, "warning", 1))        # low score
    assert ext._regex_low_confidence(_po(100, "exception", 1))     # not valid


def test_auto_uses_regex_when_clean(monkeypatch):
    calls = {"regex": 0, "ai": 0}
    monkeypatch.setattr(ext, "parse_pdf", lambda p: (calls.__setitem__("regex", calls["regex"]+1) or _po()))
    monkeypatch.setattr(ext, "parse_pdf_ai", lambda p, **k: (calls.__setitem__("ai", calls["ai"]+1) or _po()))
    po, used_ai = ext._parse_pdf_by_method("f.pdf", "auto", "sk-key", "deepseek-chat")
    assert used_ai is False and calls == {"regex": 1, "ai": 0}     # AI never called


def test_auto_falls_back_to_ai_when_low_confidence(monkeypatch):
    calls = {"regex": 0, "ai": 0}
    monkeypatch.setattr(ext, "parse_pdf", lambda p: (calls.__setitem__("regex", calls["regex"]+1) or _po(rows=0)))
    monkeypatch.setattr(ext, "parse_pdf_ai", lambda p, **k: (calls.__setitem__("ai", calls["ai"]+1) or _po()))
    po, used_ai = ext._parse_pdf_by_method("f.pdf", "auto", "sk-key", "deepseek-chat")
    assert used_ai is True and calls == {"regex": 1, "ai": 1}


def test_auto_without_key_stays_regex(monkeypatch):
    calls = {"regex": 0, "ai": 0}
    monkeypatch.setattr(ext, "parse_pdf", lambda p: (calls.__setitem__("regex", calls["regex"]+1) or _po(rows=0)))
    monkeypatch.setattr(ext, "parse_pdf_ai", lambda p, **k: (calls.__setitem__("ai", calls["ai"]+1) or _po()))
    po, used_ai = ext._parse_pdf_by_method("f.pdf", "auto", "", "deepseek-chat")
    assert used_ai is False and calls["ai"] == 0                   # no key → no AI


def test_auto_falls_back_when_regex_raises(monkeypatch):
    def _boom(p): raise ValueError("Unknown PO format")
    monkeypatch.setattr(ext, "parse_pdf", _boom)
    monkeypatch.setattr(ext, "parse_pdf_ai", lambda p, **k: _po())
    po, used_ai = ext._parse_pdf_by_method("f.pdf", "auto", "sk-key", "deepseek-chat")
    assert used_ai is True and po is not None


def test_deepseek_method_always_uses_ai(monkeypatch):
    calls = {"regex": 0, "ai": 0}
    monkeypatch.setattr(ext, "parse_pdf", lambda p: (calls.__setitem__("regex", calls["regex"]+1) or _po()))
    monkeypatch.setattr(ext, "parse_pdf_ai", lambda p, **k: (calls.__setitem__("ai", calls["ai"]+1) or _po()))
    _, used_ai = ext._parse_pdf_by_method("f.pdf", "deepseek", "sk-key", "deepseek-chat")
    assert used_ai is True and calls == {"regex": 0, "ai": 1}


def test_regex_method_never_uses_ai(monkeypatch):
    monkeypatch.setattr(ext, "parse_pdf", lambda p: _po(rows=0))   # even low-conf
    monkeypatch.setattr(ext, "parse_pdf_ai", lambda p, **k: (_ for _ in ()).throw(AssertionError("AI must not be called")))
    _, used_ai = ext._parse_pdf_by_method("f.pdf", "regex", "sk-key", "deepseek-chat")
    assert used_ai is False
