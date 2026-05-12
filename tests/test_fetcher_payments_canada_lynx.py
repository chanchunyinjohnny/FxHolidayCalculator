from datetime import datetime
from pathlib import Path

from scripts.sources.payments_canada_lynx import build_payload, parse_document

FIXTURE = Path(__file__).parent / "fixtures" / "sources" / "payments_canada_lynx" / "sample.html"


def _by_date(holidays):
    return {h["date"]: h for h in holidays}


def test_payload_metadata():
    raw = FIXTURE.read_bytes()
    p = build_payload((2026, 2030), raw)
    assert p["currency"] == "CAD"
    assert p["calendar_kind"] == "RTGS"
    assert p["calendar_name"] == "Lynx"
    assert p["operator"] == "Payments Canada"
    src = p["default_source"]
    assert src["url"] == "https://www.payments.ca/system-closure-schedule"
    assert src["doc_title"]
    assert src["fetcher"].startswith("scripts/sources/payments_canada_lynx.py@")
    datetime.fromisoformat(src["fetched_at"].replace("Z", "+00:00"))


def test_validity_window_clamped_to_published_years():
    """Payments Canada currently publishes 2026 only; valid_until must
    clamp to 2026 even when callers ask for 2030."""
    raw = FIXTURE.read_bytes()
    p = build_payload((2026, 2030), raw)
    assert p["valid_from"] == "2026-01-01"
    assert p["valid_until"] == "2026-12-31"


def test_2026_known_holidays():
    raw = FIXTURE.read_bytes()
    holidays = parse_document(raw, (2026, 2026))
    by_date = _by_date(holidays)
    # Known 2026 Lynx closures per Payments Canada:
    assert "2026-01-01" in by_date  # New Year's Day
    assert "2026-04-03" in by_date  # Good Friday
    assert "2026-05-18" in by_date  # Victoria Day
    assert "2026-07-01" in by_date  # Canada Day
    assert "2026-09-07" in by_date  # Labour Day
    assert "2026-09-30" in by_date  # National Day for Truth and Reconciliation
    assert "2026-10-12" in by_date  # Thanksgiving
    assert "2026-11-11" in by_date  # Remembrance Day
    assert "2026-12-25" in by_date  # Christmas Day
    # Boxing Day falls Sat 2026-12-26 -> Lynx observes Mon Dec 28
    assert "2026-12-26" not in by_date
    assert "2026-12-28" in by_date
    assert "Boxing Day" in by_date["2026-12-28"]["name"]
    assert by_date["2026-12-28"]["note"]  # substitute-day note preserved


def test_no_other_dates():
    raw = FIXTURE.read_bytes()
    holidays = parse_document(raw, (2026, 2026))
    # Exactly the 10 closures published for 2026 — no more, no less.
    assert len(holidays) == 10


def test_year_range_filtering():
    raw = FIXTURE.read_bytes()
    # 2030 not published -> no entries (page only carries 2026).
    holidays = parse_document(raw, (2030, 2030))
    assert holidays == []


def test_handles_missing_future_years_gracefully():
    raw = FIXTURE.read_bytes()
    # Wide window must not raise and must still return only the 2026 entries.
    holidays = parse_document(raw, (2020, 2035))
    assert isinstance(holidays, list)
    years = {int(h["date"][:4]) for h in holidays}
    assert years == {2026}
