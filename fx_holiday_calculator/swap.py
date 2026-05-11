from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.conventions.business_day import (
    AdjustmentStep,
    CalendarSet,
    apply_eom_with_trace,
    is_good_business_day,
    roll_with_trace,
)
from fx_holiday_calculator.conventions.cross import (
    RefCurrency,
    combine_calendar_sets,
    exchange_calendar_set,
    rtgs_calendar_set,
)
from fx_holiday_calculator.conventions.dates import add_period, next_imm_date
from fx_holiday_calculator.conventions.spot_offset import apply_spot_offset
from fx_holiday_calculator.pairs import Pair
from fx_holiday_calculator.tenor import Tenor

CalendarMode = Literal["FX", "EXCHANGE", "BOTH"]


class InvalidFFSCombinationError(ValueError):
    pass


class InvalidBrokenDateError(ValueError):
    """Broken-date forward where the requested target falls on or before spot."""


class InvalidTradeDateError(ValueError):
    """Trade date is not a good business day on the chosen calendar set
    (e.g. ON tenor with a weekend or holiday trade date)."""


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
    warnings: list[str] = field(default_factory=list)


def _build_leg_calendar_set(
    pair: Pair,
    ref_currency: RefCurrency,
    calendar_mode: CalendarMode,
    rtgs_cs: CalendarSet,
    exchange_calendars: dict[str, ExchangeCalendar] | None,
) -> CalendarSet:
    if calendar_mode == "FX":
        return rtgs_cs
    ec = exchange_calendars or {}
    exch_cs = exchange_calendar_set(pair, ref_currency, ec)
    if calendar_mode == "EXCHANGE":
        return exch_cs
    return combine_calendar_sets(rtgs_cs, exch_cs)


def calculate_swap_dates(
    *,
    trade_date: date,
    pair: Pair,
    far_tenor: Tenor,
    near_tenor: Tenor | None = None,
    ref_currency: RefCurrency = "USD",
    calendars: dict[str, RtgsCalendar],
    exchange_calendars: dict[str, ExchangeCalendar] | None = None,
    calendar_mode: CalendarMode = "FX",
) -> SwapResult:
    rtgs_cs = rtgs_calendar_set(pair, ref=ref_currency, calendars=calendars)
    # Spot offset is an FX-market concept and always rolls against RTGS.
    spot = apply_spot_offset(trade_date, pair, rtgs_cs)
    # OTC-only tenors (SPOT, ON, TN, SN) never reference exchange calendars
    # regardless of calendar_mode; exchange holidays are a listed-products
    # concern (FX futures / options) and have no bearing on OTC near-dated
    # swaps. For these tenors we force the leg calendar set to RTGS.
    otc_only = far_tenor.kind in {"SPOT", "ON", "TN", "SN"} and near_tenor is None
    if otc_only:
        leg_cs = rtgs_cs
    else:
        leg_cs = _build_leg_calendar_set(
            pair,
            ref_currency,
            calendar_mode,
            rtgs_cs,
            exchange_calendars,
        )

    def _label_for(cal_label: str, cal: object) -> str:
        if isinstance(cal, RtgsCalendar):
            return f"{cal_label} ({cal.calendar_name})"
        if isinstance(cal, ExchangeCalendar):
            return cal.venue
        return cal_label

    labels = [_label_for(k, v) for k, v in leg_cs.members.items()]
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
            if not is_good_business_day(trade_date, leg_cs):
                raise InvalidTradeDateError(
                    f"ON tenor requires trade_date ({trade_date.isoformat()}, "
                    f"{trade_date.strftime('%a')}) to be a good business day "
                    f"on the chosen calendars; it is not."
                )
            base.near_date = trade_date
            cur = trade_date + timedelta(days=1)
            far_date, far_trace = roll_with_trace(cur, leg_cs, "following")
            base.far_date = far_date
            base.far_trace = far_trace
            return base
        if far_tenor.kind == "TN":
            if not is_good_business_day(trade_date, leg_cs):
                # Market practice for TN on a non-business trade date is split:
                # some venues allow it (near rolls to next good BD); others
                # refuse. We allow but warn — see docs/conventions.md.
                base.warnings.append(
                    f"TN trade date {trade_date.isoformat()} "
                    f"({trade_date.strftime('%a')}) is not a good business day "
                    f"on the relevant RTGS calendars; market practice for TN on "
                    f"a non-business day is not universal — verify with your "
                    f"counterparty."
                )
            cur = trade_date + timedelta(days=1)
            near_date, near_trace = roll_with_trace(cur, leg_cs, "following")
            base.near_date = near_date
            base.near_trace = near_trace
            base.far_date = spot.spot_date
            return base
        if far_tenor.kind == "SN":
            base.near_date = spot.spot_date
            cur = spot.spot_date + timedelta(days=1)
            far_date, far_trace = roll_with_trace(cur, leg_cs, "following")
            base.far_date = far_date
            base.far_trace = far_trace
            return base

    # PERIOD / IMM / BROKEN — standard far-only forward
    if near_tenor is None:
        if far_tenor.kind == "PERIOD":
            raw_far = add_period(spot.spot_date, far_tenor.period_unit, far_tenor.period_n)
            base.near_date = spot.spot_date
            far_date, far_trace = apply_eom_with_trace(spot.spot_date, raw_far, leg_cs)
            base.far_date = far_date
            base.far_trace = far_trace
            return base
        if far_tenor.kind == "IMM":
            raw_far = next_imm_date(spot.spot_date, far_tenor.imm_index)
            base.near_date = spot.spot_date
            far_date, far_trace = roll_with_trace(raw_far, leg_cs, "modified_following")
            base.far_date = far_date
            base.far_trace = far_trace
            return base
        if far_tenor.kind == "BROKEN":
            base.near_date = spot.spot_date
            far_date, far_trace = roll_with_trace(
                far_tenor.target_date,
                leg_cs,
                "modified_following",
            )
            if far_date <= spot.spot_date:
                raise InvalidBrokenDateError(
                    f"Broken-date target {far_tenor.target_date.isoformat()} rolls to "
                    f"{far_date.isoformat()}, which is not after spot date "
                    f"{spot.spot_date.isoformat()}."
                )
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
                return apply_eom_with_trace(spot.spot_date, raw, leg_cs)
            if t.kind == "IMM":
                raw = next_imm_date(spot.spot_date, t.imm_index)
                return roll_with_trace(raw, leg_cs, "modified_following")
            return roll_with_trace(t.target_date, leg_cs, "modified_following")

        near_d, near_tr = _resolve_with_trace(near_tenor)
        far_d, far_tr = _resolve_with_trace(far_tenor)
        base.near_date = near_d
        base.near_trace = near_tr
        base.far_date = far_d
        base.far_trace = far_tr
        if base.near_date <= spot.spot_date:
            raise InvalidFFSCombinationError(
                f"FFS near_date ({base.near_date}) must be after spot_date ({spot.spot_date})"
            )
        if base.far_date <= base.near_date:
            raise InvalidFFSCombinationError(
                f"FFS far_date ({base.far_date}) must be after near_date ({base.near_date})"
            )
        return base

    raise NotImplementedError(f"Unhandled combination: near={near_tenor!r} far={far_tenor!r}")
