"""Quoted-price conversion for fabric presentation sheets.

The customer-facing sheet quotes **USD per yard**; the internal cost in
``fabric_master`` is **RMB per metre**.  The conversion is the formula the
hand-maintained workbook used:

    =CEILING(rmb_per_m * 1.1 / 6.7 * 0.9144, 0.05)

which is, in order:

* ``* markup``    — commercial margin on the internal cost (1.1 = +10%)
* ``/ fx_rate``   — RMB → USD (6.7 RMB per USD)
* ``* 0.9144``    — per-metre → per-yard (1 yard = 0.9144 m exactly)
* ``CEILING(step)`` — round **up** to the next 0.05, never down: rounding a
  quote down would sell below the intended margin.

markup / fx_rate / round_step are parameters rather than constants because
they are commercial decisions that move — an FX rate especially — and every
sheet stores the values it was built with so old quotes stay reproducible.
"""
from __future__ import annotations

import math

# 1 international yard = 0.9144 metres, exactly (ISO 31-1).
METRES_PER_YARD = 0.9144

DEFAULT_MARKUP = 1.1
DEFAULT_FX_RATE = 6.7
DEFAULT_ROUND_STEP = 0.05


def usd_per_yard(rmb_per_m: float | None, *,
                 markup: float = DEFAULT_MARKUP,
                 fx_rate: float = DEFAULT_FX_RATE,
                 round_step: float = DEFAULT_ROUND_STEP) -> float | None:
    """Quoted USD/yard from an internal RMB/metre cost.

    Returns None when there is no usable input price, so a missing cost
    shows as blank on the sheet rather than as a quote of 0.00.
    """
    if rmb_per_m is None:
        return None
    try:
        rmb = float(rmb_per_m)
    except (TypeError, ValueError):
        return None
    if rmb <= 0 or not math.isfinite(rmb):
        return None
    if fx_rate <= 0:
        raise ValueError("fx_rate must be positive")

    usd = rmb * markup / fx_rate * METRES_PER_YARD
    if round_step and round_step > 0:
        # Excel's CEILING(x, step): up to the next multiple of step.
        usd = math.ceil(usd / round_step) * round_step
    # Guard against binary-float dust (…/0.05 can land on 2.6500000000000004).
    return round(usd, 4)
