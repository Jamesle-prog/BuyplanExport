"""The shared UI components every view is expected to use.

``show_flash`` / ``set_flash`` replace six hand-rolled one-shot banners that
had three different storage shapes; ``delete_button`` replaces sixteen delete
buttons that chose their own glyph and emphasis; the folder helpers moved up
from the cutting-plan module so any export can offer "save a copy to…".
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

import ui.shared as shared
from ui.shared import DELETE_GLYPH, delete_button, set_flash, show_flash

REPO = Path(__file__).resolve().parent.parent


class _State(dict):
    def __getattr__(self, k):
        return self[k]

    def __setattr__(self, k, v):
        self[k] = v


class _St:
    """Records which banner was shown, and fakes the widgets delete_button uses."""

    def __init__(self, *, checkbox=False, button=False):
        self.session_state = _State()
        self.shown: list[tuple[str, str]] = []
        self.buttons: list[dict] = []
        self._checkbox = checkbox
        self._button = button

    def success(self, m): self.shown.append(("success", m))
    def info(self, m):    self.shown.append(("info", m))
    def warning(self, m): self.shown.append(("warning", m))
    def error(self, m):   self.shown.append(("error", m))

    def checkbox(self, label, key=None):
        return self._checkbox

    def button(self, label, **kw):
        self.buttons.append({"label": label, **kw})
        return self._button


@pytest.fixture
def st(monkeypatch):
    fake = _St()
    monkeypatch.setattr(shared, "st", fake)
    return fake


# ── show_flash ──────────────────────────────────────────────────────────────

def test_set_then_show_renders_once_and_clears(st):
    set_flash("k", "Saved.", "success")
    assert show_flash("k") == ("success", "Saved.")
    assert st.shown == [("success", "Saved.")]
    assert show_flash("k") is None          # one-shot: gone after rendering
    assert "k" not in st.session_state


def test_plain_string_uses_default_kind(st):
    st.session_state["k"] = "Record deleted."
    show_flash("k")
    assert st.shown == [("success", "Record deleted.")]


def test_plain_string_with_cross_prefix_is_an_error(st):
    """The mailbox check returns a string and signals failure with ❌."""
    st.session_state["k"] = "❌ IMAP login failed"
    show_flash("k", default_kind="info")
    assert st.shown == [("error", "❌ IMAP login failed")]


def test_dict_shape_renders_text_and_returns_payload(st):
    st.session_state["k"] = {"kind": "info", "text": "Submitted.", "col_map": {"a": 1}}
    flash = show_flash("k")
    assert st.shown == [("info", "Submitted.")]
    assert flash["col_map"] == {"a": 1}        # caller can render the rest


def test_unknown_kind_falls_back_to_info(st):
    st.session_state["k"] = ("celebrate", "done")
    show_flash("k")
    assert st.shown == [("info", "done")]


def test_nothing_queued_shows_nothing(st):
    assert show_flash("missing") is None
    assert st.shown == []


# ── delete_button ───────────────────────────────────────────────────────────

def test_delete_button_uses_the_one_glyph(st):
    delete_button("Delete user", key="d1")
    assert st.buttons[0]["label"] == f"{DELETE_GLYPH} Delete user"
    assert st.buttons[0]["type"] == "secondary"


def test_icon_only_when_label_is_empty(st):
    delete_button("", key="d1")
    assert st.buttons[0]["label"] == DELETE_GLYPH


def test_confirm_gates_the_button_until_ticked(monkeypatch):
    fake = _St(checkbox=False, button=True)
    monkeypatch.setattr(shared, "st", fake)
    assert delete_button("Delete plan", key="d1", confirm="Yes, delete it") is False
    assert fake.buttons[0]["disabled"] is True
    assert fake.buttons[0]["type"] == "secondary"

    armed = _St(checkbox=True, button=True)
    monkeypatch.setattr(shared, "st", armed)
    assert delete_button("Delete plan", key="d1", confirm="Yes, delete it") is True
    assert armed.buttons[0]["disabled"] is False
    assert armed.buttons[0]["type"] == "primary"      # red once deliberate


def test_delete_button_can_live_in_a_column(st):
    col = _St(button=True)
    assert delete_button("Remove", key="d1", container=col) is True
    assert col.buttons and not st.buttons


# ── Conventions enforced across ui/ ─────────────────────────────────────────

UI_FILES = [p for p in (REPO / "ui").rglob("*.py")
            if "__pycache__" not in p.parts and p.name != "changelog_view.py"]


def test_no_view_draws_its_own_delete_button():
    """Every 🗑 button goes through delete_button()."""
    bad = []
    for p in UI_FILES:
        if p.name == "shared.py":
            continue
        for i, line in enumerate(io.open(p, encoding="utf-8-sig").read().splitlines(), 1):
            if re.search(r"\.button\(.*\U0001F5D1", line):
                bad.append(f"{p.relative_to(REPO).as_posix()}:{i}")
    assert not bad, "use ui.shared.delete_button():\n  " + "\n  ".join(bad)


def test_download_buttons_use_one_download_glyph():
    """The download verb is ⬇️ — not bare ⬇, 💾 (that means save) or 📥
    (that names the Downloads section)."""
    bad = []
    pat = re.compile(r'download_button\(\s*(label=)?(t\()?f?["\'](⬇ |\U0001F4BE |\U0001F4E5 )')
    for p in UI_FILES:
        src = io.open(p, encoding="utf-8-sig").read()
        for m in pat.finditer(src):
            bad.append(f"{p.relative_to(REPO).as_posix()}: {m.group(0)[:40]!r}")
    assert not bad, "use ⬇️ on download buttons:\n  " + "\n  ".join(bad)


def test_no_view_pops_a_flash_by_hand():
    """One-shot banners go through show_flash()."""
    bad = []
    for p in UI_FILES:
        if p.name == "shared.py":
            continue
        src = io.open(p, encoding="utf-8-sig").read()
        for m in re.finditer(r"session_state\.pop\(SK\.[A-Z_]*FLASH", src):
            bad.append(p.relative_to(REPO).as_posix())
    assert not bad, "use ui.shared.show_flash(SK.X_FLASH):\n  " + "\n  ".join(bad)
