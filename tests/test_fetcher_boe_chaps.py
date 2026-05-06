from datetime import datetime
from pathlib import Path

from scripts.sources.boe_chaps import build_payload, parse_document

FIXTURE = Path(__file__).parent / "fixtures" / "sources" / "boe_chaps" / "sample.json"


def _by_date(holidays):
    return {h["date"]: h for h in holidays}


def test_payload_metadata():
    raw = FIXTURE.read_bytes()
    p = build_payload((2026, 2026), raw)
    assert p["currency"] == "GBP"
    assert p["calendar_kind"] == "RTGS"
    assert p["calendar_name"] == "CHAPS"
    src = p["default_source"]
    assert src["url"] == "https://www.gov.uk/bank-holidays.json"
    assert src["doc_title"]
    datetime.fromisoformat(src["fetched_at"].replace("Z", "+00:00"))


def test_2026_known_holidays():
    raw = FIXTURE.read_bytes()
    holidays = parse_document(raw, (2026, 2026))
    by_date = _by_date(holidays)
    # Known 2026 E&W bank holidays (per gov.uk feed):
    assert "2026-01-01" in by_date          # New Year's Day
    assert "2026-04-03" in by_date          # Good Friday
    assert "2026-04-06" in by_date          # Easter Monday
    assert "2026-05-04" in by_date          # Early May bank holiday
    assert "2026-05-25" in by_date          # Spring bank holiday
    assert "2026-08-31" in by_date          # Summer bank holiday
    assert "2026-12-25" in by_date          # Christmas Day
    # Boxing Day 2026 falls Sat -> substitute Mon Dec 28
    assert "2026-12-28" in by_date
    assert "Boxing Day" in by_date["2026-12-28"]["name"]
    assert by_date["2026-12-28"]["note"]    # gov.uk's "Substitute day" preserved


def test_only_england_and_wales_division():
    raw = FIXTURE.read_bytes()
    holidays = parse_document(raw, (2026, 2026))
    # Scotland-only "St Andrew's Day" (Nov 30) must NOT appear
    by_date = _by_date(holidays)
    assert "2026-11-30" not in by_date


def test_year_range_filtering():
    raw = FIXTURE.read_bytes()
    holidays_2026 = parse_document(raw, (2026, 2026))
    years = {int(h["date"][:4]) for h in holidays_2026}
    assert years == {2026}


def test_handles_missing_future_years_gracefully():
    """gov.uk currently has data through 2028. Asking for 2029-2030 should
    return an empty list (or whatever the JSON contains), not crash."""
    raw = FIXTURE.read_bytes()
    holidays = parse_document(raw, (2030, 2030))
    # Either empty (gov.uk hasn't published 2030 yet) or some entries -- both acceptable.
    # The contract is: it should not raise.
    assert isinstance(holidays, list)
