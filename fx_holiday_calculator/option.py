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

from datetime import timedelta

from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.conventions.business_day import (
    AdjustmentStep,
    CalendarSet,
    apply_eom_with_trace,
    is_good_business_day,
    roll_with_trace,
    statuses_for_date,
)
from fx_holiday_calculator.conventions.cross import RefCurrency, rtgs_calendar_set
from fx_holiday_calculator.conventions.dates import add_period, imm_third_wednesday, next_imm_date
from fx_holiday_calculator.conventions.spot_offset import apply_spot_offset
from fx_holiday_calculator.pairs import Pair
from fx_holiday_calculator.tenor import InvalidTenorError, Tenor

# Listed FX-options expiry: 2 good business days before the 3rd Wednesday of
# the contract month, on the exchange calendar.
#
# Two equivalent spec wordings exist:
#   • CME (option-on-FX-future, e.g. EUOPT): "Trading terminates on the second
#     business day prior to the third Wednesday of the contract month" —
#     anchored on the UNROLLED 3rd Wed.
#   • HKEX USD/CNH Options (CNHO-S-2, July 2022 infosheet): "Expiry Day: Two
#     Trading Days prior to the Final Settlement Day" where Final Settlement
#     Day = "The third Wednesday of the Contract Month. If it is not a
#     Business Day, the Final Settlement Day shall be the next Business Day"
#     — anchored on the ROLLED FSD.
#
# These two wordings produce IDENTICAL dates in every case, because the chain
# of non-BDs between the unrolled 3rd Wed and the rolled FSD is traversed by
# the 2-BD back-count regardless of which end is used as the anchor. We use
# the unrolled-3rd-Wed anchor as the canonical form and cite both specs in
# the reasoning bullet so the user can verify against either.
#
# SGX FX-options spec is not separately verified in v1.x; reasoning surfaces
# that caveat for SGX listed venues.

OptionStyle = Literal["OTC", "LISTED"]


class InvalidOptionStyleError(ValueError):
    pass


class ListedOptionVenueRequiredError(ValueError):
    pass


class VenueCalendarMismatchError(ValueError):
    """Raised when the supplied exchange_calendar's venue does not match the
    declared venue argument — guards against silently computing on the wrong
    exchange while labelling the result with the requested venue."""


def _listed_imm_expiry(
    venue: str,
    contract_month: tuple[int, int],
    exch_cs: CalendarSet,
) -> tuple[date, list[AdjustmentStep], str]:
    """Compute listed-option expiry for an IMM contract month.

    Single algorithm: count 2 good business days backward from the unrolled
    3rd Wednesday of the contract month, on the exchange calendar. Returns
    (expiry_date, back_count_trace, reasoning_note).
    """
    imm_raw = imm_third_wednesday(*contract_month)

    # Back-count 2 good business days on the exchange calendar.
    cur = imm_raw
    good_bd = 0
    back_trace: list[AdjustmentStep] = []
    while good_bd < 2:
        cur = cur - timedelta(days=1)
        is_good = is_good_business_day(cur, exch_cs)
        if is_good:
            good_bd += 1
            decision = "accepted" if good_bd == 2 else "back_count_step"
        else:
            decision = "reject_weekend" if cur.weekday() >= 5 else "reject_holiday"
        back_trace.append(
            AdjustmentStep(
                candidate_date=cur,
                weekday=cur.strftime("%a"),
                statuses=statuses_for_date(cur, exch_cs),
                decision=decision,
            )
        )

    if venue == "CME":
        spec_cite = "CME spec: '2 business days prior to the third Wednesday of the contract month'"
    elif venue == "HKEX":
        spec_cite = (
            "HKEX CNHO-S-2: 'Expiry Day: Two Trading Days prior to the Final "
            "Settlement Day' — back-count from rolled FSD coincides with "
            "back-count from unrolled 3rd Wed, by construction"
        )
    else:
        spec_cite = (
            f"{venue} option spec not separately verified in v1.x; defaulting "
            f"to the 2-BD-before-3rd-Wed rule used by CME and HKEX"
        )
    anchor_note = (
        f"Unrolled 3rd Wed of {contract_month[0]}-{contract_month[1]:02d} "
        f"= {imm_raw.isoformat()}; {spec_cite}."
    )
    return cur, back_trace, anchor_note


@dataclass
class OptionResult:
    trade_date: date
    spot_date: date
    expiry_date: date
    delivery_date: date
    style: OptionStyle
    spot_trace: list[AdjustmentStep]
    expiry_trace: list[AdjustmentStep]
    delivery_trace: list[AdjustmentStep]
    calendars_used: list[str]
    warnings: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)


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
    spot_brief = "RTGS{" + ", ".join(spot_cs.members.keys()) + "}"

    # Build expiry calendar set.
    if style == "OTC":
        expiry_cs = spot_cs
        expiry_brief = spot_brief
    else:
        expiry_cs = CalendarSet(members={venue: exchange_calendar})  # type: ignore[dict-item]
        expiry_brief = f"Exchange{{{venue}}}"

    reasoning: list[str] = []
    reasoning.append(
        f"**Style:** {style}. Spot anchor on {spot_brief} → spot "
        f"{spot_result.spot_date.isoformat()} ({spot_result.spot_date.strftime('%a')})."
    )

    # Raw expiry from spot + tenor.
    if tenor.kind == "PERIOD":
        raw_expiry = add_period(spot_result.spot_date, tenor.period_unit, tenor.period_n)
        expiry_date, expiry_trace = apply_eom_with_trace(
            spot_result.spot_date, raw_expiry, expiry_cs
        )
        reasoning.append(
            f"**Expiry anchor:** spot + {tenor.period_n}{tenor.period_unit} "
            f"= {raw_expiry.isoformat()} ({raw_expiry.strftime('%a')}) (raw); "
            f"rolled modified-following on {expiry_brief} → "
            f"{expiry_date.isoformat()} ({expiry_date.strftime('%a')})."
        )
    elif tenor.kind == "IMM":
        raw_expiry = next_imm_date(spot_result.spot_date, tenor.imm_index)
        if style == "LISTED":
            # Listed options use venue-specific expiry rules (HKEX vs CME vs SGX).
            expiry_date, expiry_trace, anchor_note = _listed_imm_expiry(
                venue,  # type: ignore[arg-type]
                (raw_expiry.year, raw_expiry.month),
                expiry_cs,
            )
            reasoning.append(
                f"**Expiry anchor:** IMM{tenor.imm_index} → contract month "
                f"{raw_expiry.year}-{raw_expiry.month:02d}. {anchor_note} "
                f"Counting back 2 good BDs → {expiry_date.isoformat()} "
                f"({expiry_date.strftime('%a')})."
            )
        else:
            # OTC: traditional "expiry = 3rd Wed rolled mod-following on RTGS".
            expiry_date, expiry_trace = roll_with_trace(
                raw_expiry, expiry_cs, "modified_following"
            )
            reasoning.append(
                f"**Expiry anchor:** IMM{tenor.imm_index} after spot → 3rd Wed of "
                f"{raw_expiry.year}-{raw_expiry.month:02d} = "
                f"{raw_expiry.isoformat()} (raw); rolled modified-following on "
                f"{expiry_brief} → {expiry_date.isoformat()}."
            )
    else:  # BROKEN
        expiry_date, expiry_trace = roll_with_trace(
            tenor.target_date, expiry_cs, "modified_following"  # type: ignore[arg-type]
        )
        reasoning.append(
            f"**Expiry anchor:** user-supplied broken date "
            f"{tenor.target_date.isoformat()} (raw); rolled modified-following on "  # type: ignore[union-attr]
            f"{expiry_brief} → {expiry_date.isoformat()}."
        )

    # Delivery = expiry + pair.spot_offset_days good business days on RTGS{base, quote}.
    # Uses the same machinery as the swap engine's spot offset.
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
        spot_trace=spot_result.trace,
        expiry_trace=expiry_trace,
        delivery_trace=delivery_trace,
        calendars_used=calendars_used,
        warnings=warnings,
        reasoning=reasoning,
    )
