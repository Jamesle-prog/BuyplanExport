"""SQLite store for Sky East purchase contracts with merge/conflict detection."""
import re
import sqlite3
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

import pandas as pd

from ..models.sky_east_data import SkyEastContract, SkyEastItem
from .base_store import BaseSQLiteStore
from .ai_corrections_store import KIND_SKY_EAST_COLOUR
from ._sky_east_store_schema import _SCHEMA, _item_sizes_dict, _normalize_sizes, _sizes_equal

DB_PATH_DEFAULT = Path(__file__).parent.parent.parent / "data" / "po_history.db"

# Everything that isn't a letter, a digit or a CJK character. Colour names are
# typed by hand and the punctuation around them carries no meaning.
_COLOUR_NOISE = re.compile(r"[^0-9a-z一-鿿]+")


def colour_key(value: str | None) -> str:
    """The part of a colour name that actually identifies the colour.

    An item is identified by style + colour + client PO, and the colour is the
    only one of the three the factory retypes between revisions of the same
    contract. HHPPC053 arrived as ``(dark grey)`` on 2026-07-24 and ``Dark
    Grey`` on 2026-07-30 — the same garment, same PO, same 500 pcs. Compared as
    raw text those are different items, so the second upload inserted three new
    rows beside the three it should have updated and the buy plan printed every
    style twice.

    Case and punctuation are dropped; **word order is not**, since it separates
    a body colour from a trim ("black white" is not "white black"). That is
    enough to merge the retyped spellings without merging genuinely different
    colourways — ``(dark blue)(white)`` and ``(black)(white)`` stay distinct,
    as do NAVY/wine, BLACK/CREAM and CHOCOLATE BROWN/NAVY, all of which are
    real second colourways sharing a style and PO on other contracts.
    """
    return " ".join(_COLOUR_NOISE.sub(" ", (value or "").casefold()).split())


class SkyEastStore(BaseSQLiteStore):
    # Class-level set of db_paths that have already been schema-checked in
    # this process (same pattern as ProductionTrackingStore._checked_paths).
    # This store is constructed fresh on every Streamlit render, so without
    # the guard the executescript + PRAGMA table_info migration probes ran
    # on each construction instead of once per db_path.
    _checked_paths: set[str] = set()

    def __init__(self, db_path: str | Path = DB_PATH_DEFAULT):
        self.db_path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create tables / run column migrations — fast no-op after the first
        call per db_path within a process lifetime."""
        if self.db_path in SkyEastStore._checked_paths:
            return
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
            # Migrate: add contract_no if missing (existing DBs)
            for tbl in ("sky_east_items", "sky_east_item_history"):
                cols = {r[1] for r in conn.execute(f"PRAGMA table_info({tbl})")}
                if "contract_no" not in cols:
                    self._add_column_if_missing(conn, tbl, "contract_no", "TEXT")
            # Migrate: add progress_colors if missing (existing DBs, added after
            # sky_east_color_misses first shipped)
            _cm_cols = {r[1] for r in conn.execute("PRAGMA table_info(sky_east_color_misses)")}
            if "progress_colors" not in _cm_cols:
                self._add_column_if_missing(
                    conn, "sky_east_color_misses", "progress_colors", "TEXT"
                )
            # Migrate: add return_label if missing (existing DBs)
            for tbl in ("sky_east_items", "sky_east_item_history"):
                cols = {r[1] for r in conn.execute(f"PRAGMA table_info({tbl})")}
                if "return_label" not in cols:
                    self._add_column_if_missing(conn, tbl, "return_label", "TEXT DEFAULT 'NA'")
            self._migrate_colour_key(conn)
        SkyEastStore._checked_paths.add(self.db_path)

    def _migrate_colour_key(self, conn: sqlite3.Connection) -> None:
        """Populate colour_key and make the database enforce item identity.

        Identity is style + colour + client PO, with the colour compared
        normalised (:func:`colour_key`). That rule used to live only in Python,
        while the table's own UNIQUE was on the raw colour text — so nothing
        stopped a second row for an item whose colour had merely been retyped,
        which is how one contract came to print every style twice in its buy
        plan.

        Three steps, each a no-op once done:

        1. add the column and backfill it (the value can't be computed in SQL —
           it's a Python regex);
        2. archive and remove rows that duplicate another under the rule,
           keeping the newest, since a unique index cannot be built over them;
        3. create that index.

        Step 2 is the only one that removes anything, and everything it removes
        goes to sky_east_item_history first.
        """
        cols = {r[1] for r in conn.execute("PRAGMA table_info(sky_east_items)")}
        if "colour_key" not in cols:
            self._add_column_if_missing(conn, "sky_east_items", "colour_key", "TEXT")

        stale = conn.execute(
            "SELECT id, color_name FROM sky_east_items "
            "WHERE colour_key IS NULL OR colour_key = ''"
        ).fetchall()
        if stale:
            conn.executemany(
                "UPDATE sky_east_items SET colour_key=? WHERE id=?",
                [(colour_key(r["color_name"]), r["id"]) for r in stale],
            )

        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_sei_identity'"
        ).fetchone():
            return

        # Losers = every row but the newest for its identity. MAX(id) rather
        # than MIN: a later upload is the more current record, and it is the one
        # the merge path has been keeping since the fix.
        losers = conn.execute(
            """SELECT * FROM sky_east_items WHERE id NOT IN (
                   SELECT MAX(id) FROM sky_east_items
                   GROUP BY pc_no, style, colour_key, zalando_po)"""
        ).fetchall()
        for row in losers:
            existing = dict(row)
            existing["revision_reason"] = "superseded: same colour retyped"
            self._archive_item(conn, existing)
        if losers:
            conn.execute("DELETE FROM sky_east_items WHERE id IN (%s)"
                         % ",".join("?" * len(losers)),
                         [r["id"] for r in losers])

        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_sei_identity "
            "ON sky_east_items(pc_no, style, colour_key, zalando_po)"
        )

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _upsert_contract(self, conn: sqlite3.Connection, contract: SkyEastContract) -> None:
        """Insert or update contract header row (pc_no is the PK)."""
        conn.execute(
            """INSERT INTO sky_east_contracts
               (pc_no, pc_date, buyer, seller, currency, payment_terms, trade_term,
                source_file, extracted_at, processed_by, source_file_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(pc_no) DO UPDATE SET
                 pc_date         = excluded.pc_date,
                 buyer           = excluded.buyer,
                 seller          = excluded.seller,
                 currency        = excluded.currency,
                 payment_terms   = excluded.payment_terms,
                 trade_term      = excluded.trade_term,
                 source_file     = excluded.source_file,
                 extracted_at    = excluded.extracted_at,
                 processed_by    = excluded.processed_by,
                 source_file_hash= excluded.source_file_hash
            """,
            (
                contract.pc_no, contract.pc_date, contract.buyer, contract.seller,
                contract.currency, contract.payment_terms, contract.trade_term,
                contract.source_file, contract.extracted_at,
                contract.processed_by, contract.source_file_hash,
            ),
        )

    @staticmethod
    def _sizes_to_db_cols(sizes: dict) -> tuple:
        """Collapse a dynamic sizes dict into the 6 fixed DB columns.

        Any size key recognised by SIZE_TO_DB (e.g. "1X", "2X", "XXXL", "SM")
        is aggregated into the correct bucket.  Unknown keys are silently
        ignored so future parser additions never raise here.

        Returns: (xs, s, m, l, xl, xxl)
        """
        from ..parsers.sky_east_order import SIZE_TO_DB  # lazy import to avoid circular
        db: dict[str, int] = {"xs": 0, "s": 0, "m": 0, "l": 0, "xl": 0, "xxl": 0}
        for raw_key, qty in sizes.items():
            if not qty:
                continue
            bucket = SIZE_TO_DB.get(str(raw_key).strip().upper())
            if bucket:
                db[bucket] += int(qty)
        return db["xs"], db["s"], db["m"], db["l"], db["xl"], db["xxl"]

    # The columns sky_east_item_history keeps a copy of, in order. Named once so
    # the row-at-a-time and whole-PC archives cannot drift apart. colour_key is
    # absent deliberately — it is derived from color_name, which is here.
    _ARCHIVE_COLS = (
        "pc_no", "zalando_po", "style", "config_sku", "article_name", "brand",
        "color_name", "colour_code", "launch_date", "fabric_item_no",
        "fabrication", "contract_no", "xs", "s", "m", "l", "xl", "xxl",
        "total_qty", "fob_usd", "total_cost_usd", "ex_fty_date", "picture_id",
        "revision_reason", "return_label",
    )
    _ARCHIVE_DEFAULTS = {"xs": 0, "s": 0, "m": 0, "l": 0, "xl": 0, "xxl": 0,
                         "total_qty": 0, "fob_usd": 0.0, "total_cost_usd": 0.0,
                         "return_label": "NA"}

    @classmethod
    def _archive_insert(cls) -> str:
        return (f"INSERT INTO sky_east_item_history "
                f"({', '.join(cls._ARCHIVE_COLS)}, archived_at) ")

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _archive_item(self, conn: sqlite3.Connection, existing: dict) -> None:
        conn.execute(
            self._archive_insert()
            + f"VALUES ({','.join('?' * (len(self._ARCHIVE_COLS) + 1))})",
            tuple(existing.get(c, self._ARCHIVE_DEFAULTS.get(c))
                  for c in self._ARCHIVE_COLS) + (self._now(),),
        )

    def _archive_pc(self, conn: sqlite3.Connection, pc_no: str) -> None:
        """Archive every item of one PC No. in a single statement.

        Used by replace, which archives the whole contract unconditionally —
        reading the rows back into Python just to write them out one at a time
        would be N round trips for nothing.
        """
        cols = ", ".join(self._ARCHIVE_COLS)
        conn.execute(
            self._archive_insert()
            + f"SELECT {cols}, ? FROM sky_east_items WHERE pc_no=?",
            (self._now(), pc_no),
        )

    def _insert_item(
        self, conn: sqlite3.Connection, item: SkyEastItem, revision_reason: str | None = None
    ) -> None:
        sizes = item.sizes or {}
        xs, s, m, l, xl, xxl = self._sizes_to_db_cols(sizes)
        return conn.execute(
            """INSERT OR REPLACE INTO sky_east_items
               (pc_no, zalando_po, style, config_sku, article_name, brand,
                color_name, colour_key, colour_code, launch_date, fabric_item_no,
                fabrication, contract_no,
                xs, s, m, l, xl, xxl, total_qty, fob_usd, total_cost_usd,
                ex_fty_date, picture_id, revision_reason, return_label)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item.pc_no, item.zalando_po, item.style, item.config_sku,
                item.article_name, item.brand, item.color_name,
                colour_key(item.color_name), item.colour_code,
                item.launch_date, item.fabric_item_no, item.fabrication,
                item.contract_no,
                xs, s, m, l, xl, xxl,
                item.total_qty, item.fob_usd, item.total_cost_usd,
                item.ex_fty_date, item.picture_id, revision_reason,
                item.return_label,
            ),
        ).lastrowid

    @staticmethod
    def _refresh_parsed_fields(
        conn: sqlite3.Connection, existing: dict, item: SkyEastItem
    ) -> None:
        """Bring an otherwise-unchanged row's colour and Config SKU up to date.

        Used on the duplicate path, where the row must not be rewritten wholesale
        (see the caller). Both columns come from the parser and neither is
        editable in the app, so the newest file is authoritative — except that a
        blank incoming SKU never erases one already on file.
        """
        sets, vals = [], []
        if (existing.get("color_name") or "") != (item.color_name or ""):
            # colour_key goes with it — the two are one value, and the identity
            # index is on the derived half.
            sets += ["color_name=?", "colour_key=?"]
            vals += [item.color_name, colour_key(item.color_name)]
        if not (existing.get("config_sku") or "").strip() and (item.config_sku or "").strip():
            sets.append("config_sku=?")
            vals.append(item.config_sku)
        if not sets:
            return
        conn.execute(f"UPDATE sky_east_items SET {', '.join(sets)} WHERE id=?",
                     (*vals, existing["id"]))

    def _update_item(
        self, conn: sqlite3.Connection, item: SkyEastItem,
        revision_reason: str = "updated", row_id: int | None = None,
    ) -> None:
        """Overwrite one item row with *item*.

        Targets *row_id* when the caller has already matched the row, because
        the match is made on the normalised colour (see :func:`colour_key`) and
        the stored spelling may therefore differ from ``item.color_name`` — a
        WHERE on the raw colour would find nothing and silently update no rows.
        """
        sizes = item.sizes or {}
        xs, s, m, l, xl, xxl = self._sizes_to_db_cols(sizes)
        values = (
            item.config_sku, item.article_name, item.brand, item.colour_code,
            item.launch_date, item.fabric_item_no, item.fabrication, item.contract_no,
            xs, s, m, l, xl, xxl,
            item.total_qty, item.fob_usd, item.total_cost_usd,
            item.ex_fty_date, item.picture_id, revision_reason, item.return_label,
        )
        sets = """config_sku=?, article_name=?, brand=?, colour_code=?, launch_date=?,
                  fabric_item_no=?, fabrication=?, contract_no=?,
                  xs=?, s=?, m=?, l=?, xl=?, xxl=?,
                  total_qty=?, fob_usd=?, total_cost_usd=?,
                  ex_fty_date=?, picture_id=?, revision_reason=?, return_label=?"""
        if row_id is None:
            conn.execute(
                f"UPDATE sky_east_items SET {sets} "
                "WHERE pc_no=? AND style=? AND color_name=? AND zalando_po=?",
                values + (item.pc_no, item.style, item.color_name, item.zalando_po),
            )
            return
        # Adopt the newest file's spelling of the colour, so the buy plan shows
        # what the current contract says and the colour lookup gets the text it
        # can actually match. Neither unique constraint can object: the row was
        # matched on colour_key, so the new spelling normalises to the value
        # already stored there, and any row holding this exact spelling would
        # share that colour_key too — which idx_sei_identity forbids.
        conn.execute(f"UPDATE sky_east_items SET {sets}, color_name=?, colour_key=? "
                     "WHERE id=?",
                     values + (item.color_name, colour_key(item.color_name), row_id))

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _ai_settings() -> tuple[bool, str, str]:
        """(enabled, api_key, model) for AI colour matching — off unless the
        admin turned it on AND a DeepSeek key is configured. Any problem
        reading settings disables it; this must never block an import."""
        try:
            from . import get_app_settings_store
            from .app_settings_store import (
                KEY_DEEPSEEK_API_KEY, KEY_DEEPSEEK_MODEL, KEY_ITEM_COLOUR_AI_MATCH,
            )
            s = get_app_settings_store()
            on = s.get(KEY_ITEM_COLOUR_AI_MATCH, "false") == "true"
            api_key = (s.get(KEY_DEEPSEEK_API_KEY, "") or "").strip()
            model = s.get(KEY_DEEPSEEK_MODEL, "deepseek-chat") or "deepseek-chat"
            return (on and bool(api_key)), api_key, model
        except Exception:
            return False, "", ""

    @staticmethod
    def _ai_match(settings: tuple[bool, str, str], existing_map: dict,
                  item: SkyEastItem) -> tuple[dict, str] | None:
        """Last resort before an item is treated as new: ask the AI whether its
        colour is one of the colours already on file for this style and PO,
        written differently. Returns (row, the colour it was matched to), or
        None — the caller records it, so this only has to answer the question.

        :func:`colour_key` only sees through case and punctuation. It cannot
        see through an abbreviation ("DK Grey"), a typo ("Daek Blue"), or a
        switch of language (深灰色 / Dark Grey) — all of which the factory does,
        and each of which silently splits one item into two lines.

        Deliberately narrow. It runs only when normalisation has already
        failed, it is only ever offered the colours recorded against this exact
        style + client PO, and it can only return one of them verbatim — so the
        worst case is the duplicate line that would have appeared anyway, or
        two rows merged that should have stayed apart. It cannot invent a
        colour, touch any other field, or reach an item on another PO. Off by
        default; see KEY_ITEM_COLOUR_AI_MATCH.
        """
        if not (item.color_name or "").strip():
            return None
        # Only the colours on file for this exact style + PO are candidates.
        same_order = {
            (r.get("color_name") or ""): r
            for k, r in existing_map.items()
            if k[0] == item.style and k[2] == item.zalando_po
        }
        if not same_order:
            return None

        # 1. A correction already established for this spelling. Checked before
        #    the AI and regardless of whether AI matching is switched on: once
        #    "DK Grey" is known to mean "Dark Grey" that stays true, and
        #    re-asking would spend a call to be told the same thing. lookup()
        #    only answers with a colour still among these candidates, so a
        #    correction learned elsewhere can't put a colour on a row that
        #    never had it.
        #    Scope is deliberately blank rather than the PC No.: a spelling
        #    habit ("DK Grey", 深灰色) belongs to the factory, not to one
        #    contract, and a correction that only answered for the contract it
        #    was learned on would never save a single call.
        learned = SkyEastStore._corrections()
        if learned is not None:
            picked = learned.lookup(KIND_SKY_EAST_COLOUR, "",
                                    item.color_name, candidates=same_order)
            if picked:
                return same_order[picked], picked

        enabled, api_key, model = settings
        if not enabled:
            return None
        try:
            from ..lookups.color_ai_enhance import match_color_to_candidates
            picked = match_color_to_candidates(
                item.color_name, sorted(same_order), api_key, model)
        except Exception:
            return None
        if not picked or picked not in same_order:
            return None

        # 2. Remember it, so the next contract carrying this spelling is
        #    resolved from the database instead of another API call.
        if learned is not None:
            try:
                learned.record(KIND_SKY_EAST_COLOUR, "",
                               item.color_name, picked, model=model)
            except Exception:
                pass          # a failed write must never fail the import
        return same_order[picked], picked

    @staticmethod
    def _corrections():
        """The learned-corrections store, or None if it can't be opened —
        matching is expected to work without it."""
        try:
            from . import get_ai_correction_store
            return get_ai_correction_store()
        except Exception:
            return None

    def replace_contract(self, contract: SkyEastContract) -> dict:
        """Make the DB match *contract* exactly: every item currently on file
        for this PC No. that the contract no longer lists is archived and
        removed, and every item it does list is written fresh.

        The counterpart to :meth:`save_contract_checked`, which only ever adds
        and updates. Merging is right when a revision carries a subset of the
        order (the usual case) but cannot express a withdrawal — a style pulled
        from the contract, or a row that duplicated one already on file, stays
        forever. Replacing says the uploaded file is the whole truth.

        Everything removed goes to sky_east_item_history first, so a replace
        run in error is recoverable from the archive.

        Returns the same shape as save_contract_checked, plus
        ``removed_items``: [(style, color, po), ...].
        """
        result: dict = {
            "pc_no": contract.pc_no,
            "new_items": [],
            "updated_items": [],
            "duplicate_items": [],
            "pending_return_label": [],
            "ai_matched_items": [],
            "removed_items": [],
            "mode": "replace",
        }
        with self._conn() as conn:
            self._upsert_contract(conn, contract)

            # fabric_item_no and contract_no are maintained in the app, not in
            # the contract file — "the file is the whole truth" is about which
            # ITEMS exist, not about discarding work the file never carried.
            # Kept for any item still present, matched the same way the merge
            # path matches (see colour_key).
            # Grouped per key, not one row per key: a DB polluted by the
            # raw-colour identity bug holds several rows that now normalise
            # together, and each of those really is removed here. The newest
            # (last inserted) speaks for the group.
            self._archive_pc(conn, contract.pc_no)
            keep: dict[tuple, list[dict]] = {}
            for row in conn.execute(
                "SELECT * FROM sky_east_items WHERE pc_no=?", (contract.pc_no,)
            ).fetchall():
                existing = dict(row)
                keep.setdefault((existing["style"], existing["colour_key"],
                                 existing["zalando_po"]), []).append(existing)

            conn.execute("DELETE FROM sky_east_items WHERE pc_no=?", (contract.pc_no,))

            written: set[tuple] = set()
            for item in contract.items:
                key = (item.style, colour_key(item.color_name), item.zalando_po)
                group = keep.get(key)
                prior = group[-1] if group else None
                if prior:
                    if not (item.fabric_item_no or "").strip():
                        item.fabric_item_no = prior.get("fabric_item_no") or ""
                    if not (item.contract_no or "").strip():
                        item.contract_no = prior.get("contract_no") or ""
                self._insert_item(conn, item, revision_reason="replaced")
                written.add(key)
                result["new_items"].append(
                    (item.style, item.color_name, item.zalando_po))

            # Everything that was on file and did not survive: whole items the
            # new contract dropped, plus the older spellings of any item it
            # kept (the row it carried forward is the group's last).
            result["removed_items"] = [
                (r.get("style"), r.get("color_name"), r.get("zalando_po"))
                for k, group in keep.items()
                for r in (group if k not in written else group[:-1])
            ]
        return result

    def save_contract_checked(self, contract: SkyEastContract) -> dict:
        """
        Upsert a contract, merging items intelligently:
          - New item (not found by pc_no+style+color+po) → INSERT
          - Existing item, same size quantities, FOB, and Return Label → duplicate, skip
          - Existing item, Return Label unchanged but sizes/qty/FOB differ → archive old, UPDATE
          - Existing item, Return Label differs from what's on file → held back for
            confirmation, NOT written here (see ``pending_return_label`` below and
            :meth:`apply_pending_item`). A Return Label change always needs an
            explicit decision, regardless of whether sizes/qty/FOB also changed —
            unlike those fields, silently overwriting it risks losing a real
            business decision recorded on a previous upload.

        Returns:
          {
            "pc_no": str,
            "new_items":      [(style, color, po), ...],
            "updated_items":  [(style, color, po, old_sizes, new_sizes), ...],
            "duplicate_items": [(style, color, po), ...],
            # only when AI colour matching is on (KEY_ITEM_COLOUR_AI_MATCH) and
            # it resolved a colour plain normalisation could not:
            "ai_matched_items": [(style, matched_to, incoming_colour, po), ...],
            "pending_return_label": [
                {"pc_no", "style", "color_name", "zalando_po",
                 "old_return_label", "new_return_label", "changed", "item"}, ...
            ],
          }
        """
        result: dict = {
            "pc_no": contract.pc_no,
            "new_items": [],
            "updated_items": [],
            "duplicate_items": [],
            "pending_return_label": [],
            "ai_matched_items": [],
        }

        with self._conn() as conn:
            self._upsert_contract(conn, contract)

            # Batch-load all existing items for this PC in one query (avoids N+1)
            existing_rows = conn.execute(
                "SELECT * FROM sky_east_items WHERE pc_no=?", (contract.pc_no,)
            ).fetchall()
            # Keyed on the stored normalised colour — the same value
            # idx_sei_identity is unique on, so this map and the database agree
            # on what one item is by construction.
            existing_map: dict[tuple, dict] = {
                (r["style"], r["colour_key"], r["zalando_po"]): dict(r)
                for r in existing_rows
            }

            # Read once, not once per unmatched item: this opens its own
            # connections to the settings DB, and every item that turns out to
            # be new would otherwise pay for it even with the feature off.
            ai_settings = self._ai_settings()

            for item in contract.items:
                key = (item.style, colour_key(item.color_name), item.zalando_po)
                existing = existing_map.get(key)

                if existing is None:
                    matched = self._ai_match(ai_settings, existing_map, item)
                    if matched:
                        existing, picked = matched
                        result["ai_matched_items"].append(
                            (item.style, picked, item.color_name, item.zalando_po))

                if existing is None:
                    row_id = self._insert_item(conn, item, revision_reason=None)
                    result["new_items"].append((item.style, item.color_name, item.zalando_po))
                    # BUG fix: existing_map was built once before the loop and
                    # never updated, so a second item in this same contract
                    # sharing an identity would look up the stale pre-loop state
                    # instead of what this loop iteration just wrote, silently
                    # losing the first iteration's update or double-archiving.
                    # Re-read by rowid — cheaper than the four-column lookup,
                    # and unambiguous where that one was not.
                    existing_map[key] = dict(conn.execute(
                        "SELECT * FROM sky_east_items WHERE id=?", (row_id,),
                    ).fetchone())
                else:
                    old_sizes = _item_sizes_dict(existing)
                    # Normalise to canonical 6-key format so raw parser keys
                    # (e.g. "1X", "XXXL") compare correctly against DB data.
                    new_sizes = _normalize_sizes(item.sizes or {})

                    sizes_same = _sizes_equal(old_sizes, new_sizes)
                    old_qty  = existing.get("total_qty") or 0
                    new_qty  = item.total_qty or 0
                    old_fob  = existing.get("fob_usd") or 0.0
                    new_fob  = item.fob_usd or 0.0
                    qty_same = old_qty == new_qty
                    fob_same = abs(old_fob - new_fob) < 0.001
                    old_label = existing.get("return_label") or "NA"
                    new_label = item.return_label or "NA"
                    label_same = old_label == new_label

                    if sizes_same and qty_same and fob_same and label_same:
                        # Nothing was revised, so the row is NOT rewritten:
                        # _update_item would overwrite fabric_item_no and
                        # contract_no, which the user patches in the app and
                        # the file often leaves blank.
                        #
                        # Two parser-derived fields are still refreshed. The
                        # colour, because this branch is now reached across a
                        # retype (see colour_key) and the buy plan should print
                        # what the current contract says -- the older spelling
                        # is also the one the colour lookup fails on, which is
                        # where 未找到 came from. And the Config SKU when the
                        # stored one is blank and the new file has it: same
                        # revision of HHPPC053 that retyped the colours also
                        # filled in two SKUs that had been missing.
                        self._refresh_parsed_fields(conn, existing, item)
                        result["duplicate_items"].append(
                            (item.style, item.color_name, item.zalando_po)
                        )
                        continue

                    changed: dict = {}
                    if not sizes_same:
                        changed["sizes"] = (dict(old_sizes), dict(new_sizes))
                    if not qty_same:
                        changed["total_qty"] = (old_qty, new_qty)
                    if not fob_same:
                        changed["fob_usd"] = (round(old_fob, 4), round(new_fob, 4))

                    if not label_same:
                        # Held back -- NOT written in this pass. The caller
                        # (UI) shows old_return_label/new_return_label for
                        # review and calls apply_pending_item() once the
                        # user explicitly confirms replacing this record.
                        changed["return_label"] = (old_label, new_label)
                        result["pending_return_label"].append({
                            "pc_no": item.pc_no, "style": item.style,
                            "color_name": item.color_name, "zalando_po": item.zalando_po,
                            "old_return_label": old_label, "new_return_label": new_label,
                            "changed": changed, "item": item,
                        })
                        continue

                    self._archive_item(conn, existing)
                    self._update_item(conn, item, revision_reason="updated",
                                      row_id=existing["id"])
                    result["updated_items"].append(
                        (item.style, item.color_name, item.zalando_po,
                         old_sizes, dict(new_sizes), changed)
                    )
                    # Same fix as the insert branch above: refresh the map
                    # entry so a later duplicate-key item in this contract
                    # compares against the row we just wrote, not the
                    # pre-loop snapshot. By id — the colour spelling may have
                    # just been rewritten to the incoming one.
                    existing_map[key] = dict(conn.execute(
                        "SELECT * FROM sky_east_items WHERE id=?", (existing["id"],),
                    ).fetchone())

        return result

    def apply_pending_item(self, item: SkyEastItem) -> str:
        """Apply a user-confirmed replacement for an item that was held back
        by ``save_contract_checked`` for a Return Label conflict.

        Re-reads the current DB row at apply time (rather than trusting the
        snapshot the review table was built from) — archives it if present,
        then writes *item* in full (sizes/qty/FOB/Return Label together, not
        just the label) exactly as the automatic update path would have.

        Returns "inserted" or "updated" for caller-side reporting.
        """
        with self._conn() as conn:
            # Matched on the normalised colour for the same reason as
            # save_contract_checked — this row was held back by that pass, so it
            # has to resolve to the row that pass matched. A seek on
            # idx_sei_identity, which is exactly this key.
            existing = conn.execute(
                "SELECT * FROM sky_east_items "
                "WHERE pc_no=? AND style=? AND colour_key=? AND zalando_po=?",
                (item.pc_no, item.style, colour_key(item.color_name),
                 item.zalando_po),
            ).fetchone()
            if existing is None:
                self._insert_item(conn, item, revision_reason=None)
                return "inserted"
            self._archive_item(conn, dict(existing))
            self._update_item(conn, item, revision_reason="updated (return label confirmed)",
                              row_id=existing["id"])
            return "updated"

    def save_many_contracts_checked(self, contracts: list,
                                    mode: str = "merge") -> list:
        """
        Batch save multiple contracts.

        Contracts sharing the same pc_no are merged in order (later files
        can add new styles or update existing ones).

        *mode* ``"merge"`` (the default) adds and updates only; ``"replace"``
        makes each PC No. match its file exactly — see :meth:`replace_contract`.
        When several uploaded files share a PC No., only the FIRST replaces;
        the rest merge into it, so a replace never discards the file uploaded
        beside it in the same run.

        Returns a list of result dicts from save_contract_checked.
        """
        groups: OrderedDict[str, list] = OrderedDict()
        for contract in contracts:
            groups.setdefault(contract.pc_no, []).append(contract)

        results = []
        for pc_no, group in groups.items():
            merged_result: dict = {
                "pc_no": pc_no,
                "new_items": [],
                "updated_items": [],
                "duplicate_items": [],
                "pending_return_label": [],
                "ai_matched_items": [],
                "removed_items": [],
                "mode": mode,
            }
            for i, contract in enumerate(group):
                if mode == "replace" and i == 0:
                    r = self.replace_contract(contract)
                    merged_result["removed_items"].extend(r["removed_items"])
                else:
                    r = self.save_contract_checked(contract)
                merged_result["new_items"].extend(r["new_items"])
                merged_result["updated_items"].extend(r["updated_items"])
                merged_result["duplicate_items"].extend(r["duplicate_items"])
                merged_result["pending_return_label"].extend(r["pending_return_label"])
                merged_result["ai_matched_items"].extend(r.get("ai_matched_items", []))
            results.append(merged_result)

        return results

    def list_contracts(self) -> pd.DataFrame:
        """Return one row per pc_no with summary: total styles, total qty, date, buyer."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT c.pc_no, c.pc_date, c.buyer, c.seller, c.currency,
                          c.trade_term, c.source_file, c.extracted_at,
                          COUNT(DISTINCT i.style || '|' || i.color_name) AS total_styles,
                          COALESCE(SUM(i.total_qty), 0)                  AS total_qty
                   FROM sky_east_contracts c
                   LEFT JOIN sky_east_items i ON i.pc_no = c.pc_no
                   GROUP BY c.pc_no
                   ORDER BY c.extracted_at DESC"""
            ).fetchall()
        cols = [
            "pc_no", "pc_date", "buyer", "seller", "currency", "trade_term",
            "source_file", "extracted_at", "total_styles", "total_qty",
        ]
        return (
            pd.DataFrame([dict(r) for r in rows], columns=cols)
            if rows
            else pd.DataFrame(columns=cols)
        )

    def list_styles(self) -> list[str]:
        """Return a sorted list of distinct style names across all saved items."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT style FROM sky_east_items "
                "WHERE style IS NOT NULL AND style != '' ORDER BY style"
            ).fetchall()
        return [r[0] for r in rows]

    def list_items_by_styles(self, styles: list[str]) -> pd.DataFrame:
        """Return all items whose style is in *styles*, ordered by style then pc_no."""
        if not styles:
            return pd.DataFrame()
        ph = ",".join("?" * len(styles))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM sky_east_items WHERE style IN ({ph}) ORDER BY style, pc_no, id",
                styles,
            ).fetchall()
        return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()

    def list_items(self, pc_nos: list | None = None) -> pd.DataFrame:
        """Return all items, optionally filtered to the given pc_nos."""
        with self._conn() as conn:
            if pc_nos:
                ph = ",".join("?" * len(pc_nos))
                rows = conn.execute(
                    f"SELECT * FROM sky_east_items WHERE pc_no IN ({ph}) ORDER BY pc_no, id",
                    pc_nos,
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sky_east_items ORDER BY pc_no, id"
                ).fetchall()
        return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()

    def list_items_missing_fields(self) -> pd.DataFrame:
        """Return items missing fabric_item_no, contract_no, composition_en, or cuttable_width_cm."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT i.pc_no, i.zalando_po, i.style, i.color_name, i.brand,
                          i.fabric_item_no, i.contract_no, i.ex_fty_date, i.total_qty,
                          fm.composition_en, fm.cuttable_width_cm
                   FROM sky_east_items i
                   LEFT JOIN fabric_master fm ON TRIM(fm.quality_no) = TRIM(i.fabric_item_no)
                   WHERE COALESCE(TRIM(i.fabric_item_no), '')  = ''
                      OR COALESCE(TRIM(i.contract_no), '')     = ''
                      OR COALESCE(TRIM(fm.composition_en), '') = ''
                      OR COALESCE(fm.cuttable_width_cm, 0)    = 0
                   ORDER BY i.pc_no, i.style, i.color_name"""
            ).fetchall()
        cols = ["pc_no", "zalando_po", "style", "color_name", "brand",
                "fabric_item_no", "contract_no", "ex_fty_date", "total_qty",
                "composition_en", "cuttable_width_cm"]
        return (
            pd.DataFrame([dict(r) for r in rows], columns=cols)
            if rows
            else pd.DataFrame(columns=cols)
        )

    def update_item_fields(self, pc_no: str, style: str, color_name: str,
                           zalando_po: str, fabric_item_no: str, contract_no: str) -> bool:
        """Update fabric_item_no and contract_no for one item. Returns True if row was found."""
        with self._conn() as conn:
            cur = conn.execute(
                """UPDATE sky_east_items
                   SET fabric_item_no = ?, contract_no = ?
                   WHERE pc_no=? AND style=? AND color_name=? AND zalando_po=?""",
                (fabric_item_no.strip(), contract_no.strip(),
                 pc_no, style, color_name, zalando_po),
            )
        return cur.rowcount > 0

    def update_contract_no(self, pc_no: str, style: str, color_name: str,
                           zalando_po: str, contract_no: str) -> bool:
        """Update only contract_no — leave fabric_item_no untouched.

        BUG-35 fix: the patch-contract-numbers path called update_item_fields
        with an empty fabric_item_no, which clobbered any value already in the
        DB.  This dedicated method only touches the contract_no column.
        """
        with self._conn() as conn:
            cur = conn.execute(
                """UPDATE sky_east_items
                   SET contract_no = ?
                   WHERE pc_no=? AND style=? AND color_name=? AND zalando_po=?""",
                (contract_no.strip(), pc_no, style, color_name, zalando_po),
            )
        return cur.rowcount > 0

    def list_item_history(self, pc_no: str, style: str | None = None) -> pd.DataFrame:
        """Return archived versions for a given PC No., optionally filtered by style."""
        with self._conn() as conn:
            if style:
                rows = conn.execute(
                    """SELECT * FROM sky_east_item_history
                       WHERE pc_no=? AND style=?
                       ORDER BY archived_at DESC""",
                    (pc_no, style),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM sky_east_item_history
                       WHERE pc_no=?
                       ORDER BY archived_at DESC""",
                    (pc_no,),
                ).fetchall()
        return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()

    def delete_contracts(self, pc_nos: list) -> int:
        """Delete contracts and all their items. Returns number of contracts deleted."""
        if not pc_nos:
            return 0
        ph = ",".join("?" * len(pc_nos))
        with self._conn() as conn:
            n = conn.execute(
                f"DELETE FROM sky_east_contracts WHERE pc_no IN ({ph})", pc_nos
            ).rowcount
            conn.execute(f"DELETE FROM sky_east_items WHERE pc_no IN ({ph})", pc_nos)
            conn.execute(
                f"DELETE FROM sky_east_item_history WHERE pc_no IN ({ph})", pc_nos
            )
        return n

    def contract_count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM sky_east_contracts").fetchone()[0]

    # ------------------------------------------------------------------ #
    # Colour resolution misses — diagnostic log                            #
    # ------------------------------------------------------------------ #

    def log_color_miss(
        self, *, pc_no: str, contract_no: str, style: str, po_no: str,
        client_po_color: str, attempted_color: str, source: str,
        progress_colors: list[str] | None = None,
    ) -> None:
        """Record a colour that failed to resolve during buy plan generation.

        ``progress_colors`` is the distinct colour name(s) 大货进度表 actually
        has on file for this PC No./style (``None`` or ``[]`` when the
        internal DB was the selected source, or 大货进度表 has nothing for
        this PC/style at all) — stored comma-joined so the log mirrors the
        same "client colour vs. 大货进度表 colour" comparison already shown
        in the 未找到 cell's Excel comment.

        Deliberately append-only (no dedup) — one entry per (style, PO,
        colour) per generation run, so re-running after fixing the source
        data shows the failure count actually dropping over time.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        progress_colors_text = ", ".join(progress_colors) if progress_colors else ""
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO sky_east_color_misses
                   (pc_no, contract_no, style, po_no, client_po_color,
                    attempted_color, progress_colors, source, logged_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (pc_no, contract_no, style, po_no, client_po_color,
                 attempted_color, progress_colors_text, source, now),
            )

    def list_color_misses(self, limit: int = 500) -> pd.DataFrame:
        """Return the most recent colour-resolution misses, newest first."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM sky_east_color_misses ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        cols = ["id", "pc_no", "contract_no", "style", "po_no", "client_po_color",
                "attempted_color", "progress_colors", "source", "logged_at"]
        return pd.DataFrame([dict(r) for r in rows], columns=cols) if rows else pd.DataFrame(columns=cols)

    def clear_color_misses(self) -> int:
        """Delete all logged colour misses. Returns the number of rows removed."""
        with self._conn() as conn:
            n = conn.execute("SELECT COUNT(*) FROM sky_east_color_misses").fetchone()[0]
            conn.execute("DELETE FROM sky_east_color_misses")
        return n

    # ── Photo-issue log (missing pictures + unreadable files) ────────────────

    def replace_photo_issues(self, rows: list[dict]) -> None:
        """Replace the photo-issue log with the CURRENT generation's issues.

        *rows*: dicts with ``style``, ``issue`` ('missing' | 'error') and
        optional ``detail`` (source path for errors). Wholesale replace (one
        transaction) — a fixed photo disappears from the log on the next
        generation without manual clearing; see the schema note.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conn() as conn:
            conn.execute("DELETE FROM sky_east_photo_issues")
            if rows:
                conn.executemany(
                    "INSERT INTO sky_east_photo_issues (style, issue, detail, logged_at) "
                    "VALUES (?,?,?,?)",
                    [(r.get("style", ""), r.get("issue", "missing"),
                      r.get("detail", "") or "", now) for r in rows],
                )

    def list_photo_issues(self) -> list[dict]:
        """Photo issues from the most recent generation, missing first."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT style, issue, detail, logged_at FROM sky_east_photo_issues "
                "ORDER BY issue DESC, style"
            ).fetchall()
        return [dict(r) for r in rows]

    def clear_photo_issues(self) -> int:
        """Delete the photo-issue log. Returns rows removed."""
        with self._conn() as conn:
            n = conn.execute("SELECT COUNT(*) FROM sky_east_photo_issues").fetchone()[0]
            conn.execute("DELETE FROM sky_east_photo_issues")
        return n
