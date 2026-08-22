"""The cut-plan output folder is remembered between sessions.

It is the same shared drive on every export, so retyping it each time was
friction. The rule that matters: a folder is only remembered once a file has
actually landed in it, otherwise the suggestions fill up with typos.
"""
from __future__ import annotations

import json

import pytest

import ui.shared as shared
from ui.cutting_plan._shared import CP_FOLDER_KIND, save_copy_to_folder
from ui.shared import recent_folders, remember_folder


@pytest.fixture(autouse=True)
def history_file(tmp_path, monkeypatch):
    """Point the persisted history at a scratch file."""
    path = tmp_path / "image_folder_history.json"
    monkeypatch.setattr(shared, "_HISTORY_FILE", path)
    return path


class _FakeSt:
    """Records the warning/success calls save_copy_to_folder makes."""

    def __init__(self):
        self.warnings: list[str] = []
        self.successes: list[str] = []

    def warning(self, msg):
        self.warnings.append(str(msg))

    def success(self, msg):
        self.successes.append(str(msg))


@pytest.fixture
def fake_st(monkeypatch):
    # The widgets live in ui.shared now; the cutting-plan module only binds
    # the history bucket.  Patch where the st calls actually happen.
    stub = _FakeSt()
    monkeypatch.setattr(shared, "st", stub)
    return stub


# ── The store ───────────────────────────────────────────────────────────────

def test_a_remembered_folder_survives_a_restart(history_file):
    remember_folder(CP_FOLDER_KIND, r"D:\CutPlans\2026")
    assert recent_folders(CP_FOLDER_KIND) == [r"D:\CutPlans\2026"]
    # Persisted, not just held in memory.
    assert json.loads(history_file.read_text(encoding="utf-8"))[CP_FOLDER_KIND]


def test_most_recent_folder_comes_first(history_file):
    for folder in (r"D:\A", r"D:\B", r"D:\C"):
        remember_folder(CP_FOLDER_KIND, folder)
    assert recent_folders(CP_FOLDER_KIND) == [r"D:\C", r"D:\B", r"D:\A"]


def test_reusing_a_folder_moves_it_up_without_duplicating(history_file):
    for folder in (r"D:\A", r"D:\B", r"D:\A"):
        remember_folder(CP_FOLDER_KIND, folder)
    assert recent_folders(CP_FOLDER_KIND) == [r"D:\A", r"D:\B"]


def test_blank_is_not_remembered(history_file):
    remember_folder(CP_FOLDER_KIND, "")
    remember_folder(CP_FOLDER_KIND, "   ")
    assert recent_folders(CP_FOLDER_KIND) == []


def test_history_is_per_kind(history_file):
    remember_folder(CP_FOLDER_KIND, r"D:\CutPlans")
    remember_folder("some_other_field", r"D:\Images")
    assert recent_folders(CP_FOLDER_KIND) == [r"D:\CutPlans"]
    assert recent_folders("some_other_field") == [r"D:\Images"]


def test_unknown_kind_is_empty_not_an_error(history_file):
    assert recent_folders("never_used") == []


# ── Only remembered on a real write ─────────────────────────────────────────

def test_folder_is_remembered_after_a_successful_save(tmp_path, fake_st,
                                                      history_file):
    save_copy_to_folder(b"xlsx-bytes", "plan.xlsx", str(tmp_path))
    assert (tmp_path / "plan.xlsx").read_bytes() == b"xlsx-bytes"
    assert recent_folders(CP_FOLDER_KIND) == [str(tmp_path)]
    assert fake_st.successes and not fake_st.warnings


def test_a_folder_that_does_not_exist_is_not_remembered(tmp_path, fake_st,
                                                        history_file):
    save_copy_to_folder(b"x", "plan.xlsx", str(tmp_path / "nope"))
    assert recent_folders(CP_FOLDER_KIND) == []
    assert fake_st.warnings and not fake_st.successes


def test_a_failed_write_is_not_remembered(tmp_path, fake_st, history_file,
                                          monkeypatch):
    import builtins

    real_open = builtins.open

    def refuse(path, *a, **kw):
        if "plan.xlsx" in str(path):
            raise OSError("disk full")
        return real_open(path, *a, **kw)

    monkeypatch.setattr(builtins, "open", refuse)
    save_copy_to_folder(b"x", "plan.xlsx", str(tmp_path))

    assert recent_folders(CP_FOLDER_KIND) == []
    assert fake_st.warnings and not fake_st.successes


def test_blank_folder_writes_nothing_and_remembers_nothing(fake_st,
                                                            history_file):
    save_copy_to_folder(b"x", "plan.xlsx", "")
    assert recent_folders(CP_FOLDER_KIND) == []
    assert not fake_st.warnings and not fake_st.successes


def test_filename_cannot_escape_the_chosen_folder(tmp_path, fake_st,
                                                   history_file):
    """A name carrying separators must not write outside the folder."""
    target = tmp_path / "out"
    target.mkdir()
    save_copy_to_folder(b"x", r"..\..\escaped.xlsx", str(target))
    assert (target / "escaped.xlsx").exists()
    assert not (tmp_path.parent / "escaped.xlsx").exists()


# ── Shared across every cut-plan folder field ───────────────────────────────

def test_all_cut_plan_folder_fields_share_one_history(tmp_path, fake_st,
                                                       history_file):
    """Saving from one screen pre-fills the field on the others — the folder
    is a property of the machine, not of the widget that asked for it."""
    save_copy_to_folder(b"x", "a.xlsx", str(tmp_path))
    # Whatever widget key a later field uses, it reads the same bucket.
    assert recent_folders(CP_FOLDER_KIND) == [str(tmp_path)]
