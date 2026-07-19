"""RMB capital-form amount (人民币大写金额) — for contract documents.

``rmb_capital(12345.67)`` -> ``"壹万贰仟叁佰肆拾伍元陆角柒分"``.
Standard financial-document conventions: 零 collapsing (no double 零,
no trailing 零 before 元), 整 suffix for whole-yuan amounts, 负 prefix
for negatives.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

_DIGITS = "零壹贰叁肆伍陆柒捌玖"
_UNITS4 = ["", "拾", "佰", "仟"]          # within a 4-digit group
_GROUPS = ["", "万", "亿", "万亿"]        # 4-digit group multipliers


def _four_digits(n: int) -> str:
    """Capital form of 0..9999, with internal 零 collapsing, no leading 零."""
    if n == 0:
        return ""
    out = []
    zero_pending = False
    started = False
    for pos in (3, 2, 1, 0):
        d = (n // 10 ** pos) % 10
        if d == 0:
            if started:
                zero_pending = True
            continue
        if zero_pending:
            out.append("零")
            zero_pending = False
        out.append(_DIGITS[d] + _UNITS4[pos])
        started = True
    return "".join(out)


def rmb_capital(amount) -> str:
    """Return the 人民币大写 form of *amount* (rounded to 2 dp, half-up)."""
    dec = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "负" if dec < 0 else ""
    dec = abs(dec)
    yuan = int(dec)
    cents = int((dec - yuan) * 100)
    jiao, fen = divmod(cents, 10)

    if yuan == 0 and cents == 0:
        return "零元整"

    # ── Yuan part ──
    yuan_str = (_rebuild_yuan(yuan) + "元") if yuan else ""

    # ── Jiao/fen part ──
    tail = ""
    if cents == 0:
        tail = "整"
    else:
        if jiao:
            tail += _DIGITS[jiao] + "角"
        elif yuan:
            tail += "零"          # e.g. 5.05 -> 伍元零伍分
        if fen:
            tail += _DIGITS[fen] + "分"
        elif jiao:
            tail += "整"          # e.g. 5.50 -> 伍元伍角整

    return sign + yuan_str + tail


def _rebuild_yuan(yuan: int) -> str:
    """Capital form of the integer yuan part (no 元 suffix)."""
    groups: list[int] = []
    while yuan:
        groups.append(yuan % 10000)
        yuan //= 10000
    parts: list[str] = []
    for gi in range(len(groups) - 1, -1, -1):
        g = groups[gi]
        if g == 0:
            # only mark a zero group if something lower is non-zero and we
            # already emitted something higher
            if parts and any(groups[j] for j in range(gi)):
                if not parts[-1].endswith("零"):
                    parts.append("零")
            continue
        if parts and g < 1000 and not parts[-1].endswith("零"):
            parts.append("零")
        parts.append(_four_digits(g) + _GROUPS[gi])
    return "".join(parts)
