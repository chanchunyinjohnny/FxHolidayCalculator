from datetime import datetime
from pathlib import Path

from scripts.sources.cfets_cny import build_payload, parse_document

FIXTURE = Path(__file__).parent / "fixtures" / "sources" / "cfets_cny" / "sample.json"


def _by_date(holidays):
    return {h["date"]: h for h in holidays}


def test_payload_metadata():
    raw = FIXTURE.read_bytes()
    payload = build_payload((2026, 2030), raw)
    assert payload["currency"] == "CNY"
    assert payload["calendar_kind"] == "FIXING"
    assert payload["calendar_name"].startswith("CFETS")
    src = payload["default_source"]
    assert src["url"].startswith("https://")
    assert src["doc_title"]
    datetime.fromisoformat(src["fetched_at"].replace("Z", "+00:00"))


def test_national_day_present():
    raw = FIXTURE.read_bytes()
    holidays = parse_document(raw, (2026, 2026))
    by_date = _by_date(holidays)
    assert "2026-10-01" in by_date
    assert by_date["2026-10-01"]["name"] == "National Day"


def test_year_range_filters_out_of_scope():
    raw = FIXTURE.read_bytes()
    holidays = parse_document(raw, (2024, 2024))
    assert holidays == []


def test_year_range_admits_neighbouring_year():
    raw = FIXTURE.read_bytes()
    holidays = parse_document(raw, (2025, 2025))
    dates = [h["date"] for h in holidays]
    assert "2025-01-01" in dates
    # 2026 dates must not leak in
    assert all(d.startswith("2025-") for d in dates)


def test_holidays_sorted_and_unique():
    raw = FIXTURE.read_bytes()
    holidays = parse_document(raw, (2026, 2026))
    dates = [h["date"] for h in holidays]
    assert dates == sorted(dates)
    assert len(dates) == len(set(dates))


def test_default_source_complete():
    raw = FIXTURE.read_bytes()
    payload = build_payload((2026, 2026), raw)
    src = payload["default_source"]
    assert src["url"]
    assert src["doc_title"]
    assert src["fetched_at"]
    assert src["fetcher"]


def test_validity_window_clamped_to_api_coverage():
    """build_payload clamps valid_until to the latest year actually present
    in the API response, so the FixingCalendar raises CalendarRangeError for
    years CFETS has not yet published rather than silently returning False."""
    raw = FIXTURE.read_bytes()
    payload = build_payload((2026, 2030), raw)
    assert payload["valid_from"] == "2026-01-01"
    assert payload["valid_until"] == "2027-12-31"


def test_unmapped_date_falls_back_to_generic_name():
    """A CFETS-specific closure not in python-holidays should keep a generic
    label rather than crash or carry an empty name."""
    # 2026-05-04 / 2026-05-05 are CFETS make-up / shifted Labour Day closures
    # not always present in python-holidays.China; either way the parser
    # must produce a non-empty name.
    raw = FIXTURE.read_bytes()
    holidays = parse_document(raw, (2026, 2026))
    for h in holidays:
        assert h["name"], f"missing name for {h['date']}"
