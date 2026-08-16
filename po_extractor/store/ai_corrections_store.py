"""Corrections the AI has already made, kept so it is asked once.

When a value arrives written differently from what is on file — a colour the
factory retyped, an abbreviation, a Chinese name against an English one — the
AI is asked which known value it means. That answer is a durable fact about
the two spellings, not about the moment it was asked, so it is recorded here
and consulted first from then on.

This is deliberately NOT the same thing as ``ai_color_cache`` in
:mod:`po_extractor.lookups.color_ai_enhance`. That table caches a *question*:
its key includes the exact candidate list and the model, so the identical
colour re-asked against a different candidate set, or after switching model,
is a miss and costs another call. This table records the *conclusion* —
"DK Grey" means "Dark Grey" — and is reusable whatever the candidate set and
whichever model produced it.

Safety comes from the caller, not from this table: a stored correction is only
ever applied when its target is still one of the values actually on file for
the row being matched. A remembered answer can therefore never introduce a
value that isn't already there, which is the same limit the AI itself works
under. Corrections are scoped (normally by company) so one client's habits
don't leak into another's.

``source`` distinguishes ``ai`` from ``user``: a correction a person made by
hand outranks a guess, and is never overwritten by one.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from .base_store import BaseSQLiteStore

# Kinds in use. Free-form by design — a new caller adds a constant here rather
# than a new table.
KIND_SKY_EAST_COLOUR = "sky_east_colour"      # item identity on a re-imported contract
KIND_COLOUR_LOOKUP = "colour_lookup"          # order colour -> 大货进度表 colour

SOURCE_AI = "ai"
SOURCE_USER = "user"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_corrections (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT NOT NULL,
    scope        TEXT NOT NULL DEFAULT '',
    raw_key      TEXT NOT NULL,
    raw_value    TEXT NOT NULL,
    corrected    TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT 'ai',
    model        TEXT NOT NULL DEFAULT '',
    times_used   INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT,
    last_used_at TEXT,
    UNIQUE (kind, scope, raw_key)
);
CREATE INDEX IF NOT EXISTS idx_aicorr_lookup
    ON ai_corrections(kind, scope, raw_key);
"""


def normalise(value: str | None) -> str:
    """The form two spellings of one value share.

    Case and surrounding punctuation only — the same reduction the Sky East
    identity key uses, so a correction recorded for "(DK Grey)" is found for
    "dk grey". Word order is kept: it separates a body colour from a trim.
    """
    import re
    return " ".join(re.sub(r"[^0-9a-z一-鿿]+", " ",
                           (value or "").casefold()).split())


class AiCorrectionStore(BaseSQLiteStore):
    """Read/write access to the ai_corrections table."""

    _checked_paths: set[str] = set()

    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        if self.db_path in AiCorrectionStore._checked_paths:
            return
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
        AiCorrectionStore._checked_paths.add(self.db_path)

    # ── Read ────────────────────────────────────────────────────────────────

    def lookup(self, kind: str, scope: str, raw_value: str,
               candidates: list[str] | set[str] | None = None) -> str | None:
        """The known meaning of *raw_value*, or None.

        *candidates* is the guard: when given, a stored correction is returned
        only if it is still one of them. Without that check a correction
        learned on one order could put a colour onto a row that never had it.
        Matching against candidates is done on the normalised form, so the
        caller gets back the candidate spelled as it is on file.
        """
        raw_key = normalise(raw_value)
        if not raw_key:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, corrected FROM ai_corrections "
                "WHERE kind=? AND scope=? AND raw_key=?",
                (kind, scope or "", raw_key),
            ).fetchone()
            if row is None:
                return None
            corrected = row["corrected"]
            if candidates is not None:
                by_norm = {normalise(c): c for c in candidates}
                match = by_norm.get(normalise(corrected))
                if match is None:
                    return None          # no longer on file — don't apply it
                corrected = match
            conn.execute(
                "UPDATE ai_corrections SET times_used = times_used + 1, "
                "last_used_at = ? WHERE id = ?",
                (self._now(), row["id"]),
            )
        return corrected

    def list_all(self, kind: str | None = None) -> pd.DataFrame:
        """Every correction on file, newest first — for review in the UI."""
        cols = ["id", "kind", "scope", "raw_value", "corrected", "source",
                "model", "times_used", "created_at", "last_used_at"]
        sql = f"SELECT {', '.join(cols)} FROM ai_corrections"
        params: tuple = ()
        if kind:
            sql += " WHERE kind = ?"
            params = (kind,)
        sql += " ORDER BY COALESCE(last_used_at, created_at) DESC"
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return (pd.DataFrame([dict(r) for r in rows], columns=cols)
                if rows else pd.DataFrame(columns=cols))

    # ── Write ───────────────────────────────────────────────────────────────

    def record(self, kind: str, scope: str, raw_value: str, corrected: str,
               *, source: str = SOURCE_AI, model: str = "") -> bool:
        """Remember that *raw_value* means *corrected*. Returns True if stored.

        A correction a person made by hand is never replaced by one the AI
        guessed — the person had the order in front of them.
        """
        raw_key = normalise(raw_value)
        if not raw_key or not (corrected or "").strip():
            return False
        # Recording that a value means itself teaches nothing and would answer
        # for a spelling the plain comparison already handles.
        if raw_key == normalise(corrected):
            return False
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT source FROM ai_corrections "
                "WHERE kind=? AND scope=? AND raw_key=?",
                (kind, scope or "", raw_key),
            ).fetchone()
            if existing and existing["source"] == SOURCE_USER and source != SOURCE_USER:
                return False
            now = self._now()
            conn.execute(
                """INSERT INTO ai_corrections
                       (kind, scope, raw_key, raw_value, corrected, source,
                        model, times_used, created_at, last_used_at)
                   VALUES (?,?,?,?,?,?,?,0,?,NULL)
                   ON CONFLICT(kind, scope, raw_key) DO UPDATE SET
                       raw_value = excluded.raw_value,
                       corrected = excluded.corrected,
                       source    = excluded.source,
                       model     = excluded.model""",
                (kind, scope or "", raw_key, raw_value, corrected, source,
                 model, now),
            )
        return True

    def delete(self, correction_id: int) -> bool:
        """Forget one correction — the undo for a wrong AI answer."""
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM ai_corrections WHERE id = ?",
                               (int(correction_id),))
        return cur.rowcount > 0

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
