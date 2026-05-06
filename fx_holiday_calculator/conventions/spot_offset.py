from dataclasses import dataclass, field
from datetime import date, timedelta

from fx_holiday_calculator.calendars.types import CalendarStatus
from fx_holiday_calculator.conventions.business_day import CalendarSet, is_good_business_day
from fx_holiday_calculator.pairs import Pair


@dataclass
class AdjustmentStep:
    candidate_date: date
    weekday: str
    statuses: dict[str, CalendarStatus]
    decision: str  # "accepted" | "reject_holiday" | "reject_weekend" | "rolled_eom"


@dataclass
class SpotResult:
    spot_date: date
    trace: list[AdjustmentStep] = field(default_factory=list)


def _statuses(d: date, cs: CalendarSet) -> dict[str, CalendarStatus]:
    out: dict[str, CalendarStatus] = {}
    for label, cal in cs.members.items():
        entry = cal.get_holiday(d) if hasattr(cal, "get_holiday") else None
        if entry is None or not entry.is_closure:
            # Either no entry, or informational entry (not a closure).
            liq = entry.liquidity if entry else None
            out[label] = CalendarStatus(
                is_good=True, holiday_name=None,
                source=None if not entry else entry.source,
                source_origin=None if not entry else entry.source_origin,
                liquidity=liq,
            )
        else:
            out[label] = CalendarStatus(
                is_good=False, holiday_name=entry.name,
                source=entry.source, source_origin=entry.source_origin,
                liquidity=entry.liquidity,
            )
    return out


def apply_spot_offset(trade_date: date, pair: Pair, cs: CalendarSet) -> SpotResult:
    cur = trade_date
    accepted = 0
    trace: list[AdjustmentStep] = []
    while accepted < pair.spot_offset_days:
        cur = cur + timedelta(days=1)
        statuses = _statuses(cur, cs)
        if cur.weekday() >= 5:
            decision = "reject_weekend"
        elif any(not s.is_good for s in statuses.values()):
            decision = "reject_holiday"
        else:
            decision = "accepted"
            accepted += 1
        trace.append(AdjustmentStep(
            candidate_date=cur,
            weekday=cur.strftime("%a"),
            statuses=statuses,
            decision=decision,
        ))
    return SpotResult(spot_date=cur, trace=trace)
