from datetime import datetime
from pathlib import Path

from scripts.sources.federal_reserve import build_payload, parse_document

FIXTURE = Path(__file__).parent / "fixtures" / "sources" / "federal_reserve" / "sample.html"


def _by_date(holidays):
    return {h["date"]: h for h in holidays}


def test_payload_has_correct_metadata():
    raw = FIXTURE.read_bytes()
    payload = build_payload((2026, 2030), raw)
    assert payload["currency"] == "USD"
    assert payload["calendar_kind"] == "RTGS"
    assert payload["calendar_name"] == "Fedwire"
    src = payload["default_source"]
    assert src["url"].startswith("https://www.federalreserve.gov")
    assert src["doc_title"]
    datetime.fromisoformat(src["fetched_at"].replace("Z", "+00:00"))


def test_2026_independence_day_is_saturday_excluded():
    raw = FIXTURE.read_bytes()
    holidays = parse_document(raw, (2026, 2026))
    by_date = _by_date(holidays)
    # Jul 4 2026 is Saturday (Fed page shows "July 4*"). Per strict rule:
    # NOT a Fedwire closure. Neither Jul 3 (Fri, FRB OPEN) nor Jul 4 (Sat, weekend) is in our list.
    assert "2026-07-03" not in by_date
    assert "2026-07-04" not in by_date


def test_2027_independence_day_is_sunday_observed_monday():
    raw = FIXTURE.read_bytes()
    holidays = parse_document(raw, (2027, 2027))
    by_date = _by_date(holidays)
    # Jul 4 2027 is Sunday (page shows "July 4**"). Per rule: following Monday Jul 5 is closure.
    assert "2027-07-04" not in by_date           # the Sunday itself is not listed
    assert "2027-07-05" in by_date
    assert "Independence Day" in by_date["2027-07-05"]["name"]
    assert by_date["2027-07-05"]["note"]          # note explaining observed Monday


def test_2026_plain_dates_present():
    raw = FIXTURE.read_bytes()
    holidays = parse_document(raw, (2026, 2026))
    by_date = _by_date(holidays)
    # Plain (non-marked) dates should be present as-is for 2026.
    assert by_date.get("2026-01-01", {}).get("name") == "New Year's Day"
    assert by_date.get("2026-01-19", {}).get("name") == "Birthday of Martin Luther King, Jr."
    assert by_date.get("2026-05-25", {}).get("name") == "Memorial Day"
    assert by_date.get("2026-06-19", {}).get("name") == "Juneteenth National Independence Day"
    assert by_date.get("2026-09-07", {}).get("name") == "Labor Day"
    assert by_date.get("2026-10-12", {}).get("name") == "Columbus Day"
    assert by_date.get("2026-11-11", {}).get("name") == "Veterans Day"
    assert by_date.get("2026-11-26", {}).get("name") == "Thanksgiving Day"
    assert by_date.get("2026-12-25", {}).get("name") == "Christmas Day"


def test_2026_year_count():
    """2026 has Jul 4 falling on Saturday -> that holiday excluded.
    11 named holidays - 1 excluded = 10 entries for 2026."""
    raw = FIXTURE.read_bytes()
    holidays = parse_document(raw, (2026, 2026))
    assert len(holidays) == 10


def test_default_source_complete():
    raw = FIXTURE.read_bytes()
    payload = build_payload((2026, 2026), raw)
    src = payload["default_source"]
    assert src["url"]
    assert src["doc_title"]
    assert src["fetched_at"]
    assert src["fetcher"]
