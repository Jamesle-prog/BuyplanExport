"""SQLite store for Sky East purchase contracts with merge/conflict detection."""
import sqlite3
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

import pandas as pd

from ..models.sky_east_data import SkyEastContract, SkyEastItem
from .base_store import BaseSQLiteStore
from ._sky_east_store_schema import _SCHEMA, _item_sizes_dict, _sizes_equal

DB_PATH_DEFAULT = Path(__file__).parent.parent.parent / "data" / "po_history.db"


class SkyEastStore(BaseSQLiteStore):
    def __init__(self, db_path: str | Path = DB_PATH_DEFAULT):
        self.db_path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
            # Migrate: add contract_no if missing (existing DBs)
            for tbl in ("sky_east_items", "sky_east_item_history"):
                cols = {r[1] for r in conn.execute(f"PRAGMA table_info({tbl})")}
                if "contract_no" not in cols:
                    conn.execute(f"ALTER TABLE {tbl} ADD COLUMN contract_no TEXT")

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

    def _archive_item(self, conn: sqlite3.Connection, existing: dict) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """INSERT INTO sky_east_item_history
               (pc_no, zalando_po, style, config_sku, article_name, brand,
                color_name, colour_code, launch_date, fabric_item_no, fabrication,
                contract_no,
                xs, s, m, l, xl, xxl, total_qty, fob_usd, total_cost_usd,
                ex_fty_date, picture_id, revision_reason, archived_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                existing.get("picture_id"), existing.get("revision_reason"), now,
            ),
        )

    def _insert_item(
        self, conn: sqlite3.Connection, item: SkyEastItem, revision_reason: str | None = None
    ) -> None:
        sizes = item.sizes or {}
        conn.execute(
            """INSERT OR REPLACE INTO sky_east_items
               (pc_no, zalando_po, style, config_sku, article_name, brand,
                color_name, colour_code, launch_date, fabric_item_no, fabrication,
                contract_no,
                xs, s, m, l, xl, xxl, total_qty, fob_usd, total_cost_usd,
                ex_fty_date, picture_id, revision_reason)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item.pc_no, item.zalando_po, item.style, item.config_sku,
                item.article_name, item.brand, item.color_name, item.colour_code,
                item.launch_date, item.fabric_item_no, item.fabrication,
                item.contract_no,
                sizes.get("XS", 0), sizes.get("S", 0), sizes.get("M", 0),
                sizes.get("L", 0), sizes.get("XL", 0), sizes.get("2XL", 0),
                item.total_qty, item.fob_usd, item.total_cost_usd,
                item.ex_fty_date, item.picture_id, revision_reason,
            ),
        )

    def _update_item(
        self, conn: sqlite3.Connection, item: SkyEastItem, revision_reason: str = "updated"
    ) -> None:
        sizes = item.sizes or {}
        conn.execute(
            """UPDATE sky_east_items SET
               config_sku=?, article_name=?, brand=?, colour_code=?, launch_date=?,
               fabric_item_no=?, fabrication=?, contract_no=?,
               xs=?, s=?, m=?, l=?, xl=?, xxl=?,
               total_qty=?, fob_usd=?, total_cost_usd=?,
               ex_fty_date=?, picture_id=?, revision_reason=?
               WHERE pc_no=? AND style=? AND color_name=? AND zalando_po=?""",
            (
                item.config_sku, item.article_name, item.brand, item.colour_code,
                item.launch_date, item.fabric_item_no, item.fabrication, item.contract_no,
                sizes.get("XS", 0), sizes.get("S", 0), sizes.get("M", 0),
                sizes.get("L", 0), sizes.get("XL", 0), sizes.get("2XL", 0),
                item.total_qty, item.fob_usd, item.total_cost_usd,
                item.ex_fty_date, item.picture_id, revision_reason,
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
          - Existing item, same size quantities → duplicate, skip
          - Existing item, different quantities → archive old, UPDATE

        Returns:
          {
            "pc_no": str,
            "new_items":      [(style, color, po), ...],
            "updated_items":  [(style, color, po, old_sizes, new_sizes), ...],
            "duplicate_items": [(style, color, po), ...],
          }
        """
        result: dict = {
            "pc_no": contract.pc_no,
            "new_items": [],
            "updated_items": [],
            "duplicate_items": [],
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
                existing = existing_map.get((item.style, item.color_name, item.zalando_po))

                if existing is None:
                    self._insert_item(conn, item, revision_reason=None)
                    result["new_items"].append((item.style, item.color_name, item.zalando_po))
                else:
                    old_sizes = _item_sizes_dict(existing)
                    new_sizes = item.sizes or {}

                    sizes_same = _sizes_equal(old_sizes, new_sizes)
                    old_qty  = existing.get("total_qty") or 0
                    new_qty  = item.total_qty or 0
                    old_fob  = existing.get("fob_usd") or 0.0
                    new_fob  = item.fob_usd or 0.0
                    qty_same = old_qty == new_qty
                    fob_same = abs(old_fob - new_fob) < 0.001

                    if sizes_same and qty_same and fob_same:
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

                    self._archive_item(conn, existing)
                    self._update_item(conn, item, revision_reason="updated")
                    result["updated_items"].append(
                        (item.style, item.color_name, item.zalando_po,
                         old_sizes, dict(new_sizes), changed)
                    )

        return result

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
            }
            for contract in group:
                r = self.save_contract_checked(contract)
                merged_result["new_items"].extend(r["new_items"])
                merged_result["updated_items"].extend(r["updated_items"])
                merged_result["duplicate_items"].extend(r["duplicate_items"])
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
