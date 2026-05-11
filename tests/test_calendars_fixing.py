from datetime import date, datetime, timezone

import pytest

from fx_holiday_calculator.calendars.fixing import FixingCalendar
from fx_holiday_calculator.calendars.types import (
    CalendarRangeError,
    HolidayEntry,
    SourceRef,
)


def _src() -> SourceRef:
    return SourceRef(
        url="https://x",
        doc_title="x",
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        fetcher="t",
    )


def _entry(d: date, name: str = "Holiday") -> HolidayEntry:
    return HolidayEntry(
        date=d,
        name=name,
        note=None,
        source=_src(),
        source_origin="bundled",
        is_closure=True,
    )


def test_fixing_calendar_is_holiday_true_when_present():
    cal = FixingCalendar(
        currency="CNY",
        calendar_name="CFETS",
        operator="PBoC",
        entries_by_date={date(2026, 10, 1): _entry(date(2026, 10, 1), "National Day")},
        valid_from=date(2026, 1, 1),
        valid_until=date(2026, 12, 31),
    )
    assert cal.is_holiday(date(2026, 10, 1)) is True
    assert cal.is_holiday(date(2026, 10, 2)) is False


def test_fixing_calendar_get_holiday_returns_entry():
    e = _entry(date(2026, 10, 1), "National Day")
    cal = FixingCalendar(
        currency="CNY",
        calendar_name="CFETS",
        operator="PBoC",
        entries_by_date={date(2026, 10, 1): e},
        valid_from=date(2026, 1, 1),
        valid_until=date(2026, 12, 31),
    )
    assert cal.get_holiday(date(2026, 10, 1)) is e
    assert cal.get_holiday(date(2026, 10, 2)) is None


def test_fixing_calendar_raises_on_out_of_range_query():
    cal = FixingCalendar(
        currency="CNY",
        calendar_name="CFETS",
        operator="PBoC",
        entries_by_date={},
        valid_from=date(2026, 1, 1),
        valid_until=date(2026, 12, 31),
    )
    with pytest.raises(CalendarRangeError):
        cal.is_holiday(date(2025, 12, 31))
    with pytest.raises(CalendarRangeError):
        cal.is_holiday(date(2027, 1, 1))


def test_fixing_calendar_label_includes_currency_and_name():
    cal = FixingCalendar(
        currency="CNY",
        calendar_name="CFETS USD/CNY Central Parity",
        operator="PBoC",
        entries_by_date={},
        valid_from=date(2026, 1, 1),
        valid_until=date(2026, 12, 31),
    )
    try:
        cal.is_holiday(date(2025, 1, 1))
    except CalendarRangeError as exc:
        assert "CNY" in exc.calendar_label
        assert "CFETS" in exc.calendar_label


def test_fixing_calendar_library_sourced_field_defaults_false():
    cal = FixingCalendar(
        currency="CNY",
        calendar_name="x",
        operator="x",
        entries_by_date={},
        valid_from=date(2026, 1, 1),
        valid_until=date(2026, 12, 31),
    )
    assert cal.library_sourced is False


def test_fixing_calendar_library_sourced_field_can_be_set():
    cal = FixingCalendar(
        currency="CNY",
        calendar_name="x",
        operator="x",
        entries_by_date={},
        valid_from=date(2026, 1, 1),
        valid_until=date(2026, 12, 31),
        library_sourced=True,
    )
    assert cal.library_sourced is True
