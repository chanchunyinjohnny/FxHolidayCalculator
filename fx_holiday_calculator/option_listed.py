"""Listed FX-option derivation math: contract month -> expiry + delivery.

Expiry = 2 good business days before the unrolled 3rd Wednesday of the
contract month, on the venue's exchange calendar. Two spec wordings exist
(CME: anchored on unrolled 3rd Wed; HKEX CNHO-S-2: anchored on rolled FSD)
and produce IDENTICAL dates in every case — see docs/conventions.md §10A.

Delivery = expiry + pair.spot_offset_days good business days on
RTGS{base, quote}; the reference currency does not enter the listed path.

This module is invoked at *refresh time* by scripts/sources/<venue>_options_contracts.py,
not at UI time. Runtime listed-option lookups read pre-derived contracts from
data/fx_exchange/<VENUE>_options_contracts.json via fx_holiday_calculator.options.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.conventions.business_day import (
    AdjustmentStep,
    CalendarSet,
    is_good_business_day,
    statuses_for_date,
)
from fx_holiday_calculator.conventions.dates import imm_third_wednesday
from fx_holiday_calculator.conventions.spot_offset import apply_spot_offset
from fx_holiday_calculator.pairs import Pair


class ContractMonthDerivationError(ValueError):
    """Raised when listed-option derivation inputs are inconsistent: venue not
    in pair.listed_on, exchange_calendar venue mismatch, or contract month in
    the past."""


@dataclass
class DeriveContractResult:
    venue: str
    pair: str  # "BASE/QUOTE"
    contract_month: tuple[int, int]
    imm_anchor: date  # unrolled 3rd Wednesday
    expiry_date: date
    delivery_date: date
    expiry_trace: list[AdjustmentStep]
    delivery_trace: list[AdjustmentStep]
    spec_cite: str
    warnings: list[str] = field(default_factory=list)


def _spec_cite(venue: str) -> str:
    if venue == "CME":
        return "CME spec: '2 business days prior to the third Wednesday of the contract month'"
    if venue == "HKEX":
        return (
            "HKEX CNHO-S-2: 'Expiry Day: Two Trading Days prior to the Final "
            "Settlement Day' — back-count from rolled FSD coincides with "
            "back-count from unrolled 3rd Wed, by construction"
        )
    return (
        f"{venue} option spec not separately verified in v1.x; defaulting to "
        "the 2-BD-before-3rd-Wed rule used by CME and HKEX"
    )


def derive_contract(
    *,
    venue: str,
    pair: Pair,
    contract_month: tuple[int, int],
    rtgs_calendars: dict[str, RtgsCalendar],
    exchange_calendar: ExchangeCalendar,
    from_date: Optional[date] = None,
) -> DeriveContractResult:
    if venue not in pair.listed_on:
        raise ContractMonthDerivationError(
            f"{pair.base}/{pair.quote} is not listed on {venue}. "
            f"Listed venues: {pair.listed_on}"
        )
    if exchange_calendar.venue != venue:
        raise ContractMonthDerivationError(
            f"exchange_calendar.venue={exchange_calendar.venue!r} does not match "
            f"declared venue={venue!r}."
        )
    today = date.today()
    if from_date is None and (contract_month[0], contract_month[1]) < (today.year, today.month):
        raise ContractMonthDerivationError(f"Contract month {contract_month} is in the past.")

    imm_raw = imm_third_wednesday(*contract_month)
    exch_cs = CalendarSet(members={venue: exchange_calendar})  # type: ignore[dict-item]

    # Back-count 2 good BDs on the exchange calendar.
    cur = imm_raw
    good_bd = 0
    expiry_trace: list[AdjustmentStep] = []
    while good_bd < 2:
        cur = cur - timedelta(days=1)
        is_good = is_good_business_day(cur, exch_cs)
        if is_good:
            good_bd += 1
            decision = "accepted" if good_bd == 2 else "back_count_step"
        else:
            decision = "reject_weekend" if cur.weekday() >= 5 else "reject_holiday"
        expiry_trace.append(
            AdjustmentStep(
                candidate_date=cur,
                weekday=cur.strftime("%a"),
                statuses=statuses_for_date(cur, exch_cs),
                decision=decision,
            )
        )
    expiry_date = cur

    # Delivery = expiry + pair.spot_offset_days good BDs on RTGS{base, quote}.
    delivery_cs = CalendarSet(
        members={
            pair.base: rtgs_calendars[pair.base],
            pair.quote: rtgs_calendars[pair.quote],
        }
    )
    delivery_result = apply_spot_offset(expiry_date, pair, delivery_cs)

    warnings: list[str] = []
    if expiry_date <= today and from_date is None:
        warnings.append(
            f"Expiry {expiry_date.isoformat()} for contract {contract_month} "
            f"is on or before today; contract has effectively expired."
        )

    return DeriveContractResult(
        venue=venue,
        pair=f"{pair.base}/{pair.quote}",
        contract_month=contract_month,
        imm_anchor=imm_raw,
        expiry_date=expiry_date,
        delivery_date=delivery_result.spot_date,
        expiry_trace=expiry_trace,
        delivery_trace=delivery_result.trace,
        spec_cite=_spec_cite(venue),
        warnings=warnings,
    )
