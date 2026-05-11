import calendar as _calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal, Protocol

from fx_holiday_calculator.calendars.types import CalendarStatus


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


@dataclass
class AdjustmentStep:
    candidate_date: date
    weekday: str
    statuses: dict[str, CalendarStatus]
    decision: str  # "accepted" | "reject_holiday" | "reject_weekend" | "rolled_eom"


def statuses_for_date(d: date, cs: CalendarSet) -> dict[str, CalendarStatus]:
    """Per-calendar status snapshot for a given date.

    For each calendar in the set, returns a CalendarStatus indicating
    whether the date is good and (if not) the holiday name + provenance.
    Liquidity flag is propagated even on good days (informational entries).
    """
    out: dict[str, CalendarStatus] = {}
    for label, cal in cs.members.items():
        entry = cal.get_holiday(d) if hasattr(cal, "get_holiday") else None
        if entry is None or not entry.is_closure:
            liq = entry.liquidity if entry else None
            out[label] = CalendarStatus(
                is_good=True,
                holiday_name=None,
                source=None if not entry else entry.source,
                source_origin=None if not entry else entry.source_origin,
                liquidity=liq,
            )
        else:
            out[label] = CalendarStatus(
                is_good=False,
                holiday_name=entry.name,
                source=entry.source,
                source_origin=entry.source_origin,
                liquidity=entry.liquidity,
            )
    return out


def _step_for(d: date, cs: CalendarSet, decision: str) -> AdjustmentStep:
    return AdjustmentStep(
        candidate_date=d,
        weekday=d.strftime("%a"),
        statuses=statuses_for_date(d, cs),
        decision=decision,
    )


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


def roll_with_trace(
    d: date, cs: CalendarSet, mode: RollMode = "modified_following"
) -> tuple[date, list[AdjustmentStep]]:
    """Like roll(), but also returns a trace of every candidate considered.

    Always emits at least one step. If `d` is already a good business day,
    the trace is a single accepted step at `d`. Otherwise candidates are
    walked in the appropriate direction and each rejection is recorded.

    For modified_following / modified_preceding, when the forward direction
    crosses a month boundary, an explicit `rolled_eom` step is emitted at
    the original date and the trace is then extended with a preceding-direction
    walk.
    """
    trace: list[AdjustmentStep] = []
    if is_good_business_day(d, cs):
        trace.append(_step_for(d, cs, "accepted"))
        return d, trace

    # First step: rejection at d
    if _is_weekend(d):
        trace.append(_step_for(d, cs, "reject_weekend"))
    else:
        trace.append(_step_for(d, cs, "reject_holiday"))

    direction = 1 if mode in ("following", "modified_following") else -1
    cur = d
    while True:
        cur = cur + timedelta(days=direction)
        if is_good_business_day(cur, cs):
            trace.append(_step_for(cur, cs, "accepted"))
            break
        if _is_weekend(cur):
            trace.append(_step_for(cur, cs, "reject_weekend"))
        else:
            trace.append(_step_for(cur, cs, "reject_holiday"))

    if mode == "modified_following" and cur.month != d.month:
        # Forward roll crossed month boundary; switch direction.
        trace.append(_step_for(d, cs, "rolled_eom"))
        new_date, prec_trace = roll_with_trace(d, cs, "preceding")
        trace.extend(prec_trace)
        return new_date, trace
    if mode == "modified_preceding" and cur.month != d.month:
        trace.append(_step_for(d, cs, "rolled_eom"))
        new_date, fwd_trace = roll_with_trace(d, cs, "following")
        trace.extend(fwd_trace)
        return new_date, trace
    return cur, trace


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


def apply_eom_with_trace(
    spot_date: date, raw_far: date, cs: CalendarSet
) -> tuple[date, list[AdjustmentStep]]:
    """Like apply_eom(), but returns a trace of candidates considered.

    When the EOM rule kicks in, the trace shows a `rolled_eom` step at
    `raw_far` and then a single accepted step at the last business day
    of the target month. When the EOM rule does NOT kick in, the trace
    is the same as `roll_with_trace(raw_far, cs, modified_following)`.
    """
    spot_eom = last_business_day_of_month(spot_date.year, spot_date.month, cs)
    if spot_date == spot_eom:
        target = last_business_day_of_month(raw_far.year, raw_far.month, cs)
        trace = [
            _step_for(raw_far, cs, "rolled_eom"),
            _step_for(target, cs, "accepted"),
        ]
        return target, trace
    return roll_with_trace(raw_far, cs, mode="modified_following")


def imm_last_trade_date(contract_month: tuple[int, int], cs: CalendarSet) -> date:
    """Compute the FX-futures last trade date: 2 good business days before the
    unrolled 3rd Wednesday of `contract_month`, on the supplied calendar set.

    Used by all three venues in v1.1 (CME, HKEX, SGX) — see CME Rule 25102.E
    for the EUR/USD canonical example. The unrolled 3rd Wed is the anchor,
    not the rolled delivery date: LTD does not chain off delivery.
    """
    from fx_holiday_calculator.conventions.dates import imm_third_wednesday

    year, month = contract_month
    anchor = imm_third_wednesday(year, month)
    cur = anchor
    good_count = 0
    while good_count < 2:
        cur = cur - timedelta(days=1)
        if is_good_business_day(cur, cs):
            good_count += 1
    return cur
