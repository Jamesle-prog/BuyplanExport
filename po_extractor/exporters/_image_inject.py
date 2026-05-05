"""Inject style photos into a saved buyplan .xlsx (one sheet per style).

openpyxl copy_worksheet() does not carry drawings/images.  After saving we
patch the zip archive directly.

Each style sheet gets up to two photos:
  • front photo  — centred in the left  merged picture box (default J3:L6)
  • back  photo  — centred in the right merged picture box (default M3:O6)

Photos are skipped silently when bytes are None / missing.
"""
from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------

_NS_XDR = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
_NS_R   = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_A   = "http://schemas.openxmlformats.org/drawingml/2006/main"
_RT_IMG = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
_RT_DRW = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing"
_CT_DRW = "application/vnd.openxmlformats-officedocument.drawing+xml"
_CT_PNG = "image/png"


def _anchor_xml(rid: str, pic_id: int, region: dict) -> str:
    """One <twoCellAnchor> block for a single photo."""
    fc  = region["from_col"]
    fr  = region["from_row"]
    tc  = region["to_col"]
    tr  = region["to_row"]
    return (
        f'<xdr:twoCellAnchor editAs="twoCell">'
        f'<xdr:from>'
        f'<xdr:col>{fc}</xdr:col><xdr:colOff>0</xdr:colOff>'
        f'<xdr:row>{fr}</xdr:row><xdr:rowOff>0</xdr:rowOff>'
        f'</xdr:from>'
        f'<xdr:to>'
        f'<xdr:col>{tc}</xdr:col><xdr:colOff>0</xdr:colOff>'
        f'<xdr:row>{tr}</xdr:row><xdr:rowOff>0</xdr:rowOff>'
        f'</xdr:to>'
        f'<xdr:pic>'
        f'<xdr:nvPicPr>'
        f'<xdr:cNvPr id="{pic_id}" name="Photo {pic_id}"/>'
        f'<xdr:cNvPicPr><a:picLocks noChangeAspect="0"/></xdr:cNvPicPr>'
        f'</xdr:nvPicPr>'
        f'<xdr:blipFill>'
        f'<a:blip r:embed="{rid}" cstate="print"/>'
        f'<a:stretch><a:fillRect/></a:stretch>'
        f'</xdr:blipFill>'
        f'<xdr:spPr>'
        f'<a:xfrm><a:off x="0" y="0"/><a:ext cx="1" cy="1"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f'</xdr:spPr>'
        f'</xdr:pic>'
        f'<xdr:clientData/>'
        f'</xdr:twoCellAnchor>'
    )


def _drawing_xml(anchors: list[str]) -> bytes:
    body = "".join(anchors)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<xdr:wsDr xmlns:xdr="{_NS_XDR}" xmlns:r="{_NS_R}" xmlns:a="{_NS_A}">'
        f'{body}'
        f'</xdr:wsDr>'
    ).encode("utf-8")


def _drawing_rels_xml(rids: dict[str, str]) -> bytes:
    """Build the per-drawing rels file.

    *rids* maps ``rId{N}`` → media path in the zip (e.g. ``xl/media/img.png``).
    The Target attribute is resolved relative to the drawing file
    (``xl/drawings/drawing{N}.xml``), so we strip the leading ``xl/`` and
    prepend ``../`` to walk up out of ``xl/drawings/`` into ``xl/``.
    """
    rels_xml = []
    for rid, path in rids.items():
        rel_path = path[3:] if path.startswith("xl/") else path
        rels_xml.append(
            f'<Relationship Id="{rid}" Type="{_RT_IMG}" Target="../{rel_path}"/>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'{"".join(rels_xml)}'
        f'</Relationships>'
    ).encode("utf-8")


# ---------------------------------------------------------------------------
# Default photo regions — derived from the shared 1-based PhotoRegion
# constants in _photo_utils so there is a single source of truth.
# This module needs 0-based indices (OOXML drawingML convention) with the
# *to* marker exclusive — PhotoRegion.to_zero_based() does that conversion.
# ---------------------------------------------------------------------------

from ._photo_utils import PHOTO_REGION_FRONT, PHOTO_REGION_BACK   # noqa: E402

DEFAULT_PHOTO_REGIONS = {
    "front": PHOTO_REGION_FRONT.to_zero_based(),
    "back":  PHOTO_REGION_BACK.to_zero_based(),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def inject_style_photos(
    output_path: str | Path,
    sheet_photo_map: dict[str, dict[str, bytes | None]],
    photo_regions: dict | None = None,
) -> None:
    """Inject front / back photos into each style sheet of a buyplan xlsx.

    Parameters
    ----------
    output_path:     Generated buyplan xlsx — modified in-place.
    sheet_photo_map: {sheet_title: {'front': bytes|None, 'back': bytes|None}}
                     None values are skipped silently.
    photo_regions:   Optional override for cell regions.  Dict with keys
                     'front' and/or 'back', each a dict with from_col,
                     from_row, to_col, to_row (all 0-based).
    """
    output_path = Path(output_path)
    if not output_path.exists():
        return

    # Remove sheets that have no photos at all
    active = {
        title: photos
        for title, photos in sheet_photo_map.items()
        if any(v is not None for v in photos.values())
    }
    if not active:
        return

    regions = {**DEFAULT_PHOTO_REGIONS, **(photo_regions or {})}
    tmp = output_path.with_suffix(".tmp_photos")

    try:
        _patch(output_path, tmp, active, regions)
        if output_path.exists():
            output_path.unlink()
        shutil.move(str(tmp), str(output_path))
    except Exception as exc:
        if tmp.exists():
            tmp.unlink()
        import warnings
        warnings.warn(f"inject_style_photos: {exc}")


# keep old name for backward compatibility
inject_logo_into_sheets = inject_style_photos  # noqa: E305


# ---------------------------------------------------------------------------
# Core patcher
# ---------------------------------------------------------------------------

def _patch(
    src: Path,
    dst: Path,
    active: dict[str, dict[str, bytes | None]],
    regions: dict,
) -> None:
    with zipfile.ZipFile(src, "r") as inz:
        names  = set(inz.namelist())
        wb_xml = inz.read("xl/workbook.xml").decode("utf-8")
        ct_xml = inz.read("[Content_Types].xml").decode("utf-8")

        sheet_map = _parse_sheets(wb_xml)          # {title: 1-based sheet num}

        # Only process sheets that are in active AND in the workbook
        target = {
            title: num
            for title, num in sheet_map.items()
            if title in active
        }
        if not target:
            return

        # Next free media index (avoid collisions with existing media)
        existing_media = {
            int(m.group(1))
            for item in names
            for m in [re.search(r"xl/media/image(\d+)\.", item)]
            if m
        }
        next_media = max(existing_media, default=0) + 1

        # Next free drawing index
        existing_drw = {
            int(m.group(1))
            for item in names
            for m in [re.search(r"xl/drawings/drawing(\d+)\.xml$", item)]
            if m
        }
        next_drw = max(existing_drw, default=0) + 1

        # Build per-sheet injection plan
        #   plan[sheet_num] = {
        #       'dnum': int,
        #       'anchors': [str, ...],
        #       'rels': {rid: media_zip_path},
        #       'media': {media_zip_path: bytes},
        #   }
        plan: dict[int, dict] = {}
        for title, sheet_num in target.items():
            photos = active[title]    # {'front': bytes|None, 'back': bytes|None}
            anchors = []
            rels    = {}
            media   = {}
            pic_id  = 2   # shape id counter

            for side in ("front", "back"):
                photo_bytes = photos.get(side)
                if not photo_bytes:
                    continue
                rid        = f"rId{len(rels) + 1}"
                media_path = f"xl/media/image{next_media}.png"
                next_media_val = next_media  # capture before increment
                region = regions.get(side, DEFAULT_PHOTO_REGIONS.get(side, {}))
                anchors.append(_anchor_xml(rid, pic_id, region))
                rels[rid]              = media_path
                media[media_path]      = photo_bytes
                next_media += 1
                pic_id += 1

            if not anchors:
                continue

            plan[sheet_num] = {
                "dnum":    next_drw,
                "anchors": anchors,
                "rels":    rels,
                "media":   media,
            }
            next_drw += 1

        if not plan:
            return

        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as outz:
            for item in inz.namelist():
                data = inz.read(item)

                if item == "[Content_Types].xml":
                    data = _patch_ct(
                        data.decode("utf-8"), plan,
                    ).encode("utf-8")
                    outz.writestr(item, data)
                    continue

                # Patch existing sheet _rels
                m = re.match(r"xl/worksheets/_rels/sheet(\d+)\.xml\.rels$", item)
                if m:
                    n = int(m.group(1))
                    if n in plan:
                        txt = data.decode("utf-8")
                        rid = _next_rid(txt)
                        txt = txt.replace(
                            "</Relationships>",
                            f'<Relationship Id="{rid}" Type="{_RT_DRW}"'
                            f' Target="../drawings/drawing{plan[n]["dnum"]}.xml"/>'
                            "</Relationships>",
                        )
                        data = txt.encode("utf-8")
                    outz.writestr(item, data)
                    continue

                # Patch sheet XML — add <drawing r:id="..."/>
                m = re.match(r"xl/worksheets/sheet(\d+)\.xml$", item)
                if m:
                    n = int(m.group(1))
                    if n in plan:
                        rid = _drawing_rid_for_sheet(names, inz, n, plan[n]["dnum"])
                        txt = data.decode("utf-8")
                        if "<drawing " not in txt:
                            txt = txt.replace(
                                "</worksheet>",
                                f'<drawing xmlns:r="{_NS_R}" r:id="{rid}"/>'
                                f'</worksheet>',
                            )
                        data = txt.encode("utf-8")
                    outz.writestr(item, data)
                    continue

                outz.writestr(item, data)

            # Add missing sheet _rels files
            for n, info in plan.items():
                rels_path = f"xl/worksheets/_rels/sheet{n}.xml.rels"
                if rels_path not in names:
                    outz.writestr(
                        rels_path,
                        (
                            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                            f'<Relationships xmlns="http://schemas.openxmlformats.org'
                            f'/package/2006/relationships">'
                            f'<Relationship Id="rId1" Type="{_RT_DRW}"'
                            f' Target="../drawings/drawing{info["dnum"]}.xml"/>'
                            f'</Relationships>'
                        ).encode("utf-8"),
                    )

            # Add media, drawing XMLs and their rels
            for n, info in plan.items():
                dnum = info["dnum"]
                # Media files
                for path, data in info["media"].items():
                    outz.writestr(path, data)
                # Drawing XML
                outz.writestr(
                    f"xl/drawings/drawing{dnum}.xml",
                    _drawing_xml(info["anchors"]),
                )
                # Drawing rels
                outz.writestr(
                    f"xl/drawings/_rels/drawing{dnum}.xml.rels",
                    _drawing_rels_xml(info["rels"]),
                )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_sheets(wb_xml: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for i, m in enumerate(
        re.finditer(r"<sheet\b.*?/>", wb_xml, re.DOTALL), start=1
    ):
        nm = re.search(r'\bname="([^"]*)"', m.group(0))
        if nm:
            out[nm.group(1)] = i
    return out


def _next_rid(rels_xml: str) -> str:
    ids = re.findall(r'Id="rId(\d+)"', rels_xml)
    return f"rId{max((int(x) for x in ids), default=0) + 1}"


def _drawing_rid_for_sheet(
    names: set, inz: zipfile.ZipFile, sheet_n: int, dnum: int
) -> str:
    rels_path = f"xl/worksheets/_rels/sheet{sheet_n}.xml.rels"
    if rels_path in names:
        return _next_rid(inz.read(rels_path).decode("utf-8"))
    return "rId1"


def _patch_ct(ct_xml: str, plan: dict) -> str:
    additions: list[str] = []
    # Drawings
    for info in plan.values():
        part = f"/xl/drawings/drawing{info['dnum']}.xml"
        if part not in ct_xml:
            additions.append(f'<Override PartName="{part}" ContentType="{_CT_DRW}"/>')
    # PNG media (add Default extension once if not present)
    has_any_png = any(
        path.endswith(".png")
        for info in plan.values()
        for path in info["media"]
    )
    if has_any_png and 'Extension="png"' not in ct_xml:
        additions.append(f'<Default Extension="png" ContentType="{_CT_PNG}"/>')
    if additions:
        ct_xml = ct_xml.replace("</Types>", "\n".join(additions) + "</Types>")
    return ct_xml
