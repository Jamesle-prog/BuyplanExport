"""Fabric-parts and HHN-cache mixin for POStore."""
from __future__ import annotations

from datetime import datetime

import pandas as pd


class _FabricMixin:
    """Fabric parts and HHN cache operations for POStore.
    Requires self._conn() from BaseSQLiteStore.
    """

    # ------------------------------------------------------------------ #
    # Fabric parts — universal multi-fabric store                          #
    # ------------------------------------------------------------------ #

    def save_fabric_parts(
        self,
        source: str,
        style: str,
        parts: list,
        enrich_from_lookup=None,
    ) -> int:
        """
        Upsert fabric parts for a style from a given source pipeline.

        Parameters
        ----------
        source   : pipeline identifier — 'zalando', 'sky_east', 'giii', 'reference'
        style    : Main Supplier Config SKU / style number
        parts    : list of FabricPart objects
        enrich_from_lookup : optional FabricLookup instance; if provided and a
                             part has no composition, the lookup fills it in.

        Returns the number of rows upserted.
        """
        if not parts or not style:
            return 0

        from ..models.fabric_part import FabricPart

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        count = 0

        with self._conn() as conn:
            for p in parts:
                if not isinstance(p, FabricPart):
                    continue
                if p.is_empty():
                    continue

                comp   = p.composition
                weight = p.weight_gsm
                width  = p.width_cm

                # Optionally enrich from FabricLookup
                if enrich_from_lookup and p.hhn_no and not comp:
                    detail = enrich_from_lookup.get_fabric_detail(p.hhn_no) or {}
                    comp   = detail.get("composition", "") or comp
                    weight = detail.get("weight_gsm",  0)  or weight
                    width  = detail.get("width_cm",    0)  or width

                conn.execute(
                    """INSERT INTO style_fabric_parts
                       (source, style, combo_idx, seq, body_part, hhn_no, composition,
                        weight_gsm, width_cm, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(source, style, combo_idx, seq) DO UPDATE SET
                         body_part   = excluded.body_part,
                         hhn_no      = excluded.hhn_no,
                         composition = excluded.composition,
                         weight_gsm  = excluded.weight_gsm,
                         width_cm    = excluded.width_cm,
                         updated_at  = excluded.updated_at
                    """,
                    (source, style, p.combo_idx, p.seq, p.body_part, p.hhn_no,
                     comp, weight, width, now),
                )
                count += 1
        return count

    def save_fabric_parts_batch(
        self,
        source: str,
        style_parts_map: dict,
        enrich_from_lookup=None,
    ) -> int:
        """
        Batch-upsert fabric parts for all styles in a single DB transaction.

        Parameters
        ----------
        style_parts_map : {style: [FabricPart, ...], ...}

        Returns total rows upserted.
        """
        from ..models.fabric_part import FabricPart

        if not style_parts_map:
            return 0

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        count = 0

        with self._conn() as conn:
            for style, parts in style_parts_map.items():
                if not parts or not style:
                    continue
                for p in parts:
                    if not isinstance(p, FabricPart) or p.is_empty():
                        continue

                    comp   = p.composition
                    weight = p.weight_gsm
                    width  = p.width_cm

                    if enrich_from_lookup and p.hhn_no and not comp:
                        detail = enrich_from_lookup.get_fabric_detail(p.hhn_no) or {}
                        comp   = detail.get("composition", "") or comp
                        weight = detail.get("weight_gsm",  0)  or weight
                        width  = detail.get("width_cm",    0)  or width

                    conn.execute(
                        """INSERT INTO style_fabric_parts
                           (source, style, combo_idx, seq, body_part, hhn_no, composition,
                            weight_gsm, width_cm, updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(source, style, combo_idx, seq) DO UPDATE SET
                             body_part   = excluded.body_part,
                             hhn_no      = excluded.hhn_no,
                             composition = excluded.composition,
                             weight_gsm  = excluded.weight_gsm,
                             width_cm    = excluded.width_cm,
                             updated_at  = excluded.updated_at
                        """,
                        (source, style, p.combo_idx, p.seq, p.body_part, p.hhn_no,
                         comp, weight, width, now),
                    )
                    count += 1

        return count

    def load_fabric_parts(
        self,
        style: str | None = None,
        source: str | None = None,
    ) -> pd.DataFrame:
        """
        Return fabric parts as a DataFrame.

        Filter by style and/or source if provided.
        Columns: id, source, style, seq, body_part, hhn_no, composition,
                 weight_gsm, width_cm, updated_at
        """
        clauses: list[str] = []
        params:  list      = []
        if style:
            clauses.append("style = ?")
            params.append(style)
        if source:
            clauses.append("source = ?")
            params.append(source)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM style_fabric_parts {where} ORDER BY style, combo_idx, seq",
                params,
            ).fetchall()
        return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()

    def load_fabric_parts_for_styles(
        self,
        styles: list[str],
        source: str | None = None,
    ) -> dict:
        """
        Return {style: [FabricPart, ...]} for the given list of styles.

        Merges all sources unless source is specified.
        """
        from ..models.fabric_part import FabricPart

        if not styles:
            return {}

        ph = ",".join("?" * len(styles))
        params: list = list(styles)
        source_clause = ""
        if source:
            source_clause = " AND source = ?"
            params.append(source)

        with self._conn() as conn:
            rows = conn.execute(
                f"""SELECT style, combo_idx, seq, body_part, hhn_no, composition,
                           weight_gsm, width_cm
                    FROM style_fabric_parts
                    WHERE style IN ({ph}){source_clause}
                    ORDER BY style, combo_idx, seq""",
                params,
            ).fetchall()

        result: dict[str, list] = {}
        for r in rows:
            fp = FabricPart(
                combo_idx=r["combo_idx"] or 0,
                seq=r["seq"],
                body_part=r["body_part"] or "",
                hhn_no=r["hhn_no"] or "",
                composition=r["composition"] or "",
                weight_gsm=r["weight_gsm"] or 0,
                width_cm=r["width_cm"] or 0,
            )
            result.setdefault(r["style"], []).append(fp)
        return result

    def list_mapped_styles(self, source: str) -> set[str]:
        """Return the set of style names that have at least one fabric part for *source*."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT style FROM style_fabric_parts WHERE source=?", (source,)
            ).fetchall()
        return {r["style"] for r in rows}

    def delete_fabric_parts(self, source: str, styles: list[str] | None = None) -> int:
        """Delete fabric parts for a source, optionally filtered to specific styles."""
        with self._conn() as conn:
            if styles:
                ph = ",".join("?" * len(styles))
                n = conn.execute(
                    f"DELETE FROM style_fabric_parts WHERE source=? AND style IN ({ph})",
                    [source] + list(styles),
                ).rowcount
            else:
                n = conn.execute(
                    "DELETE FROM style_fabric_parts WHERE source=?", (source,)
                ).rowcount
        return n

    # ------------------------------------------------------------------ #
    # HHN fabric composition cache                                         #
    # ------------------------------------------------------------------ #

    def save_fabric_hhn_cache(self, records: dict) -> int:
        """
        Populate (or refresh) the HHN composition cache.

        Parameters
        ----------
        records : {hhn_no: {"composition": str, "weight_gsm": int, "width_cm": int}, ...}
                  Typically sourced from FabricLookup._by_fabric (the 洗标 file).

        Returns the number of rows upserted.
        """
        if not records:
            return 0
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = [
            (
                hhn_no,
                detail.get("composition", ""),
                detail.get("weight_gsm", 0) or 0,
                detail.get("width_cm",   0) or 0,
                now,
            )
            for hhn_no, detail in records.items()
            if hhn_no
        ]
        if not rows:
            return 0
        with self._conn() as conn:
            conn.executemany(
                """INSERT INTO fabric_hhn_cache
                   (hhn_no, composition, weight_gsm, width_cm, updated_at)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(hhn_no) DO UPDATE SET
                     composition = excluded.composition,
                     weight_gsm  = excluded.weight_gsm,
                     width_cm    = excluded.width_cm,
                     updated_at  = excluded.updated_at
                """,
                rows,
            )
        return len(rows)

    def get_fabric_by_hhn(self, hhn_no: str) -> dict | None:
        """
        Return {composition, weight_gsm, width_cm} for an HHN fabric number,
        or None if not found in the cache.
        """
        if not hhn_no:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT composition, weight_gsm, width_cm FROM fabric_hhn_cache WHERE hhn_no=?",
                (hhn_no.strip(),),
            ).fetchone()
        return dict(row) if row else None

    def list_fabric_hhn_cache(self) -> pd.DataFrame:
        """Return the full HHN composition cache as a DataFrame."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT hhn_no, composition, weight_gsm, width_cm, updated_at "
                "FROM fabric_hhn_cache ORDER BY hhn_no"
            ).fetchall()
        cols = ["hhn_no", "composition", "weight_gsm", "width_cm", "updated_at"]
        return (
            pd.DataFrame([dict(r) for r in rows], columns=cols)
            if rows else pd.DataFrame(columns=cols)
        )

    def fabric_hhn_cache_count(self) -> int:
        """Return the number of HHN codes in the cache."""
        with self._conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM fabric_hhn_cache"
            ).fetchone()[0]
