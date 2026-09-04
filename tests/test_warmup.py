"""Tests for ui.warmup — the start-up import pre-load."""
from __future__ import annotations

import sys
import threading
import time

from ui import warmup


def _wait_for_thread(name: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not any(t.name == name and t.is_alive() for t in threading.enumerate()):
            return
        time.sleep(0.05)


def test_warm_up_runs_once_per_process(monkeypatch):
    monkeypatch.setattr(warmup, "_started", False)
    starts: list[int] = []
    real_thread = threading.Thread

    class _Spy(real_thread):
        def start(self):
            starts.append(1)
            super().start()

    monkeypatch.setattr(warmup.threading, "Thread", _Spy)
    warmup.warm_up()
    warmup.warm_up()
    warmup.warm_up()
    _wait_for_thread("import-warmup")
    assert starts == [1], "second and third calls must be no-ops"


def test_warm_up_loads_the_heavy_modules_and_never_raises(monkeypatch):
    monkeypatch.setattr(warmup, "_started", False)
    warmup.warm_up()
    _wait_for_thread("import-warmup")
    for mod in ("bcrypt", "pandas", "openpyxl", "po_extractor.store", "ui.stores"):
        assert mod in sys.modules, f"{mod} should be imported by the warm-up"
    from auth import users
    assert users._dummy_hash is not None, "timing-pad hash should be primed"


def test_a_failing_step_does_not_stop_the_others():
    """An optional package missing must not cost the remaining warm-ups."""
    calls: list[str] = []

    def boom():
        calls.append("boom")
        raise RuntimeError("optional package missing")

    def ok():
        calls.append("ok")

    warmup._do_warm_up(steps=(boom, ok))     # must not raise
    assert calls == ["boom", "ok"]
