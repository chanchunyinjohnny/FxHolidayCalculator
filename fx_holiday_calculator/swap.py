from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.conventions.business_day import apply_eom, is_good_business_day, roll
from fx_holiday_calculator.conventions.cross import RefCurrency, rtgs_calendar_set
from fx_holiday_calculator.conventions.dates import add_period, next_imm_date
from fx_holiday_calculator.conventions.spot_offset import AdjustmentStep, apply_spot_offset
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
            base.far_date = cur if is_good_business_day(cur, cs) else roll(cur, cs, "following")
            return base
        if far_tenor.kind == "TN":
            cur = trade_date + timedelta(days=1)
            base.near_date = cur if is_good_business_day(cur, cs) else roll(cur, cs, "following")
            base.far_date = spot.spot_date
            return base
        if far_tenor.kind == "SN":
            base.near_date = spot.spot_date
            cur = spot.spot_date + timedelta(days=1)
            base.far_date = cur if is_good_business_day(cur, cs) else roll(cur, cs, "following")
            return base

    # PERIOD / IMM / BROKEN — standard far-only forward
    if near_tenor is None:
        if far_tenor.kind == "PERIOD":
            raw_far = add_period(spot.spot_date, far_tenor.period_unit, far_tenor.period_n)
            base.near_date = spot.spot_date
            base.far_date = apply_eom(spot.spot_date, raw_far, cs)
            return base
        if far_tenor.kind == "IMM":
            raw_far = next_imm_date(spot.spot_date, far_tenor.imm_index)
            base.near_date = spot.spot_date
            base.far_date = roll(raw_far, cs, "modified_following")
            return base
        if far_tenor.kind == "BROKEN":
            base.near_date = spot.spot_date
            base.far_date = roll(far_tenor.target_date, cs, "modified_following")
            return base

    # Forward-forward swap (FFS)
    if near_tenor is not None:
        forward_kinds = {"PERIOD", "IMM", "BROKEN"}
        if near_tenor.kind not in forward_kinds or far_tenor.kind not in forward_kinds:
            raise InvalidFFSCombinationError(
                f"FFS requires forward tenors on both legs; got "
                f"near={near_tenor.kind} far={far_tenor.kind}"
            )

        def _resolve(t: Tenor) -> date:
            if t.kind == "PERIOD":
                raw = add_period(spot.spot_date, t.period_unit, t.period_n)
                return apply_eom(spot.spot_date, raw, cs)
            if t.kind == "IMM":
                raw = next_imm_date(spot.spot_date, t.imm_index)
                return roll(raw, cs, "modified_following")
            return roll(t.target_date, cs, "modified_following")

        base.near_date = _resolve(near_tenor)
        base.far_date = _resolve(far_tenor)
        if base.far_date <= base.near_date:
            raise InvalidFFSCombinationError(
                f"FFS far_date ({base.far_date}) must be after near_date ({base.near_date})"
            )
        return base

    raise NotImplementedError(
        f"Unhandled combination: near={near_tenor!r} far={far_tenor!r}"
    )
