from datetime import date, datetime, timezone

from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import HolidayEntry, SourceRef
from fx_holiday_calculator.conventions.business_day import (
    CalendarSet,
    apply_eom,
    apply_eom_with_trace,
    is_good_business_day,
    last_business_day_of_month,
    roll,
    roll_with_trace,
)


def _cal(currency: str, holidays: list[date]) -> RtgsCalendar:
    src = SourceRef(
        url="https://x",
        doc_title="x",
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        fetcher="test",
    )
    entries = {
        d: HolidayEntry(date=d, name="X", note=None, source=src, source_origin="bundled")
        for d in holidays
    }
    return RtgsCalendar(
        currency=currency,
        calendar_name=currency,
        operator="x",
        entries_by_date=entries,
        valid_from=date(2020, 1, 1),
        valid_until=date(2030, 12, 31),
    )


def test_weekend_is_not_good_business_day():
    eur = _cal("EUR", [])
    cs = CalendarSet({"EUR (TARGET2)": eur})
    assert is_good_business_day(date(2026, 5, 9), cs) is False  # Saturday
    assert is_good_business_day(date(2026, 5, 10), cs) is False  # Sunday
    assert is_good_business_day(date(2026, 5, 11), cs) is True  # Monday


def test_holiday_in_any_calendar_disqualifies():
    eur = _cal("EUR", [date(2026, 5, 11)])
    jpy = _cal("JPY", [])
    cs = CalendarSet({"EUR (TARGET2)": eur, "JPY (BoJ)": jpy})
    assert is_good_business_day(date(2026, 5, 11), cs) is False
    assert is_good_business_day(date(2026, 5, 12), cs) is True


def test_following_skips_weekend():
    cs = CalendarSet({"EUR": _cal("EUR", [])})
    assert roll(date(2026, 5, 9), cs, mode="following") == date(2026, 5, 11)


def test_modified_following_falls_back_when_crossing_month_end():
    # 2026-05-30 (Sat), 2026-05-31 (Sun), 2026-06-01 (Mon, but assume holiday)
    cs = CalendarSet({"EUR": _cal("EUR", [date(2026, 6, 1)])})
    # following would give 2026-06-02, but mod-following should fall back to 2026-05-29 (Fri).
    assert roll(date(2026, 5, 31), cs, mode="modified_following") == date(2026, 5, 29)


def test_last_business_day_of_month():
    cs = CalendarSet({"EUR": _cal("EUR", [date(2026, 5, 29)])})
    # May 30/31 are weekend; May 29 is a holiday → last business day is May 28.
    assert last_business_day_of_month(2026, 5, cs) == date(2026, 5, 28)


def test_apply_eom_rolls_far_to_month_end_when_spot_is_month_end():
    cs = CalendarSet({"EUR": _cal("EUR", [])})
    # Spot 2026-05-29 (Fri) is the last BD of May; far raw = 2026-08-29 (Sat).
    # EOM rule rolls far to last BD of August (2026-08-31 Mon).
    spot = date(2026, 5, 29)
    raw_far = date(2026, 8, 29)
    assert apply_eom(spot, raw_far, cs) == date(2026, 8, 31)


def test_apply_eom_passes_through_when_spot_not_month_end():
    cs = CalendarSet({"EUR": _cal("EUR", [])})
    spot = date(2026, 5, 14)  # mid-month
    raw_far = date(2026, 8, 14)
    assert apply_eom(spot, raw_far, cs) == raw_far


def test_roll_with_trace_already_good():
    cs = CalendarSet({"EUR": _cal("EUR", [])})
    result_date, trace = roll_with_trace(date(2026, 5, 11), cs, mode="following")
    # 2026-05-11 is Mon, no holidays → already good
    assert result_date == date(2026, 5, 11)
    assert len(trace) == 1
    assert trace[0].decision == "accepted"


def test_roll_with_trace_weekend_rejection():
    cs = CalendarSet({"EUR": _cal("EUR", [])})
    result_date, trace = roll_with_trace(date(2026, 5, 9), cs, mode="following")
    # Sat → Sun → Mon
    assert result_date == date(2026, 5, 11)
    assert len(trace) == 3
    assert trace[0].decision == "reject_weekend"
    assert trace[1].decision == "reject_weekend"
    assert trace[2].decision == "accepted"


def test_roll_with_trace_holiday_rejection():
    cs = CalendarSet({"EUR": _cal("EUR", [date(2026, 5, 11)])})
    result_date, trace = roll_with_trace(date(2026, 5, 11), cs, mode="following")
    # Mon is holiday → Tue accepted
    assert result_date == date(2026, 5, 12)
    assert trace[0].decision == "reject_holiday"
    assert trace[-1].decision == "accepted"


def test_apply_eom_with_trace_passes_through():
    cs = CalendarSet({"EUR": _cal("EUR", [])})
    spot = date(2026, 5, 14)  # mid-month
    raw_far = date(2026, 8, 14)  # Fri, no holidays → already good
    result_date, trace = apply_eom_with_trace(spot, raw_far, cs)
    assert result_date == raw_far
    assert len(trace) == 1
    assert trace[0].decision == "accepted"


def test_apply_eom_with_trace_eom_kick_in():
    cs = CalendarSet({"EUR": _cal("EUR", [])})
    # Spot 2026-05-29 (Fri) is last BD of May.
    # Raw far 2026-08-29 (Sat). EOM rule → last BD of Aug = 2026-08-31 Mon.
    spot = date(2026, 5, 29)
    raw_far = date(2026, 8, 29)
    result_date, trace = apply_eom_with_trace(spot, raw_far, cs)
    assert result_date == date(2026, 8, 31)
    # Two steps: rolled_eom at raw_far, accepted at target
    assert len(trace) == 2
    assert trace[0].decision == "rolled_eom"
    assert trace[1].decision == "accepted"
