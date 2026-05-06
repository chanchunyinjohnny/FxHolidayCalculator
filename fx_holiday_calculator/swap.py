from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.conventions.business_day import (
    AdjustmentStep,
    apply_eom_with_trace,
    is_good_business_day,
    roll_with_trace,
)
from fx_holiday_calculator.conventions.cross import RefCurrency, rtgs_calendar_set
from fx_holiday_calculator.conventions.dates import add_period, next_imm_date
from fx_holiday_calculator.conventions.spot_offset import apply_spot_offset
from fx_holiday_calculator.pairs import Pair
from fx_holiday_calculator.tenor import Tenor


CalendarMode = Literal["FX", "EXCHANGE", "BOTH"]


class InvalidFFSCombinationError(ValueError):
    pass


@dataclass
class SwapResult:
    trade_date: date
    spot_date: date
    near_date: date | None
    far_date: date | None
    spot_trace: list[AdjustmentStep]
    near_trace: list[AdjustmentStep] = field(default_factory=list)
    far_trace: list[AdjustmentStep] = field(default_factory=list)
    calendars_used: list[str] = field(default_factory=list)
    calendar_mode: CalendarMode = "FX"


def calculate_swap_dates(
    *,
    trade_date: date,
    pair: Pair,
    far_tenor: Tenor,
    near_tenor: Tenor | None = None,
    ref_currency: RefCurrency = "USD",
    calendars: dict[str, RtgsCalendar],
    calendar_mode: CalendarMode = "FX",
) -> SwapResult:
    cs = rtgs_calendar_set(pair, ref=ref_currency, calendars=calendars)
    spot = apply_spot_offset(trade_date, pair, cs)
    labels = [f"{c} ({calendars[c].calendar_name})" for c in cs.members.keys()]
    base = SwapResult(
        trade_date=trade_date,
        spot_date=spot.spot_date,
        near_date=None,
        far_date=None,
        spot_trace=spot.trace,
        calendars_used=labels,
        calendar_mode=calendar_mode,
    )

    # SPOT — return only spot date, no near/far legs
    if far_tenor.kind == "SPOT" and near_tenor is None:
        return base

    # ON / TN / SN — short-date swaps
    if near_tenor is None and far_tenor.kind in {"ON", "TN", "SN"}:
        if far_tenor.kind == "ON":
            base.near_date = trade_date
            cur = trade_date + timedelta(days=1)
            far_date, far_trace = roll_with_trace(cur, cs, "following")
            base.far_date = far_date
            base.far_trace = far_trace
            return base
        if far_tenor.kind == "TN":
            cur = trade_date + timedelta(days=1)
            near_date, near_trace = roll_with_trace(cur, cs, "following")
            base.near_date = near_date
            base.near_trace = near_trace
            base.far_date = spot.spot_date
            # far is just the spot — no separate trace needed beyond spot_trace.
            return base
        if far_tenor.kind == "SN":
            base.near_date = spot.spot_date
            cur = spot.spot_date + timedelta(days=1)
            far_date, far_trace = roll_with_trace(cur, cs, "following")
            base.far_date = far_date
            base.far_trace = far_trace
            return base

    # PERIOD / IMM / BROKEN — standard far-only forward
    if near_tenor is None:
        if far_tenor.kind == "PERIOD":
            raw_far = add_period(spot.spot_date, far_tenor.period_unit, far_tenor.period_n)
            base.near_date = spot.spot_date
            far_date, far_trace = apply_eom_with_trace(spot.spot_date, raw_far, cs)
            base.far_date = far_date
            base.far_trace = far_trace
            return base
        if far_tenor.kind == "IMM":
            raw_far = next_imm_date(spot.spot_date, far_tenor.imm_index)
            base.near_date = spot.spot_date
            far_date, far_trace = roll_with_trace(raw_far, cs, "modified_following")
            base.far_date = far_date
            base.far_trace = far_trace
            return base
        if far_tenor.kind == "BROKEN":
            base.near_date = spot.spot_date
            far_date, far_trace = roll_with_trace(far_tenor.target_date, cs, "modified_following")
            base.far_date = far_date
            base.far_trace = far_trace
            return base

    # Forward-forward swap (FFS)
    if near_tenor is not None:
        forward_kinds = {"PERIOD", "IMM", "BROKEN"}
        if near_tenor.kind not in forward_kinds or far_tenor.kind not in forward_kinds:
            raise InvalidFFSCombinationError(
                f"FFS requires forward tenors on both legs; got "
                f"near={near_tenor.kind} far={far_tenor.kind}"
            )

        def _resolve_with_trace(t: Tenor) -> tuple[date, list]:
            if t.kind == "PERIOD":
                raw = add_period(spot.spot_date, t.period_unit, t.period_n)
                return apply_eom_with_trace(spot.spot_date, raw, cs)
            if t.kind == "IMM":
                raw = next_imm_date(spot.spot_date, t.imm_index)
                return roll_with_trace(raw, cs, "modified_following")
            return roll_with_trace(t.target_date, cs, "modified_following")

        near_d, near_tr = _resolve_with_trace(near_tenor)
        far_d, far_tr = _resolve_with_trace(far_tenor)
        base.near_date = near_d
        base.near_trace = near_tr
        base.far_date = far_d
        base.far_trace = far_tr
        if base.far_date <= base.near_date:
            raise InvalidFFSCombinationError(
                f"FFS far_date ({base.far_date}) must be after near_date ({base.near_date})"
            )
        return base

    raise NotImplementedError(
        f"Unhandled combination: near={near_tenor!r} far={far_tenor!r}"
    )
