"""OTC FX option date math: expiry and delivery.

OTC: spot anchor on RTGS{base, quote, ref}; expiry rolls on the same set;
delivery rolls on RTGS{base, quote} (no reference-currency constraint on
the delivery leg).

Conventions: see docs/conventions.md §10.

Listed options live in `option_listed.py` (derivation) and `options.py`
(lookup facade). This module handles OTC only.
"""
from dataclasses import dataclass, field
from datetime import date

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


@dataclass
class OtcOptionResult:
    trade_date: date
    spot_date: date
    expiry_date: date
    delivery_date: date
    spot_trace: list[AdjustmentStep]
    expiry_trace: list[AdjustmentStep]
    delivery_trace: list[AdjustmentStep]
    calendars_used: list[str]
    warnings: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)


def calculate_otc_option_dates(
    *,
    trade_date: date,
    pair: Pair,
    tenor: Tenor,
    ref_currency: RefCurrency = "USD",
    rtgs_calendars: dict[str, RtgsCalendar],
) -> OtcOptionResult:
    if tenor.kind in {"SPOT", "ON", "TN", "SN"}:
        raise InvalidTenorError("OTC option requires a forward tenor (PERIOD / IMM / BROKEN).")

    spot_cs = rtgs_calendar_set(pair, ref=ref_currency, calendars=rtgs_calendars)
    spot_result = apply_spot_offset(trade_date, pair, spot_cs)
    spot_brief = "RTGS{" + ", ".join(spot_cs.members.keys()) + "}"

    reasoning: list[str] = [
        f"**Style:** OTC. Spot anchor on {spot_brief} → spot "
        f"{spot_result.spot_date.isoformat()} ({spot_result.spot_date.strftime('%a')})."
    ]

    if tenor.kind == "PERIOD":
        raw_expiry = add_period(spot_result.spot_date, tenor.period_unit, tenor.period_n)
        expiry_date, expiry_trace = apply_eom_with_trace(spot_result.spot_date, raw_expiry, spot_cs)
        reasoning.append(
            f"**Expiry anchor:** spot + {tenor.period_n}{tenor.period_unit} "
            f"= {raw_expiry.isoformat()} ({raw_expiry.strftime('%a')}) (raw); "
            f"rolled modified-following on {spot_brief} → "
            f"{expiry_date.isoformat()} ({expiry_date.strftime('%a')})."
        )
    elif tenor.kind == "IMM":
        raw_expiry = next_imm_date(spot_result.spot_date, tenor.imm_index)
        expiry_date, expiry_trace = roll_with_trace(raw_expiry, spot_cs, "modified_following")
        reasoning.append(
            f"**Expiry anchor:** IMM{tenor.imm_index} after spot → 3rd Wed of "
            f"{raw_expiry.year}-{raw_expiry.month:02d} = "
            f"{raw_expiry.isoformat()} (raw); rolled modified-following on "
            f"{spot_brief} → {expiry_date.isoformat()}."
        )
    else:  # BROKEN
        expiry_date, expiry_trace = roll_with_trace(
            tenor.target_date,  # type: ignore[arg-type]
            spot_cs,
            "modified_following",
        )
        reasoning.append(
            f"**Expiry anchor:** user-supplied broken date "
            f"{tenor.target_date.isoformat()} (raw); rolled modified-following on "  # type: ignore[union-attr]
            f"{spot_brief} → {expiry_date.isoformat()}."
        )

    delivery_cs = CalendarSet(
        members={pair.base: rtgs_calendars[pair.base], pair.quote: rtgs_calendars[pair.quote]}
    )
    delivery_result = apply_spot_offset(expiry_date, pair, delivery_cs)
    delivery_date = delivery_result.spot_date
    delivery_trace = delivery_result.trace
    reasoning.append(
        f"**Delivery:** expiry + {pair.spot_offset_days} good BD on "
        f"RTGS{{{pair.base}, {pair.quote}}} (no ref — cash legs are bilateral) "
        f"→ {delivery_date.isoformat()} ({delivery_date.strftime('%a')})."
    )

    calendars_used: list[str] = []
    for label, cal in spot_cs.members.items():
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

    return OtcOptionResult(
        trade_date=trade_date,
        spot_date=spot_result.spot_date,
        expiry_date=expiry_date,
        delivery_date=delivery_date,
        spot_trace=spot_result.trace,
        expiry_trace=expiry_trace,
        delivery_trace=delivery_trace,
        calendars_used=calendars_used,
        warnings=warnings,
        reasoning=reasoning,
    )
