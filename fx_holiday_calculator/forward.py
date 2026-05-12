"""FX forward outright date math.

A forward outright is a single-leg trade: settle once on the forward date.
Mathematically the date math is the same as a standard swap with no near
tenor — see `swap.py`'s PERIOD/IMM/BROKEN branch. This module is a thin
wrapper that relabels the result so that consumers don't see misleading
'near'/'far' fields when there is no near leg.

Conventions: see docs/conventions.md §12 (FX Forward outright).
"""
from dataclasses import dataclass, field
from datetime import date

from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.conventions.business_day import AdjustmentStep
from fx_holiday_calculator.conventions.cross import RefCurrency
from fx_holiday_calculator.pairs import Pair
from fx_holiday_calculator.swap import CalendarMode, calculate_swap_dates
from fx_holiday_calculator.tenor import Tenor


class InvalidForwardTenorError(ValueError):
    """Forward outright requires a forward tenor (PERIOD / IMM / BROKEN)."""


@dataclass
class ForwardResult:
    trade_date: date
    spot_date: date  # reference date used to compute the forward
    settlement_date: date  # the single settlement date of the outright
    spot_trace: list[AdjustmentStep]
    settlement_trace: list[AdjustmentStep]
    calendars_used: list[str]
    calendar_mode: CalendarMode = "FX"
    warnings: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)


def calculate_forward_dates(
    *,
    trade_date: date,
    pair: Pair,
    tenor: Tenor,
    ref_currency: RefCurrency = "USD",
    calendars: dict[str, RtgsCalendar],
    exchange_calendars: dict[str, ExchangeCalendar] | None = None,
    calendar_mode: CalendarMode = "FX",
) -> ForwardResult:
    if tenor.kind in {"SPOT", "ON", "TN", "SN"}:
        raise InvalidForwardTenorError(
            "Forward outright requires a forward tenor (PERIOD / IMM / BROKEN)."
        )
    swap_result = calculate_swap_dates(
        trade_date=trade_date,
        pair=pair,
        far_tenor=tenor,
        near_tenor=None,
        ref_currency=ref_currency,
        calendars=calendars,
        exchange_calendars=exchange_calendars,
        calendar_mode=calendar_mode,
    )
    # swap_result.near_date is set to spot for the no-near-tenor forward-leg
    # branch in swap.py. We discard it; the outright has only one settlement.
    assert swap_result.far_date is not None
    return ForwardResult(
        trade_date=swap_result.trade_date,
        spot_date=swap_result.spot_date,
        settlement_date=swap_result.far_date,
        spot_trace=swap_result.spot_trace,
        settlement_trace=swap_result.far_trace,
        calendars_used=swap_result.calendars_used,
        calendar_mode=swap_result.calendar_mode,
        warnings=list(swap_result.warnings),
        reasoning=[
            s.replace("**Far anchor:**", "**Settlement anchor:**").replace(
                "**Far roll", "**Settlement roll"
            )
            for s in swap_result.reasoning
        ],
    )
