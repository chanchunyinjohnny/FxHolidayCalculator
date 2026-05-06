from datetime import date

from fx_holiday_calculator.calendars.national import NationalCalendar, get_national_calendar


def test_us_calendar_recognises_independence_day():
    cal = get_national_calendar("US")
    assert isinstance(cal, NationalCalendar)
    assert cal.is_holiday(date(2026, 7, 4)) is True


def test_us_holiday_entry_carries_library_origin():
    cal = get_national_calendar("US")
    entry = cal.get_holiday(date(2026, 7, 4))
    assert entry is not None
    assert entry.source_origin == "library"
    assert entry.source.url == "https://pypi.org/project/holidays/"
    assert "python-holidays" in entry.source.doc_title
    assert entry.source.doc_title.endswith("calendar=US") or "calendar=US" in entry.source.doc_title
