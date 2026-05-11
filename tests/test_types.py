from datetime import date, datetime, timezone

from fx_holiday_calculator.calendars.types import CalendarStatus, HolidayEntry, SourceRef


def _make_source() -> SourceRef:
    return SourceRef(
        url="https://example.com/cal",
        doc_title="Example Calendar 2026",
        fetched_at=datetime(2026, 4, 15, 3, 0, tzinfo=timezone.utc),
        fetcher="scripts/sources/example.py@v1",
    )


def test_holiday_entry_carries_resolved_source():
    src = _make_source()
    entry = HolidayEntry(
        date=date(2026, 1, 1),
        name="New Year's Day",
        note=None,
        source=src,
        source_origin="bundled",
    )
    assert entry.source.url == "https://example.com/cal"
    assert entry.source_origin == "bundled"


def test_calendar_status_holiday():
    src = _make_source()
    status = CalendarStatus(
        is_good=False,
        holiday_name="New Year's Day",
        source=src,
        source_origin="bundled",
    )
    assert status.is_good is False
    assert status.holiday_name == "New Year's Day"
    assert status.source.url == "https://example.com/cal"


def test_calendar_status_good_day_has_no_source():
    status = CalendarStatus(
        is_good=True,
        holiday_name=None,
        source=None,
        source_origin=None,
    )
    assert status.is_good is True
    assert status.source is None
