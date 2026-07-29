"""Extract embedded images from WPS/Excel xlsx files.

A photo reaches a spreadsheet cell one of **two** ways, and a single client PO
routinely contains both — one row's picture pasted as a WPS cell image, the
next row's inserted the ordinary Excel way:

1. **WPS cell image (DISPIMG).** The cell holds a ``=DISPIMG("ID_xxx",1)``
   formula and the bytes live in a workbook-level part:
     xl/cellimages.xml            — maps name="ID_xxx" → r:embed="rIdN"
     xl/_rels/cellimages.xml.rels — maps rIdN → ../media/imageN.png
     xl/media/imageN.png          — actual image bytes

2. **Anchored picture** (Excel's own Insert ▸ Picture). Nothing is in the cell
   at all — the picture FLOATS over it, anchored from a drawing part:
     xl/worksheets/_rels/sheetN.xml.rels → xl/drawings/drawingM.xml
     xl/drawings/drawingM.xml            — anchor <xdr:from> col/row (0-based)
     xl/drawings/_rels/drawingM.xml.rels — rIdN → ../media/imageN.png

   Only form 1 used to be read here, so a style whose photo was inserted the
   ordinary way came through with no picture at all.

This module provides:
  extract_images_from_xlsx(path)
      → dict mapping  image_id (str) → image_bytes (bytes), both forms
  extract_dispimg_positions(path, sheet_index)  — form 1 cell positions
  extract_anchored_positions(path, sheet_index) — form 2 cell positions

  ImageCache
      — lazy, multi-file cache keyed by image_id across all loaded xlsx files
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import zipfile

# Sheet XML here comes straight from an UPLOADED workbook, so parse it with
# defusedxml when available: the stdlib ElementTree is documented as vulnerable
# to entity-expansion DoS ("billion laughs" / quadratic blowup). Falling back to
# the stdlib keeps this an optional hardening rather than a hard dependency —
# the parsing API and behaviour are identical either way.
try:
    from defusedxml import ElementTree as ET
    from defusedxml.common import DefusedXmlException
except ImportError:                                   # pragma: no cover
    from xml.etree import ElementTree as ET
    DefusedXmlException = ()                          # nothing extra to catch

# defusedxml raises DefusedXmlException (a ValueError subclass), NOT
# ET.ParseError, when it refuses a hostile document — so a rejected workbook
# must be caught here too, or hardening would turn a skipped file into a crash.
_XML_ERRORS = (ET.ParseError,) + (
    (DefusedXmlException,) if DefusedXmlException else ()
)

_DISPIMG_CELL_RE = re.compile(r'DISPIMG\("(ID_[0-9A-Fa-f]+)"', re.IGNORECASE)
_COL_LETTER_RE   = re.compile(r'^([A-Za-z]+)')


def _col_letters_to_num(letters: str) -> int:
    """A=1, Z=26, AA=27, …"""
    n = 0
    for ch in letters.upper():
        n = n * 26 + (ord(ch) - 64)
    return n


def extract_dispimg_positions(path: str, sheet_index: int = 0) -> dict[tuple[int, int], str]:
    """
    Parse worksheet XML to find all DISPIMG formula cells.

    Returns {(row_1based, col_1based): image_id} without loading openpyxl,
    so it works even when the workbook is opened with data_only=True (which
    would otherwise suppress formula strings and return None for DISPIMG cells).
    """
    result: dict[tuple[int, int], str] = {}
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = set(zf.namelist())
            sheet_path = f"xl/worksheets/sheet{sheet_index + 1}.xml"
            if sheet_path not in names:
                return result

            xml_bytes = zf.read(sheet_path)
            root = ET.fromstring(xml_bytes)
            ns_m = re.match(r'\{([^}]+)\}', root.tag)
            ns = ns_m.group(1) if ns_m else \
                "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

            for c_elem in root.iter(f'{{{ns}}}c'):
                f_elem = c_elem.find(f'{{{ns}}}f')
                if f_elem is None or not f_elem.text:
                    continue
                m = _DISPIMG_CELL_RE.search(f_elem.text)
                if not m:
                    continue
                img_id   = m.group(1)
                cell_ref = c_elem.get("r", "")
                col_m    = _COL_LETTER_RE.match(cell_ref)
                row_part = _COL_LETTER_RE.sub("", cell_ref)
                if col_m and row_part.isdigit():
                    result[(int(row_part), _col_letters_to_num(col_m.group(1)))] = img_id
    except Exception:
        pass
    return result


# XML namespaces used in WPS/Excel cellimages.xml
_NS = {
    "etc": "http://www.wps.cn/officeDocument/2017/etCustomData",
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "r":   "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a":   "http://schemas.openxmlformats.org/drawingml/2006/main",
}

_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


# ── Anchored pictures (Excel's own Insert ▸ Picture) ───────────────────────

_XDR_NS = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
_A_NS   = "http://schemas.openxmlformats.org/drawingml/2006/main"
_R_NS   = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _as_zip_source(path):
    """Accept a path, raw bytes, or a file-like object as a zip source."""
    if isinstance(path, (bytes, bytearray)):
        return io.BytesIO(bytes(path))
    if hasattr(path, "read") and hasattr(path, "seek"):
        path.seek(0)
        return path
    return path


def _resolve_target(base_dir: str, target: str) -> str:
    """Resolve a relationship Target against the owning part's directory."""
    if target.startswith("/"):
        return target.lstrip("/")
    parts = base_dir.split("/") if base_dir else []
    for seg in target.split("/"):
        if seg == "..":
            if parts:
                parts.pop()
        elif seg not in ("", "."):
            parts.append(seg)
    return "/".join(parts)


def _rels_for(zf, names: set[str], part: str) -> dict[str, tuple[str, str, str]]:
    """``{rId: (Target, TargetMode, Type)}`` from a part's ``.rels`` sidecar."""
    head, _, base = part.rpartition("/")
    rels_path = f"{head}/_rels/{base}.rels"
    out: dict[str, tuple[str, str, str]] = {}
    if rels_path not in names:
        return out
    try:
        root = ET.fromstring(zf.read(rels_path))
    except (KeyError, *_XML_ERRORS):
        return out
    for rel in root.findall(f"{{{_REL_NS}}}Relationship"):
        rid = rel.get("Id", "")
        if rid:
            out[rid] = (rel.get("Target", ""), rel.get("TargetMode", ""),
                        rel.get("Type", ""))
    return out


def _drawing_paths(zf, names: set[str], sheet_index: int | None) -> list[str]:
    """Drawing parts for one sheet, or for every sheet when *sheet_index* is None."""
    if sheet_index is not None:
        sheets = [f"xl/worksheets/sheet{sheet_index + 1}.xml"]
    else:
        sheets = sorted(n for n in names
                        if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
    out: list[str] = []
    for sheet in sheets:
        if sheet not in names:
            continue
        for target, mode, rtype in _rels_for(zf, names, sheet).values():
            if mode == "External" or not rtype.endswith("/drawing"):
                continue
            path = _resolve_target(os.path.dirname(sheet), target)
            if path in names and path not in out:
                out.append(path)
    return out


def _anchored_pictures(zf, names: set[str], drawing_path: str
                       ) -> list[tuple[int, int, str]]:
    """``[(row0, col0, media_zip_path)]`` for each picture anchored in a drawing.

    The anchor's ``<xdr:from>`` cell is the one the picture's top-left corner
    sits in, which is the cell a reader sees it as belonging to.
    """
    out: list[tuple[int, int, str]] = []
    try:
        root = ET.fromstring(zf.read(drawing_path))
    except (KeyError, *_XML_ERRORS):
        return out
    rels = _rels_for(zf, names, drawing_path)
    base = os.path.dirname(drawing_path)
    for anchor in root:
        # absoluteAnchor is positioned in EMUs with no cell reference at all.
        if anchor.tag.rpartition("}")[2] not in ("twoCellAnchor", "oneCellAnchor"):
            continue
        frm = anchor.find(f"{{{_XDR_NS}}}from")
        blip = anchor.find(f".//{{{_A_NS}}}blip")
        if frm is None or blip is None:
            continue
        col_el = frm.find(f"{{{_XDR_NS}}}col")
        row_el = frm.find(f"{{{_XDR_NS}}}row")
        if col_el is None or row_el is None:
            continue
        target, mode, _rtype = rels.get(blip.get(f"{{{_R_NS}}}embed", ""),
                                        ("", "", ""))
        # A linked (TargetMode="External") or placeholder relationship — seen
        # in real files as Target="NULL" — carries no bytes in this workbook.
        if not target or mode == "External":
            continue
        media = _resolve_target(base, target)
        if media not in names:
            continue
        try:
            out.append((int(row_el.text), int(col_el.text), media))
        except (TypeError, ValueError):
            continue
    return out


def _anchored_id(data: bytes) -> str:
    """Stable, filename-safe id for an anchored picture.

    Content-addressed, because an anchored picture has no id of its own. Two
    consequences that both matter: the same photo re-uploaded keeps its id
    rather than being saved again, and two workbooks that each call their
    picture ``image1.png`` cannot collide — a picture_id becomes a filename in
    a shared folder downstream, so a collision would attach the wrong photo.
    """
    return "IMG_" + hashlib.md5(data).hexdigest().upper()


def extract_anchored_positions(path, sheet_index: int = 0
                               ) -> dict[tuple[int, int], str]:
    """``{(row_1based, col_1based): image_id}`` for pictures floating over cells.

    A picture inserted the ordinary Excel way leaves the cell itself empty, so
    it carries no DISPIMG formula and :func:`extract_dispimg_positions` cannot
    see it. Its bytes come back from :func:`extract_images_from_xlsx` under the
    same id.
    """
    result: dict[tuple[int, int], str] = {}
    try:
        with zipfile.ZipFile(_as_zip_source(path), "r") as zf:
            names = set(zf.namelist())
            # One photo can be anchored in several places; memoise so a big
            # media part on a network mount is read once, not once per anchor.
            memo: dict[str, str] = {}
            for drawing in _drawing_paths(zf, names, sheet_index):
                for row0, col0, media in _anchored_pictures(zf, names, drawing):
                    if media not in memo:
                        memo[media] = _anchored_id(zf.read(media))
                    result[(row0 + 1, col0 + 1)] = memo[media]
    except (zipfile.BadZipFile, OSError, *_XML_ERRORS, KeyError):
        pass
    return result


def _anchored_images(zf, names: set[str]) -> dict[str, bytes]:
    """``image_id → bytes`` for every anchored picture in the workbook."""
    out: dict[str, bytes] = {}
    seen: set[str] = set()
    for drawing in _drawing_paths(zf, names, None):
        for _row0, _col0, media in _anchored_pictures(zf, names, drawing):
            if media in seen:
                continue
            seen.add(media)
            try:
                data = zf.read(media)
            except (KeyError, OSError):
                continue
            out.setdefault(_anchored_id(data), data)
    return out


def extract_images_from_xlsx(path: str) -> dict[str, bytes]:
    """
    Extract every embedded image from an xlsx file — both forms.

    Returns
    -------
    dict  image_id → bytes
        For a WPS cell image the id is the string from the DISPIMG formula,
        e.g. "ID_B9EFBCAD61844BBF8E4323A2E8891898". For a picture anchored
        over a cell there is no such id, so a content-addressed one is used
        (see :func:`_anchored_id`).
    """
    result: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(_as_zip_source(path), "r") as zf:
            names = set(zf.namelist())
            result.update(_dispimg_images(zf, names))
            result.update(_anchored_images(zf, names))
    except (zipfile.BadZipFile, OSError, *_XML_ERRORS, KeyError):
        pass   # silently skip unreadable / hostile files
    return result


def _dispimg_images(zf, names: set[str]) -> dict[str, bytes]:
    """``image_id → bytes`` for the WPS cell images (``xl/cellimages.xml``)."""
    result: dict[str, bytes] = {}

    try:
        # 1. Parse cellimages.xml to map image_id → rId
        if "xl/cellimages.xml" not in names:
            return result  # no embedded DISPIMG images

        id_to_rid: dict[str, str] = {}
        xml_bytes = zf.read("xl/cellimages.xml")
        root = ET.fromstring(xml_bytes)

        for cell_img in root.findall(".//etc:cellImage", _NS):
            # <xdr:cNvPr name="ID_xxx" .../>
            for cnv_pr in cell_img.findall(".//xdr:cNvPr", _NS):
                img_name = cnv_pr.get("name", "")
                if not img_name.startswith("ID_"):
                    continue
                # <a:blip r:embed="rIdN"/>
                for blip in cell_img.findall(".//a:blip", _NS):
                    rid = blip.get(f"{{{_R_NS}}}embed", "")
                    if rid:
                        id_to_rid[img_name] = rid

        if not id_to_rid:
            return result

        # 2. Parse cellimages.xml.rels to map rId → media path
        rels_path = "xl/_rels/cellimages.xml.rels"
        if rels_path not in names:
            return result

        rid_to_path: dict[str, str] = {}
        rels_xml = zf.read(rels_path)
        rels_root = ET.fromstring(rels_xml)
        for rel in rels_root.findall(f"{{{_REL_NS}}}Relationship"):
            rid    = rel.get("Id", "")
            target = rel.get("Target", "")
            if rid and target:
                # Target is relative to xl/, e.g. "../media/image1.png"
                rid_to_path[rid] = _resolve_target("xl", target)

        # 3. Read image bytes
        for img_id, rid in id_to_rid.items():
            img_path = rid_to_path.get(rid)
            if img_path and img_path in names:
                result[img_id] = zf.read(img_path)

    except (zipfile.BadZipFile, OSError, *_XML_ERRORS, KeyError):
        pass   # silently skip unreadable / hostile files

    return result


class ImageCache:
    """
    Multi-file image cache.  Images are extracted lazily on first access
    and cached in memory keyed by image_id.

    Usage
    -----
    cache = ImageCache()
    cache.add_file(path_to_order_xlsx)
    cache.add_file(path_to_fabric_xlsx)
    cache.add_file(path_to_progress_xlsx)

    img_bytes = cache.get("ID_B9EFBCAD61844BBF8E4323A2E8891898")
    """

    def __init__(self):
        self._cache:  dict[str, bytes] = {}
        self._loaded: set[str]         = set()

    def add_file(self, path: str) -> int:
        """
        Extract and cache all DISPIMG images from an xlsx file.

        Returns the number of new images added.
        """
        if path in self._loaded:
            return 0
        self._loaded.add(path)
        imgs = extract_images_from_xlsx(path)
        new = 0
        for img_id, data in imgs.items():
            if img_id not in self._cache:
                self._cache[img_id] = data
                new += 1
        return new

    def get(self, image_id: str) -> bytes | None:
        """Return image bytes or None if not found."""
        return self._cache.get(image_id)

    def has(self, image_id: str) -> bool:
        return image_id in self._cache

    def all_ids(self) -> list[str]:
        return list(self._cache.keys())

    def __len__(self) -> int:
        return len(self._cache)
