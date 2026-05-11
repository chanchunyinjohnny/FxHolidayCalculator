"""FX futures date math: last trade date and delivery date.

Delivery date is the 3rd Wednesday of the contract month, rolled
modified-following on the combined exchange + base/quote RTGS set.
Last trade date is anchored to the unrolled 3rd Wednesday and is
2 good business days before it (CME Rule 25102.E and analogous rules
on HKEX / SGX).

Conventions: see docs/conventions.md §11.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.conventions.business_day import (
    AdjustmentStep,
    CalendarSet,
    imm_last_trade_date,
    roll_with_trace,
)
from fx_holiday_calculator.conventions.dates import imm_third_wednesday, next_imm_date
from fx_holiday_calculator.pairs import Pair
from fx_holiday_calculator.tenor import InvalidTenorError, Tenor


class VenueNotListedError(ValueError):
    pass


class VenueCalendarMismatchError(ValueError):
    """Raised when the supplied exchange_calendar's venue does not match the
    declared venue argument — guards against silently computing on the wrong
    exchange while labelling the result with the requested venue."""


class InvalidContractMonthError(ValueError):
    pass


@dataclass
class FutureResult:
    contract_month: tuple[int, int]
    venue: str
    last_trade_date: date
    delivery_date: date
    last_trade_trace: list[AdjustmentStep]
    delivery_trace: list[AdjustmentStep]
    calendars_used: list[str]
    warnings: list[str] = field(default_factory=list)


def calculate_future_dates(
    *,
    pair: Pair,
    venue: str,
    contract_month: Optional[tuple[int, int]] = None,
    imm_tenor: Optional[Tenor] = None,
    from_date: Optional[date] = None,
    rtgs_calendars: dict[str, RtgsCalendar],
    exchange_calendar: ExchangeCalendar,
) -> FutureResult:
    if venue not in pair.listed_on:
        raise VenueNotListedError(
            f"{pair.base}/{pair.quote} is not listed on {venue}. "
            f"Listed venues: {pair.listed_on}"
        )
    if exchange_calendar.venue != venue:
        raise VenueCalendarMismatchError(
            f"exchange_calendar.venue={exchange_calendar.venue!r} does not match "
            f"declared venue={venue!r}."
        )
    if contract_month is None and imm_tenor is None:
        raise ValueError("Exactly one of contract_month / imm_tenor must be provided")
    if contract_month is not None and imm_tenor is not None:
        raise ValueError("Provide contract_month OR imm_tenor, not both")

    if imm_tenor is not None:
        if imm_tenor.kind != "IMM":
            raise InvalidTenorError("Futures input only accepts IMM1..IMM4 tenor")
        anchor_date = from_date or date.today()
        imm_date = next_imm_date(anchor_date, imm_tenor.imm_index)
        contract_month = (imm_date.year, imm_date.month)
    assert contract_month is not None  # for type-checker

    today = date.today()
    if (contract_month[0], contract_month[1]) < (today.year, today.month) and from_date is None:
        raise InvalidContractMonthError(f"Contract month {contract_month} is in the past.")

    # Combined calendar set: venue exchange + base + quote RTGS.
    combined_cs = CalendarSet(
        members={
            venue: exchange_calendar,
            pair.base: rtgs_calendars[pair.base],
            pair.quote: rtgs_calendars[pair.quote],
        }  # type: ignore[dict-item]
    )

    # Delivery: 3rd Wed rolled modified-following on combined set.
    anchor = imm_third_wednesday(*contract_month)
    delivery_date, delivery_trace = roll_with_trace(anchor, combined_cs, "modified_following")

    # Last trade date: 2 good BDs back from unrolled 3rd Wed.
    last_trade_date = imm_last_trade_date(contract_month, combined_cs)
    # LTD is by construction a good BD on combined_cs, so roll_with_trace
    # returns a single accepted step — no need to reach for a private helper.
    _, last_trade_trace = roll_with_trace(last_trade_date, combined_cs, "following")

    # Date-aware staleness check: month being "current or future" isn't enough
    # if LTD has already passed (i.e. mid-month after the 2-BD-before-3rd-Wed
    # cutoff). from_date being provided is an explicit override for backtests.
    if from_date is None and last_trade_date < today:
        raise InvalidContractMonthError(
            f"Last trade date {last_trade_date.isoformat()} for contract "
            f"{contract_month} has already passed."
        )

    calendars_used = [venue]
    calendars_used += [
        f"{pair.base} ({rtgs_calendars[pair.base].calendar_name})",
        f"{pair.quote} ({rtgs_calendars[pair.quote].calendar_name})",
    ]

    warnings: list[str] = []

    return FutureResult(
        contract_month=contract_month,
        venue=venue,
        last_trade_date=last_trade_date,
        delivery_date=delivery_date,
        last_trade_trace=last_trade_trace,
        delivery_trace=delivery_trace,
        calendars_used=calendars_used,
        warnings=warnings,
    )
