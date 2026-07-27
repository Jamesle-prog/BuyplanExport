"""SQLite store for uploaded cutting plans and the POs they cover.

Cut plans are produced outside the app (see
``po_extractor.parsers.cutting_plan``); this store keeps the parsed result,
the original file, and the PO links so any PO can answer "which cut plan
covers this, and does it cover the whole quantity?".
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from typing import Any

import pandas as pd

from .base_store import BaseSQLiteStore
from ._cutting_plan_schema import _CUTTING_PLAN_SCHEMA, SOURCE_SKY_EAST


class CuttingPlanStore(BaseSQLiteStore):
    """Read/write access to the cutting_plan_* tables."""

    # Schema-ensure runs once per db_path per process (same guard the other
    # stores use) so the uncached factory stays cheap.
    _checked_paths: set[str] = set()

    def __init__(self, db_path: str):
        self.db_path = db_path
        if db_path not in CuttingPlanStore._checked_paths:
            self._ensure_schema()
            CuttingPlanStore._checked_paths.add(db_path)

    def _ensure_schema(self) -> None:
        with self._conn() as conn:
            # Migrate BEFORE the schema script: that script indexes
            # cutting_plan_links(style), which fails on a pre-v2.106.0 DB
            # where CREATE TABLE IF NOT EXISTS is a no-op and the column
            # doesn't exist yet.  On a fresh DB the table isn't there and the
            # migration no-ops.
            self._migrate_links_add_style(conn)
            conn.executescript(_CUTTING_PLAN_SCHEMA)
            self._backfill_materials(conn)

    @staticmethod
    def _backfill_materials(conn) -> None:
        """Populate cutting_plan_materials for plans saved before it existed.

        The per-fabric figures were always in ``parsed_json``; this just
        unpacks them so already-uploaded plans show up in the per-fabric list
        instead of silently having no rows.
        """
        pending = conn.execute(
            """SELECT p.id, p.parsed_json FROM cutting_plans p
                WHERE NOT EXISTS (SELECT 1 FROM cutting_plan_materials m
                                   WHERE m.plan_id = p.id)"""
        ).fetchall()
        for row in pending:
            try:
                parsed = json.loads(row["parsed_json"] or "{}")
            except json.JSONDecodeError:
                continue
            if parsed.get("materials"):
                CuttingPlanStore._replace_materials(conn, int(row["id"]), parsed)

    @staticmethod
    def _migrate_links_add_style(conn) -> None:
        """Add ``style`` to cutting_plan_links (v2.106.0).

        A plain ADD COLUMN isn't enough: the uniqueness key has to widen to
        include the style, or two rows for different styles of the same PO
        collide.  SQLite can't alter a constraint, so the table is rebuilt.
        Existing rows get ``style=''`` — "the whole PO", which is what they
        meant before styles were recorded.
        """
        cols = {r[1] for r in conn.execute(
            "PRAGMA table_info(cutting_plan_links)")}
        if not cols or "style" in cols:
            return
        conn.executescript(
            """
            DROP INDEX IF EXISTS idx_cpl_plan;
            DROP INDEX IF EXISTS idx_cpl_pc;
            DROP INDEX IF EXISTS idx_cpl_po;
            ALTER TABLE cutting_plan_links RENAME TO _cpl_pre_style;

            CREATE TABLE cutting_plan_links (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id   INTEGER NOT NULL,
                source    TEXT NOT NULL DEFAULT 'sky_east',
                pc_no     TEXT DEFAULT '',
                po_no     TEXT DEFAULT '',
                style     TEXT DEFAULT '',
                linked_at TEXT,
                linked_by TEXT,
                UNIQUE(plan_id, source, pc_no, po_no, style)
            );
            INSERT INTO cutting_plan_links
                   (plan_id, source, pc_no, po_no, style, linked_at, linked_by)
            SELECT plan_id, source, pc_no, po_no, '', linked_at, linked_by
              FROM _cpl_pre_style;
            DROP TABLE _cpl_pre_style;

            CREATE INDEX IF NOT EXISTS idx_cpl_plan  ON cutting_plan_links(plan_id);
            CREATE INDEX IF NOT EXISTS idx_cpl_pc    ON cutting_plan_links(pc_no);
            CREATE INDEX IF NOT EXISTS idx_cpl_po    ON cutting_plan_links(po_no);
            CREATE INDEX IF NOT EXISTS idx_cpl_style ON cutting_plan_links(style);
            """
        )

    # ── Write ───────────────────────────────────────────────────────────────

    def save_plan(self, parsed: dict[str, Any], *, source_file: str,
                  file_bytes: bytes | None = None, uploaded_by: str = "",
                  notes: str = "",
                  links: list[dict] | None = None) -> int:
        """Insert a parsed plan (see ``parse_cut_plan``) and return its id.

        *links* are ``{"pc_no": ..., "po_no": ..., "source": ...}`` dicts; they
        can also be set later with :meth:`set_links`.
        """
        now = datetime.now().isoformat(timespec="seconds")
        summary = summarise_plan(parsed)
        blob = bytes(file_bytes) if file_bytes else None
        digest = hashlib.sha256(blob).hexdigest() if blob else ""

        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO cutting_plans
                      (plan_name, client, operator, plan_date, plan_time,
                       source_file, source_hash, plan_format, styles, colors,
                       materials, order_qty, cut_qty, total_tables,
                       total_markers, fabric_length_m, efficiency_pct, notes,
                       parsed_json, file_blob, uploaded_at, uploaded_by)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    summary["plan_name"] or (source_file or "cut plan"),
                    summary["client"], summary["operator"],
                    summary["plan_date"], summary["plan_time"],
                    source_file or "", digest,
                    parsed.get("format", "optitex"),
                    summary["styles"], summary["colors"], summary["materials"],
                    summary["order_qty"], summary["cut_qty"],
                    summary["total_tables"], summary["total_markers"],
                    summary["fabric_length_m"], summary["efficiency_pct"],
                    notes or "",
                    json.dumps(parsed, ensure_ascii=False),
                    blob, now, uploaded_by or "",
                ),
            )
            plan_id = int(cur.lastrowid)
            self._replace_materials(conn, plan_id, parsed)
            self._replace_demands(conn, plan_id, parsed)
            if links:
                self._replace_links(conn, plan_id, links, uploaded_by, now)
        return plan_id

    @staticmethod
    def _replace_materials(conn, plan_id: int, parsed: dict[str, Any]) -> None:
        conn.execute("DELETE FROM cutting_plan_materials WHERE plan_id=?",
                     (plan_id,))
        rows = []
        for seq, mat in enumerate(parsed.get("materials", [])):
            plies = sum(int(line.get("plies") or 0)
                        for spread in mat.get("spreads", [])
                        for line in spread.get("rows", []))
            rows.append((
                plan_id, seq,
                str(mat.get("material") or ""),
                mat.get("width_cm"), mat.get("length_cm"),
                str(mat.get("spreading") or ""),
                int(mat.get("n_markers") or 0),
                int(mat.get("total_tables") or 0),
                mat.get("min_plies"), mat.get("max_plies"),
                plies,
                int(mat.get("cut_qty") or 0),
                mat.get("fabric_length_m"),
                mat.get("total_efficiency_pct"),
                mat.get("total_cut_length_m"),
                mat.get("total_cost"),
            ))
        if rows:
            conn.executemany(
                """INSERT INTO cutting_plan_materials
                      (plan_id, seq, material, width_cm, length_cm, spreading,
                       n_markers, total_tables, min_plies, max_plies,
                       total_plies, cut_qty, fabric_length_m, efficiency_pct,
                       cut_length_m, cost)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                rows,
            )

    @staticmethod
    def _replace_demands(conn, plan_id: int, parsed: dict[str, Any]) -> None:
        conn.execute("DELETE FROM cutting_plan_demands WHERE plan_id=?",
                     (plan_id,))
        achieved = _achieved_by_cell(parsed)
        rows = [
            (plan_id, d.get("style", ""), d.get("color", ""), d.get("size", ""),
             int(d.get("qty") or 0),
             achieved.get((d.get("style", ""), d.get("color", ""),
                           d.get("size", "")), 0))
            for d in parsed.get("demands", [])
        ]
        # Cells that exist only in the Solution (cut but never ordered — an
        # overcut size) would otherwise vanish from the comparison.
        seen = {(r[1], r[2], r[3]) for r in rows}
        for key, qty in achieved.items():
            if key not in seen:
                rows.append((plan_id, key[0], key[1], key[2], 0, qty))
        if rows:
            conn.executemany(
                """INSERT INTO cutting_plan_demands
                      (plan_id, style, color, size, qty, cut_qty)
                   VALUES (?,?,?,?,?,?)""",
                rows,
            )

    @staticmethod
    def _replace_links(conn, plan_id: int, links: list[dict],
                       linked_by: str, now: str) -> None:
        conn.execute("DELETE FROM cutting_plan_links WHERE plan_id=?",
                     (plan_id,))
        rows, seen = [], set()
        for ln in links:
            pc = str(ln.get("pc_no") or "").strip()
            po = str(ln.get("po_no") or "").strip()
            style = str(ln.get("style") or "").strip()
            src = str(ln.get("source") or SOURCE_SKY_EAST).strip()
            if not pc and not po:
                continue
            key = (src, pc, po, style)
            if key in seen:
                continue
            seen.add(key)
            rows.append((plan_id, src, pc, po, style, now, linked_by or ""))
        if rows:
            conn.executemany(
                """INSERT OR IGNORE INTO cutting_plan_links
                      (plan_id, source, pc_no, po_no, style, linked_at,
                       linked_by)
                   VALUES (?,?,?,?,?,?,?)""",
                rows,
            )

    def set_links(self, plan_id: int, links: list[dict],
                  linked_by: str = "") -> None:
        """Replace *all* PO links of a plan (the link editor saves at once)."""
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as conn:
            self._replace_links(conn, plan_id, links, linked_by, now)

    def update_notes(self, plan_id: int, notes: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("UPDATE cutting_plans SET notes=? WHERE id=?",
                               (notes or "", plan_id))
        return cur.rowcount > 0

    def delete_plan(self, plan_id: int) -> bool:
        with self._conn() as conn:
            conn.execute("DELETE FROM cutting_plan_links WHERE plan_id=?",
                         (plan_id,))
            conn.execute("DELETE FROM cutting_plan_materials WHERE plan_id=?",
                         (plan_id,))
            conn.execute("DELETE FROM cutting_plan_demands WHERE plan_id=?",
                         (plan_id,))
            cur = conn.execute("DELETE FROM cutting_plans WHERE id=?",
                               (plan_id,))
        return cur.rowcount > 0

    # ── Read ────────────────────────────────────────────────────────────────

    _LIST_COLS = (
        "id, plan_name, client, operator, plan_date, styles, colors, "
        "materials, order_qty, cut_qty, total_tables, total_markers, "
        "fabric_length_m, efficiency_pct, source_file, notes, "
        "uploaded_at, uploaded_by"
    )

    @classmethod
    def _list_cols(cls, alias: str = "") -> str:
        """``_LIST_COLS`` qualified with a table alias.

        Required in any joined query: cutting_plan_materials also has ``id``
        and ``total_tables``, so the bare list is ambiguous there.
        """
        names = [c.strip() for c in cls._LIST_COLS.split(",")]
        if not alias:
            return ", ".join(names)
        return ", ".join(f"{alias}.{n} AS {n}" for n in names)

    def list_plans(self) -> pd.DataFrame:
        """One row per plan, newest first, with its PO and style links.

        ``linked_pos`` counts distinct PO numbers, not link rows — one PO
        linked for three styles is still one PO.  ``linked_styles`` lists the
        PO-side style codes the plan covers, which is what tells you at a
        glance whether a plan is for the whole PO or part of it.
        """
        with self._conn() as conn:
            rows = conn.execute(
                f"""SELECT {self._LIST_COLS},
                       (SELECT COUNT(DISTINCT l.pc_no || '|' || l.po_no)
                          FROM cutting_plan_links l
                         WHERE l.plan_id = p.id) AS linked_pos,
                       (SELECT GROUP_CONCAT(s, ', ') FROM (
                            SELECT DISTINCT l2.style AS s
                              FROM cutting_plan_links l2
                             WHERE l2.plan_id = p.id AND l2.style <> ''
                             ORDER BY l2.style)) AS linked_styles
                    FROM cutting_plans p
                    ORDER BY datetime(uploaded_at) DESC, id DESC"""
            ).fetchall()
        cols = ([c.strip() for c in self._LIST_COLS.split(",")]
                + ["linked_pos", "linked_styles"])
        if not rows:
            return pd.DataFrame(columns=cols)
        df = pd.DataFrame([dict(r) for r in rows])
        df["linked_styles"] = df["linked_styles"].fillna("")
        return df

    def po_qty_by_plan(self, source: str = SOURCE_SKY_EAST) -> dict[int, int]:
        """Ordered quantity from the **PO side**, per plan.

        The plan file states what the cutting room was told to cut; this is
        what the PO actually ordered for the linked POs and styles.  Seeing
        both is the point — they should agree, and a gap means the plan was
        built against a superseded quantity or linked to the wrong styles.

        Items are counted once per plan (DISTINCT on the item id) so a plan
        holding both a whole-PO link and a per-style link can't double-count.
        Returns {} when the PO tables aren't present in this database.
        """
        sql = """
            SELECT plan_id, SUM(total_qty) AS po_qty FROM (
                SELECT DISTINCT l.plan_id AS plan_id,
                                i.id      AS item_id,
                                i.total_qty AS total_qty
                  FROM cutting_plan_links l
                  JOIN sky_east_items i
                    ON TRIM(i.pc_no) = TRIM(l.pc_no)
                   AND (l.po_no = '' OR TRIM(i.zalando_po) = TRIM(l.po_no))
                   AND (l.style = '' OR TRIM(i.style)      = TRIM(l.style))
                 WHERE l.source = ?
            ) GROUP BY plan_id
        """
        try:
            with self._conn() as conn:
                rows = conn.execute(sql, (source,)).fetchall()
        except sqlite3.OperationalError:
            return {}          # no sky_east_items in this DB (e.g. a test DB)
        return {int(r["plan_id"]): int(r["po_qty"] or 0) for r in rows}

    def list_plan_materials(self, plan_id: int) -> pd.DataFrame:
        """One row per fabric for a single plan, in the plan's own order.

        Adds the two consumption figures: metres per unit (per garment) and
        metres per piece.  See :func:`consumption` for why both exist.
        """
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT m.material, m.width_cm, m.spreading, m.n_markers,
                          m.total_tables, m.total_plies, m.cut_qty,
                          m.fabric_length_m, m.efficiency_pct, m.cut_length_m,
                          m.cost, p.cut_qty AS unit_qty
                     FROM cutting_plan_materials m
                     JOIN cutting_plans p ON p.id = m.plan_id
                    WHERE m.plan_id=? ORDER BY m.seq, m.id""",
                (plan_id,)).fetchall()
        cols = ["material", "width_cm", "spreading", "n_markers",
                "total_tables", "total_plies", "cut_qty", "fabric_length_m",
                "m_per_unit", "m_per_piece", "efficiency_pct", "cut_length_m",
                "cost"]
        if not rows:
            return pd.DataFrame(columns=cols)
        df = pd.DataFrame([dict(r) for r in rows])
        df["m_per_unit"] = [consumption(m, q) for m, q in
                            zip(df["fabric_length_m"], df["unit_qty"])]
        df["m_per_piece"] = [consumption(m, q) for m, q in
                             zip(df["fabric_length_m"], df["cut_qty"])]
        return df[cols]

    def list_plans_by_material(self) -> pd.DataFrame:
        """The plan list expanded to one row per fabric.

        Plan-level columns repeat on each of a plan's fabric rows; the
        fabric-level ones (width, markers, tables, plies, metres, efficiency,
        cost) are that fabric's own.  ``po_qty`` is the linked PO's ordered
        quantity, alongside the plan's own ``order_qty``.  A plan whose
        materials couldn't be read still appears, with empty fabric columns.
        """
        with self._conn() as conn:
            rows = conn.execute(
                f"""SELECT {self._list_cols('p')},
                       m.material, m.width_cm, m.spreading, m.n_markers,
                       m.total_tables AS mat_tables,
                       m.total_plies, m.cut_qty AS mat_cut_qty,
                       m.fabric_length_m AS mat_fabric_m,
                       m.efficiency_pct  AS mat_efficiency_pct,
                       m.cut_length_m, m.cost, m.seq,
                       (SELECT COUNT(DISTINCT l.pc_no || '|' || l.po_no)
                          FROM cutting_plan_links l
                         WHERE l.plan_id = p.id) AS linked_pos,
                       (SELECT GROUP_CONCAT(s, ', ') FROM (
                            SELECT DISTINCT l2.style AS s
                              FROM cutting_plan_links l2
                             WHERE l2.plan_id = p.id AND l2.style <> ''
                             ORDER BY l2.style)) AS linked_styles
                    FROM cutting_plans p
                    LEFT JOIN cutting_plan_materials m ON m.plan_id = p.id
                    ORDER BY datetime(p.uploaded_at) DESC, p.id DESC,
                             m.seq, m.id"""
            ).fetchall()
        cols = ([c.strip() for c in self._LIST_COLS.split(",")]
                + ["material", "width_cm", "spreading", "n_markers",
                   "mat_tables", "total_plies", "mat_cut_qty",
                   "mat_fabric_m", "m_per_unit", "m_per_piece",
                   "mat_efficiency_pct", "cut_length_m", "cost", "seq",
                   "linked_pos", "linked_styles", "po_qty", "diff_pct"])
        if not rows:
            return pd.DataFrame(columns=cols)
        df = pd.DataFrame([dict(r) for r in rows])
        df["linked_styles"] = df["linked_styles"].fillna("")
        df["material"] = df["material"].fillna("")
        po_qty = self.po_qty_by_plan()
        df["po_qty"] = df["id"].map(po_qty).fillna(0).astype(int)
        df["diff_pct"] = [
            cut_vs_po_pct(po, cut)
            for po, cut in zip(df["po_qty"], df["cut_qty"])
        ]
        df["m_per_unit"] = [consumption(m, q) for m, q in
                            zip(df["mat_fabric_m"], df["cut_qty"])]
        df["m_per_piece"] = [consumption(m, q) for m, q in
                             zip(df["mat_fabric_m"], df["mat_cut_qty"])]
        return df

    def get_plan(self, plan_id: int) -> dict[str, Any] | None:
        """Full plan record: summary columns + parsed structure + links."""
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT {self._LIST_COLS}, parsed_json, plan_time, "
                "source_hash, plan_format FROM cutting_plans WHERE id=?",
                (plan_id,),
            ).fetchone()
            if not row:
                return None
            rec = dict(row)
            rec["links"] = [dict(r) for r in conn.execute(
                "SELECT source, pc_no, po_no, style, linked_at, linked_by "
                "FROM cutting_plan_links WHERE plan_id=? "
                "ORDER BY pc_no, po_no, style", (plan_id,)).fetchall()]
        try:
            rec["parsed"] = json.loads(rec.pop("parsed_json") or "{}")
        except json.JSONDecodeError:
            rec["parsed"] = {}
        return rec

    def get_plan_file(self, plan_id: int) -> tuple[str, bytes] | None:
        """(filename, bytes) of the original upload, or None when not stored."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT source_file, file_blob FROM cutting_plans WHERE id=?",
                (plan_id,)).fetchone()
        if not row or row["file_blob"] is None:
            return None
        return (row["source_file"] or f"cut_plan_{plan_id}.xlsx",
                bytes(row["file_blob"]))

    def find_by_hash(self, file_bytes: bytes) -> dict | None:
        """Return the existing plan with identical bytes, if any."""
        if not file_bytes:
            return None
        digest = hashlib.sha256(bytes(file_bytes)).hexdigest()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, plan_name, source_file, uploaded_at, uploaded_by "
                "FROM cutting_plans WHERE source_hash=? ORDER BY id DESC "
                "LIMIT 1", (digest,)).fetchone()
        return dict(row) if row else None

    def list_demands(self, plan_id: int) -> pd.DataFrame:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT style, color, size, qty, cut_qty "
                "FROM cutting_plan_demands WHERE plan_id=? ORDER BY id",
                (plan_id,)).fetchall()
        return (pd.DataFrame([dict(r) for r in rows]) if rows
                else pd.DataFrame(columns=["style", "color", "size",
                                           "qty", "cut_qty"]))

    def plans_for_pos(self, pc_nos: list[str] | None = None,
                      po_nos: list[str] | None = None,
                      styles: list[str] | None = None,
                      source: str = SOURCE_SKY_EAST) -> pd.DataFrame:
        """Plans linked to any of the given PC No.s / PO numbers / styles.

        *styles* narrows to plans covering those PO-side styles; links made
        before styles were recorded (``style=''``, meaning the whole PO) match
        any style filter rather than disappearing from the results.
        """
        pc_nos = [p for p in (pc_nos or []) if p]
        po_nos = [p for p in (po_nos or []) if p]
        styles = [s for s in (styles or []) if s]
        cols = ["plan_id", "pc_no", "po_no", "style"]
        if not pc_nos and not po_nos and not styles:
            return pd.DataFrame(columns=cols)
        clauses, params = [], [source]
        if pc_nos:
            clauses.append(f"l.pc_no IN ({','.join('?' * len(pc_nos))})")
            params += pc_nos
        if po_nos:
            clauses.append(f"l.po_no IN ({','.join('?' * len(po_nos))})")
            params += po_nos
        if styles and clauses:
            # Narrowing a PO match: a link made before styles were recorded
            # ('' = the whole PO) still covers the style being asked about.
            where = (f"({' OR '.join(clauses)}) AND (l.style = '' OR "
                     f"l.style IN ({','.join('?' * len(styles))}))")
            params += styles
        elif styles:
            # Searching by style alone — only an explicit style match counts,
            # or every whole-PO link in the database would come back.
            where = f"l.style IN ({','.join('?' * len(styles))})"
            params += styles
        else:
            where = f"({' OR '.join(clauses)})"
        with self._conn() as conn:
            rows = conn.execute(
                f"""SELECT DISTINCT l.plan_id AS plan_id, l.pc_no, l.po_no,
                           l.style, p.plan_name, p.order_qty, p.cut_qty,
                           p.colors, p.styles, p.uploaded_at
                    FROM cutting_plan_links l
                    JOIN cutting_plans p ON p.id = l.plan_id
                    WHERE l.source = ? AND {where}
                    ORDER BY datetime(p.uploaded_at) DESC""",
                params).fetchall()
        return (pd.DataFrame([dict(r) for r in rows]) if rows
                else pd.DataFrame(columns=cols))

    def count(self) -> int:
        with self._conn() as conn:
            return int(conn.execute(
                "SELECT COUNT(*) FROM cutting_plans").fetchone()[0])


# ---------------------------------------------------------------------------
# Summary helpers (module-level so the UI can summarise before saving)
# ---------------------------------------------------------------------------

def consumption(length_m: Any, qty: Any, digits: int = 4) -> float | None:
    """Fabric consumption — metres of one fabric divided by a quantity.

    Which quantity decides what the number means, so callers pass it
    explicitly: against the unit count it is metres per garment (what fabric
    purchasing orders against, 单耗); against the piece count it is metres per
    piece, which is what the plan's own "Average Length" line reports.  For a
    co-ord set cut from one shell those differ by a factor of two.

    Returns None when either side is missing — a blank cell, not a 0 that
    would read as "this fabric costs nothing".
    """
    try:
        metres = float(length_m or 0)
        n = float(qty or 0)
    except (TypeError, ValueError):
        return None
    if metres <= 0 or n <= 0:
        return None
    return round(metres / n, digits)


def cut_vs_po_pct(po_qty: Any, cut_qty: Any) -> float | None:
    """How far the plan's cut quantity sits from what the PO ordered, in %.

    Positive means overcut.  Both figures are *unit* counts — the plan's
    per-style total, not the per-fabric piece count: a fabric's ``cut_qty``
    sums the pieces of every style cut from it (trousers + top of a co-ord
    set), so measuring it against a PO's unit quantity would read as +111 %
    when nothing is actually over.

    Returns None when the PO quantity is unknown (nothing linked, or the POs
    aren't in this database) — there is no baseline to compare against.
    """
    try:
        po = float(po_qty or 0)
        cut = float(cut_qty or 0)
    except (TypeError, ValueError):
        return None
    if po <= 0:
        return None
    return round((cut - po) / po * 100.0, 2)


def _achieved_by_cell(parsed: dict[str, Any]) -> dict[tuple[str, str, str], int]:
    """(style, colour, size) → achieved qty, taken from the material whose
    solution covers that cell with the largest count.

    A garment is cut from several materials (shell, lining); each material's
    solution repeats the same garment counts, so summing them would multiply
    the quantity by the number of materials.
    """
    from ..parsers.cutting_plan import achieved_rows

    best: dict[tuple[str, str, str], int] = {}
    for mat in parsed.get("materials", []):
        for sol in achieved_rows(mat.get("solution", [])):
            color = sol.get("color", "")
            for cell in sol.get("cells", []):
                key = (cell.get("style", ""), color, cell.get("size", ""))
                qty = int(cell.get("qty") or 0)
                if qty > best.get(key, 0):
                    best[key] = qty
    return best


def summarise_plan(parsed: dict[str, Any]) -> dict[str, Any]:
    """Flatten a parsed plan into the summary columns of ``cutting_plans``."""
    materials = parsed.get("materials", [])
    style_totals: dict[str, int] = parsed.get("style_totals") or {}

    achieved = _achieved_by_cell(parsed)
    cut_per_style: dict[str, int] = {}
    for (style, _color, _size), qty in achieved.items():
        cut_per_style[style] = cut_per_style.get(style, 0) + qty

    fabric = sum(float(m.get("fabric_length_m") or 0) for m in materials)
    # Weight each material's efficiency by the fabric it consumes — a lining
    # marker using 3 % of the fabric shouldn't move the headline number as
    # much as the shell.
    weighted = sum(
        float(m.get("total_efficiency_pct") or 0) * float(m.get("fabric_length_m") or 0)
        for m in materials
    )
    efficiency = (weighted / fabric) if fabric else (
        float(materials[0].get("total_efficiency_pct") or 0) if materials else 0.0
    )

    return {
        "plan_name":  parsed.get("order_name", "") or "",
        "client":     parsed.get("client", "") or "",
        "operator":   parsed.get("operator", "") or "",
        "plan_date":  parsed.get("plan_date", "") or "",
        "plan_time":  parsed.get("plan_time", "") or "",
        "styles":     ", ".join(s.get("name", "") for s in parsed.get("styles", [])
                                if s.get("name")),
        "colors":     ", ".join(parsed.get("colors", []) or []),
        "materials":  ", ".join(str(m.get("material", "")) for m in materials
                                if m.get("material")),
        "order_qty":  max(style_totals.values()) if style_totals else 0,
        "cut_qty":    max(cut_per_style.values()) if cut_per_style else 0,
        "total_tables":  int(parsed.get("total_tables") or 0),
        "total_markers": sum(int(m.get("n_markers") or 0) for m in materials),
        "fabric_length_m": round(fabric, 4),
        "efficiency_pct":  round(efficiency, 4),
    }
