from datetime import datetime
from pathlib import Path

from scripts.sources.cfets_cny import build_payload, parse_document

FIXTURE = Path(__file__).parent / "fixtures" / "sources" / "cfets_cny" / "sample.html"


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
    holidays = parse_document(raw, (2027, 2027))
    assert holidays == []


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
