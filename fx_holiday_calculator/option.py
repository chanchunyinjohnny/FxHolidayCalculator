"""FX option date math: expiry and delivery.

OTC: spot anchor on RTGS{base, quote, ref}; expiry rolls on the same set;
delivery rolls on RTGS{base, quote} (no reference-currency constraint on
the delivery leg).

Listed: spot anchor on RTGS{base, quote} (ref currency does not enter the
listed-contract path); expiry rolls on the venue's exchange calendar;
delivery rolls on RTGS{base, quote} (cash legs settle bilaterally).

Conventions: see docs/conventions.md §10.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional

from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.conventions.business_day import (
    AdjustmentStep,
    CalendarSet,
    apply_eom_with_trace,
    roll_with_trace,
)
from fx_holiday_calculator.conventions.cross import RefCurrency, rtgs_calendar_set
from fx_holiday_calculator.conventions.dates import add_period, next_imm_date
from fx_holiday_calculator.conventions.spot_offset import apply_spot_offset
from fx_holiday_calculator.pairs import Pair
from fx_holiday_calculator.tenor import InvalidTenorError, Tenor

OptionStyle = Literal["OTC", "LISTED"]


class InvalidOptionStyleError(ValueError):
    pass


class ListedOptionVenueRequiredError(ValueError):
    pass


class VenueCalendarMismatchError(ValueError):
    """Raised when the supplied exchange_calendar's venue does not match the
    declared venue argument — guards against silently computing on the wrong
    exchange while labelling the result with the requested venue."""


@dataclass
class OptionResult:
    trade_date: date
    spot_date: date
    expiry_date: date
    delivery_date: date
    style: OptionStyle
    expiry_trace: list[AdjustmentStep]
    delivery_trace: list[AdjustmentStep]
    calendars_used: list[str]
    warnings: list[str] = field(default_factory=list)


def calculate_option_dates(
    *,
    trade_date: date,
    pair: Pair,
    tenor: Tenor,
    style: OptionStyle,
    ref_currency: RefCurrency = "USD",
    rtgs_calendars: dict[str, RtgsCalendar],
    exchange_calendar: Optional[ExchangeCalendar] = None,
    venue: Optional[str] = None,
) -> OptionResult:
    if style not in ("OTC", "LISTED"):
        raise InvalidOptionStyleError(f"Unknown option style: {style!r}")

    if style == "LISTED":
        if exchange_calendar is None or venue is None or venue not in pair.listed_on:
            raise ListedOptionVenueRequiredError(
                f"LISTED option requires a venue from pair.listed_on={pair.listed_on} "
                f"and a matching exchange_calendar."
            )
        if exchange_calendar.venue != venue:
            raise VenueCalendarMismatchError(
                f"exchange_calendar.venue={exchange_calendar.venue!r} does not match "
                f"declared venue={venue!r}."
            )

    if tenor.kind in {"SPOT", "ON", "TN", "SN"}:
        raise InvalidTenorError("Option requires a forward tenor (PERIOD / IMM / BROKEN).")

    # Spot anchor calendar set differs by style:
    # OTC: ref-aware (base + quote + ref) — full FX cross-spot constraint.
    # LISTED: base + quote only — the exchange contract is venue-defined; the
    # spot anchor is treated as a bilateral base/quote concept and the ref
    # currency does not enter the calculation.
    spot_anchor_ref: RefCurrency = ref_currency if style == "OTC" else "none"
    spot_cs = rtgs_calendar_set(pair, ref=spot_anchor_ref, calendars=rtgs_calendars)
    spot_result = apply_spot_offset(trade_date, pair, spot_cs)

    # Build expiry calendar set.
    if style == "OTC":
        expiry_cs = spot_cs
    else:
        expiry_cs = CalendarSet(members={venue: exchange_calendar})  # type: ignore[dict-item]

    # Raw expiry from spot + tenor.
    if tenor.kind == "PERIOD":
        raw_expiry = add_period(spot_result.spot_date, tenor.period_unit, tenor.period_n)
        expiry_date, expiry_trace = apply_eom_with_trace(
            spot_result.spot_date, raw_expiry, expiry_cs
        )
    elif tenor.kind == "IMM":
        raw_expiry = next_imm_date(spot_result.spot_date, tenor.imm_index)
        expiry_date, expiry_trace = roll_with_trace(raw_expiry, expiry_cs, "modified_following")
    else:  # BROKEN
        expiry_date, expiry_trace = roll_with_trace(
            tenor.target_date, expiry_cs, "modified_following"  # type: ignore[arg-type]
        )

    # Delivery = expiry + pair.spot_offset_days good business days on RTGS{base, quote}.
    # Uses the same machinery as the swap engine's spot offset.
    delivery_cs = CalendarSet(
        members={pair.base: rtgs_calendars[pair.base], pair.quote: rtgs_calendars[pair.quote]}
    )
    delivery_result = apply_spot_offset(expiry_date, pair, delivery_cs)
    delivery_date = delivery_result.spot_date
    delivery_trace = delivery_result.trace

    calendars_used = []
    for label, cal in expiry_cs.members.items():
        if isinstance(cal, RtgsCalendar):
            calendars_used.append(f"{label} ({cal.calendar_name})")
        else:
            calendars_used.append(label)
    for label, cal in delivery_cs.members.items():
        calendars_used.append(f"{label} ({cal.calendar_name})")

    warnings: list[str] = []
    if expiry_date == spot_result.spot_date:
        warnings.append(
            f"Option expires on spot date {expiry_date.isoformat()} — unusual, verify intent."
        )

    return OptionResult(
        trade_date=trade_date,
        spot_date=spot_result.spot_date,
        expiry_date=expiry_date,
        delivery_date=delivery_date,
        style=style,
        expiry_trace=expiry_trace,
        delivery_trace=delivery_trace,
        calendars_used=calendars_used,
        warnings=warnings,
    )
