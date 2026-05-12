"""NDF date math.

Non-deliverable forwards settle in USD only; the non-deliverable side fixes
against a primary-source fixing rate (CFETS for CNY, KFTC for KRW, Taipei
Forex for TWD). This module computes spot, settlement, and fixing dates
with full provenance traces.

Conventions: see docs/conventions.md §9.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from fx_holiday_calculator.calendars.fixing import FixingCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.conventions.business_day import (
    AdjustmentStep,
    CalendarSet,
    _step_for,
    is_good_business_day,
    last_business_day_of_month,
    roll_with_trace,
)
from fx_holiday_calculator.conventions.dates import add_period, next_imm_date
from fx_holiday_calculator.conventions.spot_offset import apply_spot_offset
from fx_holiday_calculator.pairs import Pair
from fx_holiday_calculator.tenor import InvalidTenorError, Tenor


class InvalidNdfPairError(ValueError):
    """Raised when calculate_ndf_dates is given a deliverable pair."""


class InvalidTradeDateError(ValueError):
    """Trade date is not a good USD-RTGS business day."""


class InvalidBrokenDateError(ValueError):
    """Settlement date rolls to <= spot."""


@dataclass
class NdfResult:
    trade_date: date
    spot_date: date
    fixing_date: date
    settlement_date: date
    spot_trace: list[AdjustmentStep]
    settlement_trace: list[AdjustmentStep]
    fixing_trace: list[AdjustmentStep]
    calendars_used: list[str]
    warnings: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)


def calculate_ndf_dates(
    *,
    trade_date: date,
    pair: Pair,
    tenor: Optional[Tenor] = None,
    target_settlement: Optional[date] = None,
    rtgs_calendars: dict[str, RtgsCalendar],
    fixing_calendar: FixingCalendar,
) -> NdfResult:
    if not pair.ndf:
        raise InvalidNdfPairError(
            f"{pair.base}/{pair.quote} is not configured as an NDF pair " f"(pair.ndf is False)."
        )
    # USD-only RTGS set for spot offset and settlement.
    if "USD" not in rtgs_calendars:
        raise KeyError("rtgs_calendars must contain 'USD'")
    usd = rtgs_calendars["USD"]
    usd_cs = CalendarSet(members={"USD": usd})

    # Combined USD + fixing for settlement roll.
    settle_cs = CalendarSet(
        members={"USD": usd, pair.fixing_currency: fixing_calendar}  # type: ignore[dict-item]
    )

    # Fixing-only set for back-counting fixing date.
    fixing_cs = CalendarSet(members={pair.fixing_currency: fixing_calendar})  # type: ignore[dict-item]

    if not is_good_business_day(trade_date, usd_cs):
        raise InvalidTradeDateError(
            f"Trade date {trade_date.isoformat()} is not a good USD-RTGS day."
        )

    spot_result = apply_spot_offset(trade_date, pair, usd_cs)

    # Resolve target settlement either from tenor or from user-supplied target.
    if tenor is None and target_settlement is None:
        raise ValueError("Exactly one of tenor / target_settlement must be provided")
    if tenor is not None and target_settlement is not None:
        raise ValueError("Provide tenor OR target_settlement, not both")

    reasoning: list[str] = []
    reasoning.append(
        f"**Spot offset:** T+{pair.spot_offset_days} on USD RTGS only "
        f"(non-deliverable side has no settlement leg) → "
        f"{spot_result.spot_date.isoformat()} ({spot_result.spot_date.strftime('%a')})."
    )
    settle_brief = f"USD RTGS ∪ {pair.fixing_currency} fixing"

    if tenor is not None:
        if tenor.kind in {"SPOT", "ON", "TN", "SN"}:
            raise InvalidTenorError("NDF requires a forward tenor (PERIOD / IMM / BROKEN).")
        if tenor.kind == "PERIOD":
            raw_settlement = add_period(spot_result.spot_date, tenor.period_unit, tenor.period_n)
            # EOM rule must be keyed against the calendar that defined spot
            # (USD-only here) — NOT the settle calendar set, which may have
            # a different last-BD-of-month due to fixing-currency holidays.
            spot_eom = last_business_day_of_month(
                spot_result.spot_date.year,
                spot_result.spot_date.month,
                usd_cs,
            )
            if spot_result.spot_date == spot_eom:
                # EOM rule fires: target last good BD of settlement month on settle_cs.
                settlement = last_business_day_of_month(
                    raw_settlement.year, raw_settlement.month, settle_cs
                )
                settle_trace = [
                    _step_for(raw_settlement, settle_cs, "rolled_eom"),
                    _step_for(settlement, settle_cs, "accepted"),
                ]
                reasoning.append(
                    f"**Settlement anchor:** spot + {tenor.period_n}{tenor.period_unit} "
                    f"= {raw_settlement.isoformat()} (raw); EOM rule fired (spot is "
                    f"last BD of month on USD RTGS) → last BD of target month on "
                    f"{settle_brief} = {settlement.isoformat()}."
                )
            else:
                settlement, settle_trace = roll_with_trace(
                    raw_settlement, settle_cs, "modified_following"
                )
                reasoning.append(
                    f"**Settlement anchor:** spot + {tenor.period_n}{tenor.period_unit} "
                    f"= {raw_settlement.isoformat()} (raw); rolled modified-following "
                    f"on {settle_brief} → {settlement.isoformat()}."
                )
        elif tenor.kind == "IMM":
            raw_settlement = next_imm_date(spot_result.spot_date, tenor.imm_index)
            settlement, settle_trace = roll_with_trace(
                raw_settlement, settle_cs, "modified_following"
            )
            reasoning.append(
                f"**Settlement anchor:** IMM{tenor.imm_index} after spot → 3rd Wed of "
                f"{raw_settlement.year}-{raw_settlement.month:02d} = "
                f"{raw_settlement.isoformat()} (raw); rolled modified-following on "
                f"{settle_brief} → {settlement.isoformat()}."
            )
        else:  # BROKEN
            settlement, settle_trace = roll_with_trace(
                tenor.target_date, settle_cs, "modified_following"  # type: ignore[arg-type]
            )
            reasoning.append(
                f"**Settlement anchor:** user-supplied broken date "
                f"{tenor.target_date.isoformat()} (raw); rolled modified-following on "  # type: ignore[union-attr]
                f"{settle_brief} → {settlement.isoformat()}."
            )
    else:
        settlement, settle_trace = roll_with_trace(
            target_settlement,  # type: ignore[arg-type]
            settle_cs,
            "modified_following",
        )
        reasoning.append(
            f"**Settlement anchor:** user-supplied target "
            f"{target_settlement.isoformat()} (raw); rolled modified-following on "  # type: ignore[union-attr]
            f"{settle_brief} → {settlement.isoformat()}."
        )

    if settlement <= spot_result.spot_date:
        raise InvalidBrokenDateError(
            f"NDF settlement rolls to {settlement.isoformat()}, "
            f"which is not after spot {spot_result.spot_date.isoformat()}."
        )

    # Back-count fixing = settlement - 2 BD on the fixing calendar.
    fixing_trace: list[AdjustmentStep] = []
    fixing_candidate = settlement
    good_bd_count = 0
    while good_bd_count < 2:
        fixing_candidate = fixing_candidate - timedelta(days=1)
        if is_good_business_day(fixing_candidate, fixing_cs):
            good_bd_count += 1
    fixing_date, fix_roll_trace = roll_with_trace(fixing_candidate, fixing_cs, "preceding")
    fixing_trace.extend(fix_roll_trace)
    reasoning.append(
        f"**Fixing date:** settlement − 2 good business days on "
        f"{pair.fixing_currency} fixing calendar → {fixing_date.isoformat()} "
        f"({fixing_date.strftime('%a')}). 2-BD lag matches EMTA / ISDA EM template."
    )

    calendars_used = [
        f"USD ({usd.calendar_name})",
        f"{fixing_calendar.currency} ({fixing_calendar.calendar_name})",
    ]

    warnings: list[str] = []
    if (fixing_date - trade_date).days < 2:
        warnings.append(
            f"Short fixing horizon: fixing date {fixing_date.isoformat()} is within 2 "
            f"days of trade date {trade_date.isoformat()}. Confirm with counterparty."
        )

    return NdfResult(
        trade_date=trade_date,
        spot_date=spot_result.spot_date,
        fixing_date=fixing_date,
        settlement_date=settlement,
        spot_trace=spot_result.trace,
        settlement_trace=settle_trace,
        fixing_trace=fixing_trace,
        calendars_used=calendars_used,
        warnings=warnings,
        reasoning=reasoning,
    )
