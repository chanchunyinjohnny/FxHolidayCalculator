from dataclasses import dataclass, field
from datetime import date, timedelta

from fx_holiday_calculator.conventions.business_day import (
    AdjustmentStep,
    CalendarSet,
    is_good_business_day,
    statuses_for_date,
)
from fx_holiday_calculator.pairs import Pair


@dataclass
class SpotResult:
    spot_date: date
    trace: list[AdjustmentStep] = field(default_factory=list)


def apply_spot_offset(trade_date: date, pair: Pair, cs: CalendarSet) -> SpotResult:
    cur = trade_date
    accepted = 0
    trace: list[AdjustmentStep] = []
    while accepted < pair.spot_offset_days:
        cur = cur + timedelta(days=1)
        statuses = statuses_for_date(cur, cs)
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
