"""SQLite store for Sky East purchase contracts with merge/conflict detection."""
import sqlite3
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

import pandas as pd

from ..models.sky_east_data import SkyEastContract, SkyEastItem
from .base_store import BaseSQLiteStore
from ._sky_east_store_schema import _SCHEMA, _item_sizes_dict, _normalize_sizes, _sizes_equal

DB_PATH_DEFAULT = Path(__file__).parent.parent.parent / "data" / "po_history.db"


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
        SkyEastStore._checked_paths.add(self.db_path)

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

    def _archive_item(self, conn: sqlite3.Connection, existing: dict) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """INSERT INTO sky_east_item_history
               (pc_no, zalando_po, style, config_sku, article_name, brand,
                color_name, colour_code, launch_date, fabric_item_no, fabrication,
                contract_no,
                xs, s, m, l, xl, xxl, total_qty, fob_usd, total_cost_usd,
                ex_fty_date, picture_id, revision_reason, return_label, archived_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                existing.get("pc_no"), existing.get("zalando_po"), existing.get("style"),
                existing.get("config_sku"), existing.get("article_name"), existing.get("brand"),
                existing.get("color_name"), existing.get("colour_code"), existing.get("launch_date"),
                existing.get("fabric_item_no"), existing.get("fabrication"),
                existing.get("contract_no"),
                existing.get("xs", 0), existing.get("s", 0), existing.get("m", 0),
                existing.get("l", 0), existing.get("xl", 0), existing.get("xxl", 0),
                existing.get("total_qty", 0), existing.get("fob_usd", 0.0),
                existing.get("total_cost_usd", 0.0), existing.get("ex_fty_date"),
                existing.get("picture_id"), existing.get("revision_reason"),
                existing.get("return_label", "NA"), now,
            ),
        )

    def _insert_item(
        self, conn: sqlite3.Connection, item: SkyEastItem, revision_reason: str | None = None
    ) -> None:
        sizes = item.sizes or {}
        xs, s, m, l, xl, xxl = self._sizes_to_db_cols(sizes)
        conn.execute(
            """INSERT OR REPLACE INTO sky_east_items
               (pc_no, zalando_po, style, config_sku, article_name, brand,
                color_name, colour_code, launch_date, fabric_item_no, fabrication,
                contract_no,
                xs, s, m, l, xl, xxl, total_qty, fob_usd, total_cost_usd,
                ex_fty_date, picture_id, revision_reason, return_label)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item.pc_no, item.zalando_po, item.style, item.config_sku,
                item.article_name, item.brand, item.color_name, item.colour_code,
                item.launch_date, item.fabric_item_no, item.fabrication,
                item.contract_no,
                xs, s, m, l, xl, xxl,
                item.total_qty, item.fob_usd, item.total_cost_usd,
                item.ex_fty_date, item.picture_id, revision_reason,
                item.return_label,
            ),
        )

    def _update_item(
        self, conn: sqlite3.Connection, item: SkyEastItem, revision_reason: str = "updated"
    ) -> None:
        sizes = item.sizes or {}
        xs, s, m, l, xl, xxl = self._sizes_to_db_cols(sizes)
        conn.execute(
            """UPDATE sky_east_items SET
               config_sku=?, article_name=?, brand=?, colour_code=?, launch_date=?,
               fabric_item_no=?, fabrication=?, contract_no=?,
               xs=?, s=?, m=?, l=?, xl=?, xxl=?,
               total_qty=?, fob_usd=?, total_cost_usd=?,
               ex_fty_date=?, picture_id=?, revision_reason=?, return_label=?
               WHERE pc_no=? AND style=? AND color_name=? AND zalando_po=?""",
            (
                item.config_sku, item.article_name, item.brand, item.colour_code,
                item.launch_date, item.fabric_item_no, item.fabrication, item.contract_no,
                xs, s, m, l, xl, xxl,
                item.total_qty, item.fob_usd, item.total_cost_usd,
                item.ex_fty_date, item.picture_id, revision_reason, item.return_label,
                item.pc_no, item.style, item.color_name, item.zalando_po,
            ),
        )

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

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
        }

        with self._conn() as conn:
            self._upsert_contract(conn, contract)

            # Batch-load all existing items for this PC in one query (avoids N+1)
            existing_rows = conn.execute(
                "SELECT * FROM sky_east_items WHERE pc_no=?", (contract.pc_no,)
            ).fetchall()
            existing_map: dict[tuple, dict] = {
                (r["style"], r["color_name"], r["zalando_po"]): dict(r)
                for r in existing_rows
            }

            for item in contract.items:
                key = (item.style, item.color_name, item.zalando_po)
                existing = existing_map.get(key)

                if existing is None:
                    self._insert_item(conn, item, revision_reason=None)
                    result["new_items"].append((item.style, item.color_name, item.zalando_po))
                    # BUG fix: existing_map was built once before the loop and
                    # never updated, so a second item in this same contract
                    # sharing (style, color_name, zalando_po) — the table's
                    # UNIQUE key — would look up the stale pre-loop state
                    # instead of what this loop iteration just wrote,
                    # silently losing the first iteration's update or
                    # double-archiving. Re-read what we just inserted so the
                    # next iteration of a duplicate key sees it.
                    existing_map[key] = dict(conn.execute(
                        "SELECT * FROM sky_east_items "
                        "WHERE pc_no=? AND style=? AND color_name=? AND zalando_po=?",
                        (contract.pc_no, item.style, item.color_name, item.zalando_po),
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
                    self._update_item(conn, item, revision_reason="updated")
                    result["updated_items"].append(
                        (item.style, item.color_name, item.zalando_po,
                         old_sizes, dict(new_sizes), changed)
                    )
                    # Same fix as the insert branch above: refresh the map
                    # entry so a later duplicate-key item in this contract
                    # compares against the row we just wrote, not the
                    # pre-loop snapshot.
                    existing_map[key] = dict(conn.execute(
                        "SELECT * FROM sky_east_items "
                        "WHERE pc_no=? AND style=? AND color_name=? AND zalando_po=?",
                        (contract.pc_no, item.style, item.color_name, item.zalando_po),
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
            existing = conn.execute(
                "SELECT * FROM sky_east_items "
                "WHERE pc_no=? AND style=? AND color_name=? AND zalando_po=?",
                (item.pc_no, item.style, item.color_name, item.zalando_po),
            ).fetchone()
            if existing is None:
                self._insert_item(conn, item, revision_reason=None)
                return "inserted"
            self._archive_item(conn, dict(existing))
            self._update_item(conn, item, revision_reason="updated (return label confirmed)")
            return "updated"

    def save_many_contracts_checked(self, contracts: list) -> list:
        """
        Batch save multiple contracts.

        Contracts sharing the same pc_no are merged in order (later files
        can add new styles or update existing ones).

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
            }
            for contract in group:
                r = self.save_contract_checked(contract)
                merged_result["new_items"].extend(r["new_items"])
                merged_result["updated_items"].extend(r["updated_items"])
                merged_result["duplicate_items"].extend(r["duplicate_items"])
                merged_result["pending_return_label"].extend(r["pending_return_label"])
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
