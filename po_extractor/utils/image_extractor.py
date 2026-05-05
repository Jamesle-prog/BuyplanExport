"""Extract DISPIMG embedded images from WPS/Excel xlsx files.

Excel (WPS) stores DISPIMG images in:
  xl/cellimages.xml          — maps name="ID_xxx" → r:embed="rIdN"
  xl/_rels/cellimages.xml.rels — maps rIdN → ../media/imageN.png
  xl/media/imageN.png        — actual image bytes

This module provides:
  extract_images_from_xlsx(path)
      → dict mapping  image_id (str) → image_bytes (bytes)

  ImageCache
      — lazy, multi-file cache keyed by image_id across all loaded xlsx files
"""
from __future__ import annotations

import re
import zipfile
from xml.etree import ElementTree as ET

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


def extract_images_from_xlsx(path: str) -> dict[str, bytes]:
    """
    Extract all DISPIMG-embedded images from an xlsx file.

    Returns
    -------
    dict  image_id → bytes
        image_id is the string from the DISPIMG formula, e.g.
        "ID_B9EFBCAD61844BBF8E4323A2E8891898"
    """
    result: dict[str, bytes] = {}

    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = set(zf.namelist())

            # 1. Parse cellimages.xml to map image_id → rId
            if "xl/cellimages.xml" not in names:
                return result  # no embedded DISPIMG images

            id_to_rid: dict[str, str] = {}
            xml_bytes = zf.read("xl/cellimages.xml")
            root = ET.fromstring(xml_bytes)

            for cell_img in root.findall(
                ".//etc:cellImage", _NS
            ):
                # <xdr:cNvPr name="ID_xxx" .../>
                for cnv_pr in cell_img.findall(".//xdr:cNvPr", _NS):
                    img_name = cnv_pr.get("name", "")
                    if not img_name.startswith("ID_"):
                        continue
                    # <a:blip r:embed="rIdN"/>
                    for blip in cell_img.findall(".//a:blip", _NS):
                        rid = blip.get(
                            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed",
                            ""
                        )
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
            for rel in rels_root.findall(
                f"{{{_REL_NS}}}Relationship"
            ):
                rid    = rel.get("Id", "")
                target = rel.get("Target", "")
                if rid and target:
                    # Target is relative to xl/, e.g. "../media/image1.png"
                    # Resolve to zip path
                    if target.startswith("../"):
                        zip_path = "xl/" + target[3:]
                    elif target.startswith("/"):
                        zip_path = target.lstrip("/")
                    else:
                        zip_path = "xl/" + target
                    rid_to_path[rid] = zip_path

            # 3. Read image bytes
            for img_id, rid in id_to_rid.items():
                img_path = rid_to_path.get(rid)
                if img_path and img_path in names:
                    result[img_id] = zf.read(img_path)

    except (zipfile.BadZipFile, ET.ParseError, KeyError):
        pass   # silently skip unreadable files

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
