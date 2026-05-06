from datetime import datetime
from pathlib import Path

from scripts.sources.boj import build_payload, parse_document

FIXTURE = Path(__file__).parent / "fixtures" / "sources" / "boj" / "sample.html"


def _by_date(holidays):
    return {h["date"]: h for h in holidays}


def test_payload_metadata():
    raw = FIXTURE.read_bytes()
    p = build_payload((2026, 2026), raw)
    assert p["currency"] == "JPY"
    assert p["calendar_kind"] == "RTGS"
    assert p["calendar_name"] == "BoJ-NET"
    src = p["default_source"]
    assert src["url"].startswith("https://www.boj.or.jp")
    datetime.fromisoformat(src["fetched_at"].replace("Z", "+00:00"))


def test_2026_year_end_block():
    raw = FIXTURE.read_bytes()
    by_date = _by_date(parse_document(raw, (2026, 2026)))
    # New Year's Day (public) — name from python-holidays
    assert "2026-01-01" in by_date
    # BoJ-only year-end days
    assert "2026-01-02" in by_date
    assert "Bank-only" in by_date["2026-01-02"]["name"]
    assert "2026-01-03" in by_date
    assert "Bank-only" in by_date["2026-01-03"]["name"]


def test_2026_coming_of_age_day():
    raw = FIXTURE.read_bytes()
    by_date = _by_date(parse_document(raw, (2026, 2026)))
    # 2nd Monday of January 2026 = Jan 12
    assert "2026-01-12" in by_date
    # python-holidays should give the canonical English name
    assert "Coming" in by_date["2026-01-12"]["name"] or "成人" in by_date["2026-01-12"]["name"]


def test_2026_dec_31():
    raw = FIXTURE.read_bytes()
    by_date = _by_date(parse_document(raw, (2026, 2026)))
    assert "2026-12-31" in by_date
    assert "Bank-only" in by_date["2026-12-31"]["name"]


def test_year_filtering():
    raw = FIXTURE.read_bytes()
    h_2026 = parse_document(raw, (2026, 2026))
    years = {int(h["date"][:4]) for h in h_2026}
    assert years == {2026}


def test_2026_total_count_reasonable():
    """BoJ closes ~21 days a year (public holidays + Jan 2-3 + Dec 31)."""
    raw = FIXTURE.read_bytes()
    h = parse_document(raw, (2026, 2026))
    assert 18 <= len(h) <= 25
