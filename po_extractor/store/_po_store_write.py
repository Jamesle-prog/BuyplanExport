"""Write-side mixin for POStore (check_and_save, save, force_save, etc.)."""
from __future__ import annotations

import hashlib
import threading
from dataclasses import asdict
from datetime import datetime
from typing import Literal

from ..models import POData

SaveStatus = Literal["new", "duplicate", "updated", "skipped"]

# Serialises the read-compare-write sequence in check_and_save/force_save.
# The metadata read and the save run on separate connections, so without
# this two Streamlit session threads uploading the same PO both read
# "not present", both save as "new" (one archive row lost), or both
# archive (duplicate history rows).  Streamlit sessions are threads in one
# process, so a process-level lock covers the realistic race.
_PO_WRITE_LOCK = threading.Lock()


def _row_hash(po: POData) -> str:
    """Stable hash of PO content: version string + sorted size rows (including UPC).

    UPC is included so that a correction that only updates barcode values is
    detected as a real change and not silently discarded as a duplicate.
    """
    m = po.metadata
    version_key = f"{m.po_number}|{m.version or ''}|{m.xport_date or ''}"
    size_key = "|".join(
        f"{r.style}:{r.color}:{r.size}:{r.units}:{r.upc or ''}"
        for r in sorted(po.size_rows, key=lambda r: (r.style, r.color, r.size))
    )
    return hashlib.sha256(f"{version_key}#{size_key}".encode()).hexdigest()


def _total_units(po: POData) -> int:
    return sum(r.units for r in po.size_rows)


class _WritesMixin:
    """Write operations for POStore. Requires self._conn() from BaseSQLiteStore."""

    # ------------------------------------------------------------------ #
    # Public write API                                                      #
    # ------------------------------------------------------------------ #

    def check_and_save(self, po: POData) -> tuple[SaveStatus, dict | None]:
        """
        Validate and save a PO.

        Returns (status, diff) where:
          - "new"       → brand new PO, saved. diff=None
          - "duplicate" → identical content already stored, skipped. diff=None
          - "updated"   → same PO number, content changed, old version archived,
                          new version saved. diff={"old": {...}, "new": {...}}
          - "skipped"   → po_number is empty, nothing done. diff=None
        """
        po_number = (po.metadata.po_number or "").strip()
        if not po_number:
            return "skipped", None

        with _PO_WRITE_LOCK:
            return self._check_and_save_locked(po, po_number)

    def _check_and_save_locked(self, po: POData, po_number: str) -> tuple[SaveStatus, dict | None]:
        existing = self._get_metadata(po_number)

        if existing is None:
            self._do_save(po)
            return "new", None

        # Compare by content hash
        new_hash = _row_hash(po)
        old_hash = existing.get("content_hash", "")

        new_version = (po.metadata.version or "").strip()
        old_version = (existing.get("version") or "").strip()
        new_units = _total_units(po)
        old_units = existing.get("total_units", 0) or 0

        # Primary check: content hash captures any size/color distribution change.
        # Fall back to version+units only for records that pre-date hash storage.
        if new_hash and old_hash:
            is_duplicate = (new_hash == old_hash)
        else:
            is_duplicate = (new_version == old_version and new_units == old_units)

        if is_duplicate:
            return "duplicate", None

        # Content changed — archive old, save new
        diff = {
            "old": {
                "version":    old_version or "—",
                "xport_date": existing.get("xport_date") or "—",
                "total_units": old_units,
                "extracted_at": existing.get("extracted_at") or "—",
            },
            "new": {
                "version":    new_version or "—",
                "xport_date": po.metadata.xport_date or "—",
                "total_units": new_units,
                "extracted_at": po.metadata.extracted_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        }
        self._archive_and_update(po, existing, old_units)
        return "updated", diff

    def save(self, po: POData) -> None:
        """Unconditional save — used internally and for testing."""
        self._do_save(po)

    def force_save(self, po: POData) -> None:
        """Overwrite unconditionally (used when user explicitly confirms an update)."""
        po_number = (po.metadata.po_number or "").strip()
        if not po_number:
            return  # BUG-05: guard against NULL-keyed row insertion
        with _PO_WRITE_LOCK:
            existing = self._get_metadata(po_number)
            old_units = existing.get("total_units", 0) if existing else 0
            if existing:
                self._archive_and_update(po, existing, old_units)
            else:
                self._do_save(po)

    def save_many_checked(self, pos: list[POData]) -> list[tuple[str, SaveStatus, dict | None]]:
        """
        Process a list of POs in order, delegating every decision to
        check_and_save().

        When the same PO number appears more than once in the batch (e.g. the
        user uploads v1 and v2 together), each occurrence is evaluated against
        whatever is currently in the database — so v1 is saved as "new", then
        v2 is compared against v1, detected as changed, archived, and saved as
        "updated" with a history row.  Skipping the second occurrence (as the
        old "first occurrence wins" logic did) prevented that revision from ever
        being recorded.

        Returns [(po_number, status, diff), ...].
        """
        results = []
        for po in pos:
            pn = (po.metadata.po_number or "").strip()
            status, diff = self.check_and_save(po)
            results.append((pn, status, diff))
        return results

    # ------------------------------------------------------------------ #
    # Internal helpers                                                      #
    # ------------------------------------------------------------------ #

    def _do_save(self, po: POData) -> None:
        with self._conn() as conn:
            self._do_save_with_conn(po, conn)

    def _do_save_with_conn(self, po: POData, conn) -> None:
        """Insert PO metadata + size rows into *conn* (caller owns the transaction)."""
        m = asdict(po.metadata)
        extracted_at = m.get("extracted_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        content_hash = _row_hash(po)

        conn.execute(
            """INSERT OR REPLACE INTO po_metadata
               (po_number, company, style, factory, country_of_origin, xport_date,
                issue_date, version, division_code, division_name,
                source_format, file_name, extracted_at,
                parser_version, parse_confidence, validation_status,
                revision_reason, source_file_hash, processed_by,
                external_quote_id, source_module, integration_status,
                content_hash,
                buyer, seller, ship_to, destination_code, incoterm, origin_port,
                issued_by, discount, payment_terms, approval_status, season,
                customer, style_description, style_group,
                unit_cost, line_extended_cost, factory_ship_date, packaging,
                hanger, description_code, msrp, cpo, fabric)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                       ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (m.get("po_number"), m.get("company"), m.get("style"), m.get("factory"),
             m.get("country_of_origin"), m.get("xport_date"),
             m.get("po_date"), m.get("version"),
             m.get("division_code"), m.get("division_name"),
             m.get("source_format"), m.get("file_name"), extracted_at,
             m.get("parser_version"), m.get("parse_confidence"), m.get("validation_status"),
             m.get("revision_reason"), m.get("source_file_hash"), m.get("processed_by"),
             m.get("external_quote_id"), m.get("source_module"), m.get("integration_status"),
             content_hash,
             m.get("buyer"), m.get("seller"), m.get("ship_to"), m.get("destination_code"),
             m.get("incoterm"), m.get("origin_port"), m.get("issued_by"), m.get("discount"),
             m.get("payment_terms"), m.get("approval_status"), m.get("season"),
             m.get("customer"), m.get("style_description"), m.get("style_group"),
             m.get("unit_cost"), m.get("line_extended_cost"), m.get("factory_ship_date"),
             m.get("packaging"), m.get("hanger"), m.get("description_code"),
             m.get("msrp"), m.get("cpo"), m.get("fabric")),
        )
        conn.executemany(
            """INSERT OR REPLACE INTO po_size_rows
               (po_number, style, color, size, units, upc, extracted_at)
               VALUES (?,?,?,?,?,?,?)""",
            [(r.po_number, r.style, r.color, r.size, r.units, r.upc, extracted_at)
             for r in po.size_rows],
        )

    def _archive_and_update(self, po: POData, existing: dict, old_units: int) -> None:
        """Archive the current record and save the new one in a single atomic transaction.

        BUG-04 fix: previously the archive and save used two separate connections
        (separate transactions). If _do_save failed after the archive committed, the
        old size rows were permanently deleted and the new ones never inserted. Now
        both operations share one connection so they commit or roll back together.
        """
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO po_version_history
                   (po_number, style, factory, country_of_origin, xport_date,
                    issue_date, version, division_code, division_name,
                    source_format, file_name, extracted_at, archived_at, total_units)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (existing.get("po_number"), existing.get("style"),
                 existing.get("factory"), existing.get("country_of_origin"),
                 existing.get("xport_date"), existing.get("issue_date"),
                 existing.get("version"), existing.get("division_code"),
                 existing.get("division_name"), existing.get("source_format"),
                 existing.get("file_name"), existing.get("extracted_at"),
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"), old_units),
            )
            # Remove old size rows before inserting new ones
            conn.execute("DELETE FROM po_size_rows WHERE po_number = ?",
                         (existing.get("po_number"),))
            # Save new data in the same transaction
            self._do_save_with_conn(po, conn)
