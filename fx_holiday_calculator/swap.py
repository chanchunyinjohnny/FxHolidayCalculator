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
    reasoning: list[str] = field(default_factory=list)


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


def _fmt(d: date) -> str:
    return f"{d.isoformat()} ({d.strftime('%a')})"


def _adjustment_rule(raw: date, final: date, trace: list[AdjustmentStep]) -> str:
    """Compose a one-line description of which adjustment rule fired.

    Looks at the trace for `rolled_eom` markers and a month-change between raw
    and final to distinguish: no-op, EOM, modified-following forward, and
    modified-following preceding (the post-EOM fallback)."""
    if raw == final:
        return "Raw candidate is already a good business day — no adjustment needed."
    saw_eom = any(s.decision == "rolled_eom" for s in trace)
    if saw_eom and final.month == raw.month:
        return f"End-of-month rule fired (spot is last BD of month) → last BD of target month {_fmt(final)}."
    if final.month != raw.month:
        return (
            f"Modified-following forward roll crossed into the next month; "
            f"switched to preceding-direction roll → {_fmt(final)}."
        )
    return f"Modified-following: rolled forward to next good business day → {_fmt(final)}."


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
    rtgs_brief = "RTGS{" + ", ".join(rtgs_cs.members.keys()) + "}"
    leg_brief = (
        rtgs_brief if calendar_mode == "FX" or otc_only
        else "Exchange{" + ", ".join(
            k for k, v in leg_cs.members.items() if isinstance(v, ExchangeCalendar)
        ) + "}" + (f" ∪ {rtgs_brief}" if calendar_mode == "BOTH" else "")
    )
    base = SwapResult(
        trade_date=trade_date,
        spot_date=spot.spot_date,
        near_date=None,
        far_date=None,
        spot_trace=spot.trace,
        calendars_used=labels,
        calendar_mode=calendar_mode,
    )
    base.reasoning.append(
        f"**Spot offset:** T+{pair.spot_offset_days} on {rtgs_brief} → {_fmt(spot.spot_date)}."
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
            base.reasoning.append(
                f"**ON:** near = trade date {_fmt(trade_date)}; far = T+1 ({_fmt(cur)} raw) "
                f"rolled `following` on {rtgs_brief} → {_fmt(far_date)}."
            )
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
            near_raw = trade_date + timedelta(days=1)
            near_date, near_trace = roll_with_trace(near_raw, leg_cs, "following")
            base.near_date = near_date
            base.near_trace = near_trace
            # TN's "Next" = the BD after near (not the spot date). For T+2 pairs
            # this coincides with spot; for T+1 pairs (USD/CAD) TN collapses
            # onto SN, which is exactly how the interbank market quotes it.
            far_raw = near_date + timedelta(days=1)
            far_date, far_trace = roll_with_trace(far_raw, leg_cs, "following")
            base.far_date = far_date
            base.far_trace = far_trace
            collapse_note = (
                " (T+1 pair → TN ≡ SN, both legs are (spot, spot+1))"
                if pair.spot_offset_days < 2
                else ""
            )
            base.reasoning.append(
                f"**TN:** near = T+1 ({_fmt(near_raw)} raw) rolled `following` on "
                f"{rtgs_brief} → {_fmt(near_date)}; far = near+1 ({_fmt(far_raw)} raw) "
                f"rolled `following` → {_fmt(far_date)}.{collapse_note}"
            )
            return base
        if far_tenor.kind == "SN":
            base.near_date = spot.spot_date
            cur = spot.spot_date + timedelta(days=1)
            far_date, far_trace = roll_with_trace(cur, leg_cs, "following")
            base.far_date = far_date
            base.far_trace = far_trace
            base.reasoning.append(
                f"**SN:** near = spot {_fmt(spot.spot_date)}; far = spot+1 ({_fmt(cur)} raw) "
                f"rolled `following` on {rtgs_brief} → {_fmt(far_date)}."
            )
            return base

    # PERIOD / IMM / BROKEN — standard far-only forward
    if near_tenor is None:
        if far_tenor.kind == "PERIOD":
            raw_far = add_period(spot.spot_date, far_tenor.period_unit, far_tenor.period_n)
            base.near_date = spot.spot_date
            far_date, far_trace = apply_eom_with_trace(spot.spot_date, raw_far, leg_cs)
            base.far_date = far_date
            base.far_trace = far_trace
            base.reasoning.append(
                f"**Far anchor:** spot + {far_tenor.period_n}{far_tenor.period_unit} "
                f"= {_fmt(raw_far)} (raw)."
            )
            base.reasoning.append(
                f"**Far roll on {leg_brief}:** {_adjustment_rule(raw_far, far_date, far_trace)}"
            )
            return base
        if far_tenor.kind == "IMM":
            raw_far = next_imm_date(spot.spot_date, far_tenor.imm_index)
            base.near_date = spot.spot_date
            far_date, far_trace = roll_with_trace(raw_far, leg_cs, "modified_following")
            base.far_date = far_date
            base.far_trace = far_trace
            base.reasoning.append(
                f"**Far anchor:** IMM{far_tenor.imm_index} after spot → 3rd Wed of "
                f"{raw_far.year}-{raw_far.month:02d} = {_fmt(raw_far)} (raw)."
            )
            base.reasoning.append(
                f"**Far roll on {leg_brief}:** {_adjustment_rule(raw_far, far_date, far_trace)}"
            )
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
            base.reasoning.append(
                f"**Far anchor:** user-supplied broken date {_fmt(far_tenor.target_date)} (raw)."
            )
            base.reasoning.append(
                f"**Far roll on {leg_brief}:** {_adjustment_rule(far_tenor.target_date, far_date, far_trace)}"
            )
            return base

    # Forward-forward swap (FFS)
    if near_tenor is not None:
        forward_kinds = {"PERIOD", "IMM", "BROKEN"}
        if near_tenor.kind not in forward_kinds or far_tenor.kind not in forward_kinds:
            raise InvalidFFSCombinationError(
                f"FFS requires forward tenors on both legs; got "
                f"near={near_tenor.kind} far={far_tenor.kind}"
            )

        def _resolve_with_trace(t: Tenor) -> tuple[date, list, date, str]:
            if t.kind == "PERIOD":
                raw = add_period(spot.spot_date, t.period_unit, t.period_n)
                d, tr = apply_eom_with_trace(spot.spot_date, raw, leg_cs)
                return d, tr, raw, f"spot + {t.period_n}{t.period_unit}"
            if t.kind == "IMM":
                raw = next_imm_date(spot.spot_date, t.imm_index)
                d, tr = roll_with_trace(raw, leg_cs, "modified_following")
                return d, tr, raw, f"IMM{t.imm_index} after spot → 3rd Wed of {raw.year}-{raw.month:02d}"
            d, tr = roll_with_trace(t.target_date, leg_cs, "modified_following")
            return d, tr, t.target_date, "user-supplied broken date"

        near_d, near_tr, near_raw, near_anchor = _resolve_with_trace(near_tenor)
        far_d, far_tr, far_raw, far_anchor = _resolve_with_trace(far_tenor)
        base.near_date = near_d
        base.near_trace = near_tr
        base.far_date = far_d
        base.far_trace = far_tr
        base.reasoning.append(
            "**FFS:** both legs anchored on spot (OpenGamma Strata convention)."
        )
        base.reasoning.append(
            f"**Near anchor:** {near_anchor} = {_fmt(near_raw)} (raw); "
            f"{_adjustment_rule(near_raw, near_d, near_tr)}"
        )
        base.reasoning.append(
            f"**Far anchor:** {far_anchor} = {_fmt(far_raw)} (raw); "
            f"{_adjustment_rule(far_raw, far_d, far_tr)}"
        )
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
