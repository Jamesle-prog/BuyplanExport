"""Factory dictionary — canonical factories + the many names clients use.

Different clients write the same factory differently ("01423 - CHANGZHOU
JINTAN XINZHUAN", "…XINZHUANGYUAN GARMENT CO.,LTD.", a bare "01423"), so raw
factory strings on POs don't line up. This store holds a *canonical* factory
and every *alias* that maps to it, so downstream features (factory-scoped
logins, reporting) can treat them as one.

Design
------
- ``factory_canonical`` — one row per real factory (display name + optional
  short code).
- ``factory_alias`` — every string seen in data, matched to a canonical.
  A canonical's own name is auto-registered as an alias, so resolution is a
  single lookup against this table.

Matching is on a normalised key (whitespace-collapsed, upper-cased) so
trivial spacing/case differences don't create spurious "unknown" factories,
while genuinely different names stay separate for the admin to link.
"""
from __future__ import annotations

from datetime import datetime

from .base_store import BaseSQLiteStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS factory_canonical (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    name_norm  TEXT NOT NULL UNIQUE,
    code       TEXT NOT NULL DEFAULT '',
    notes      TEXT NOT NULL DEFAULT '',
    created_at TEXT,
    created_by TEXT
);
CREATE TABLE IF NOT EXISTS factory_alias (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    alias        TEXT NOT NULL,
    alias_norm   TEXT NOT NULL UNIQUE,
    canonical_id INTEGER NOT NULL,
    created_at   TEXT,
    created_by   TEXT
);
CREATE INDEX IF NOT EXISTS idx_falias_canon ON factory_alias(canonical_id);
"""


def norm(s: str) -> str:
    """Normalised match key: collapse whitespace, upper-case, strip."""
    return " ".join(str(s or "").split()).upper()


def factory_code(s: str) -> str:
    """Leading numeric/short code before a ' - ' separator, if any.
    ``'01423 - CHANGZHOU …'`` → ``'01423'``. Used for fuzzy suggestions."""
    head = str(s or "").split(" - ", 1)[0].strip()
    return head if head and any(ch.isdigit() for ch in head) else ""


class FactoryRegistryStore(BaseSQLiteStore):
    """Canonical factories + aliases, with resolution and fuzzy suggestions."""

    _checked_paths: set[str] = set()

    def __init__(self, db_path: str):
        self.db_path = db_path
        if db_path not in FactoryRegistryStore._checked_paths:
            with self._conn() as conn:
                conn.executescript(_SCHEMA)
            FactoryRegistryStore._checked_paths.add(db_path)

    # ── Resolution ──────────────────────────────────────────────────────────

    def resolve_id(self, raw: str) -> int | None:
        """Canonical id for a raw factory string, or None if unknown."""
        key = norm(raw)
        if not key:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT canonical_id FROM factory_alias WHERE alias_norm=?",
                (key,),
            ).fetchone()
        return int(row[0]) if row else None

    def canonical_name(self, raw: str) -> str | None:
        """Canonical display name for a raw string, or None if unknown."""
        cid = self.resolve_id(raw)
        if cid is None:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT name FROM factory_canonical WHERE id=?", (cid,)
            ).fetchone()
        return row[0] if row else None

    def is_known(self, raw: str) -> bool:
        return self.resolve_id(raw) is not None

    # ── Reads ───────────────────────────────────────────────────────────────

    def list_canonical(self) -> list[dict]:
        """Every canonical factory with its aliases, name-sorted::

            [{"id", "name", "code", "notes", "aliases": [str, ...]}, ...]
        """
        with self._conn() as conn:
            cans = [dict(r) for r in conn.execute(
                "SELECT id, name, code, notes FROM factory_canonical "
                "ORDER BY name"
            ).fetchall()]
            aliases = conn.execute(
                "SELECT canonical_id, alias FROM factory_alias ORDER BY alias"
            ).fetchall()
        by_id: dict[int, list] = {}
        for cid, alias in aliases:
            by_id.setdefault(cid, []).append(alias)
        for c in cans:
            c["aliases"] = by_id.get(c["id"], [])
        return cans

    def canonical_names(self) -> list[str]:
        with self._conn() as conn:
            return [r[0] for r in conn.execute(
                "SELECT name FROM factory_canonical ORDER BY name").fetchall()]

    def aliases_for(self, canonical_id: int) -> list[str]:
        with self._conn() as conn:
            return [r[0] for r in conn.execute(
                "SELECT alias FROM factory_alias WHERE canonical_id=? ORDER BY alias",
                (canonical_id,),
            ).fetchall()]

    def scope_norms_for_names(self, names: list[str]) -> set[str]:
        """All normalised raw strings that count as in-scope for a factory user
        assigned *names* (canonical names). Includes every alias of each named
        canonical, plus the raw names themselves (legacy assignments made
        before a name was registered still match)."""
        out: set[str] = set()
        with self._conn() as conn:
            for n in names:
                out.add(norm(n))
                row = conn.execute(
                    "SELECT canonical_id FROM factory_alias WHERE alias_norm=?",
                    (norm(n),),
                ).fetchone()
                if row:
                    for a in conn.execute(
                        "SELECT alias_norm FROM factory_alias WHERE canonical_id=?",
                        (int(row[0]),),
                    ).fetchall():
                        out.add(a[0])
        return out

    # ── Unresolved detection + suggestion ───────────────────────────────────

    def data_factories(self) -> list[str]:
        """Distinct non-blank factory strings across the loaded PO tables
        (GIII ``po_metadata`` + ``production_tracking``). Missing tables are
        skipped so this never crashes on a partial DB."""
        seen: dict[str, str] = {}       # norm -> display (first spelling wins)
        with self._conn() as conn:
            for table in ("po_metadata", "production_tracking"):
                try:
                    rows = conn.execute(
                        f"SELECT DISTINCT factory FROM {table} "
                        f"WHERE TRIM(COALESCE(factory,'')) != ''"
                    ).fetchall()
                except Exception:
                    continue
                for (f,) in rows:
                    seen.setdefault(norm(f), str(f).strip())
        return sorted(seen.values())

    def list_unresolved(self) -> list[dict]:
        """Factory strings present in data but not yet in the dictionary, each
        with a fuzzy suggestion::

            [{"raw", "suggestion": {"id","name"} | None}, ...]
        """
        cans = self.list_canonical()
        out = []
        for raw in self.data_factories():
            if self.is_known(raw):
                continue
            out.append({"raw": raw, "suggestion": self._suggest(raw, cans)})
        return out

    def unresolved_count(self) -> int:
        return sum(1 for f in self.data_factories() if not self.is_known(f))

    @staticmethod
    def _suggest(raw: str, cans: list[dict]) -> dict | None:
        """Closest existing canonical for *raw*: first by shared factory code
        (e.g. '01423'), then by string similarity. None if nothing is close."""
        code = factory_code(raw)
        if code:
            for c in cans:
                if c.get("code") and norm(c["code"]) == norm(code):
                    return {"id": c["id"], "name": c["name"]}
                if any(factory_code(a) == code for a in c["aliases"]):
                    return {"id": c["id"], "name": c["name"]}
        # Fall back to fuzzy string similarity on the full name.
        import difflib
        best, best_ratio = None, 0.0
        rn = norm(raw)
        for c in cans:
            for cand in [c["name"], *c["aliases"]]:
                ratio = difflib.SequenceMatcher(None, rn, norm(cand)).ratio()
                if ratio > best_ratio:
                    best, best_ratio = c, ratio
        return ({"id": best["id"], "name": best["name"]}
                if best and best_ratio >= 0.6 else None)

    # ── Writes ──────────────────────────────────────────────────────────────

    def add_canonical(self, name: str, *, code: str = "", notes: str = "",
                      created_by: str = "") -> int:
        """Create a canonical factory (its name auto-registered as an alias).
        Returns the id. Raises ValueError on a blank or duplicate name."""
        name = (name or "").strip()
        if not name:
            raise ValueError("Factory name is required.")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conn() as conn:
            exists = conn.execute(
                "SELECT id FROM factory_canonical WHERE name_norm=?", (norm(name),)
            ).fetchone()
            if exists:
                raise ValueError(f"A factory named {name!r} already exists.")
            cur = conn.execute(
                "INSERT INTO factory_canonical (name, name_norm, code, notes, "
                "created_at, created_by) VALUES (?,?,?,?,?,?)",
                (name, norm(name), (code or "").strip(), (notes or "").strip(),
                 now, created_by),
            )
            cid = int(cur.lastrowid)
            conn.execute(
                "INSERT OR IGNORE INTO factory_alias (alias, alias_norm, "
                "canonical_id, created_at, created_by) VALUES (?,?,?,?,?)",
                (name, norm(name), cid, now, created_by),
            )
        return cid

    def add_alias(self, alias: str, canonical_id: int, *,
                  created_by: str = "") -> None:
        """Map a raw string to an existing canonical. Raises ValueError if the
        alias is already linked to a DIFFERENT canonical."""
        alias = (alias or "").strip()
        if not alias:
            raise ValueError("Alias is required.")
        key = norm(alias)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT canonical_id FROM factory_alias WHERE alias_norm=?", (key,)
            ).fetchone()
            if existing and int(existing[0]) != int(canonical_id):
                raise ValueError(
                    f"{alias!r} is already linked to another factory.")
            conn.execute(
                "INSERT OR IGNORE INTO factory_alias (alias, alias_norm, "
                "canonical_id, created_at, created_by) VALUES (?,?,?,?,?)",
                (alias, key, int(canonical_id), now, created_by),
            )

    def rename_canonical(self, canonical_id: int, new_name: str) -> None:
        new_name = (new_name or "").strip()
        if not new_name:
            raise ValueError("Factory name is required.")
        with self._conn() as conn:
            clash = conn.execute(
                "SELECT id FROM factory_canonical WHERE name_norm=? AND id!=?",
                (norm(new_name), int(canonical_id)),
            ).fetchone()
            if clash:
                raise ValueError(f"Another factory is named {new_name!r}.")
            conn.execute(
                "UPDATE factory_canonical SET name=?, name_norm=? WHERE id=?",
                (new_name, norm(new_name), int(canonical_id)),
            )

    def remove_alias(self, alias_norm_or_text: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM factory_alias WHERE alias_norm=?",
                         (norm(alias_norm_or_text),))

    def delete_canonical(self, canonical_id: int) -> None:
        """Delete a canonical factory and all its aliases (frees those strings
        to be flagged as unresolved again)."""
        with self._conn() as conn:
            conn.execute("DELETE FROM factory_alias WHERE canonical_id=?",
                         (int(canonical_id),))
            conn.execute("DELETE FROM factory_canonical WHERE id=?",
                         (int(canonical_id),))
