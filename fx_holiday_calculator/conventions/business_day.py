import calendar as _calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal, Protocol


class _CalendarLike(Protocol):
    def is_holiday(self, d: date) -> bool: ...


@dataclass
class CalendarSet:
    """Named calendars; a date is good iff good in ALL members."""
    members: dict[str, _CalendarLike]

    def __iter__(self):
        return iter(self.members.items())


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def is_good_business_day(d: date, cs: CalendarSet) -> bool:
    if _is_weekend(d):
        return False
    for cal in cs.members.values():
        if cal.is_holiday(d):
            return False
    return True


RollMode = Literal["following", "preceding", "modified_following", "modified_preceding"]


def roll(d: date, cs: CalendarSet, mode: RollMode = "modified_following") -> date:
    if is_good_business_day(d, cs):
        return d
    direction = 1 if mode in ("following", "modified_following") else -1
    cur = d
    while True:
        cur = cur + timedelta(days=direction)
        if is_good_business_day(cur, cs):
            break
    if mode == "modified_following" and cur.month != d.month:
        return roll(d, cs, mode="preceding")
    if mode == "modified_preceding" and cur.month != d.month:
        return roll(d, cs, mode="following")
    return cur


def last_business_day_of_month(year: int, month: int, cs: CalendarSet) -> date:
    last_day = _calendar.monthrange(year, month)[1]
    cur = date(year, month, last_day)
    while not is_good_business_day(cur, cs):
        cur = cur - timedelta(days=1)
        if cur.month != month:
            raise RuntimeError(f"No business day found in {year}-{month:02d}")
    return cur


def apply_eom(spot_date: date, raw_far: date, cs: CalendarSet) -> date:
    """Apply end-of-month rule, then mod-following adjustment."""
    spot_eom = last_business_day_of_month(spot_date.year, spot_date.month, cs)
    if spot_date == spot_eom:
        return last_business_day_of_month(raw_far.year, raw_far.month, cs)
    return roll(raw_far, cs, mode="modified_following")
