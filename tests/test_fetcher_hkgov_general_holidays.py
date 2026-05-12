from datetime import datetime
from pathlib import Path

from scripts.sources.hkgov_general_holidays import build_payload, parse_document

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sources" / "hkgov_general_holidays"
FIXTURE_2026 = FIXTURE_DIR / "2026.html"


def _by_date(holidays):
    return {h["date"]: h for h in holidays}


def test_2026_full_statutory_list():
    """All 17 entries from the General Holidays Ordinance schedule for 2026."""
    raw = FIXTURE_2026.read_bytes()
    holidays = parse_document(raw, 2026)
    assert len(holidays) == 17


def test_2026_known_dates():
    raw = FIXTURE_2026.read_bytes()
    by_date = _by_date(parse_document(raw, 2026))
    # New Year, Lunar New Year block (3 days), Good Friday block, Labour Day,
    # Buddha's Birthday (observed), Tuen Ng, SAR Establishment, Mid-Autumn (observed),
    # National Day, Chung Yeung (observed), Christmas, day after.
    expected = {
        "2026-01-01",
        "2026-02-17",
        "2026-02-18",
        "2026-02-19",
        "2026-04-03",
        "2026-04-04",
        "2026-04-06",  # day following Ching Ming (Sun → Mon substitution)
        "2026-04-07",  # day following Easter Monday
        "2026-05-01",
        "2026-05-25",  # day following Buddha's Birthday (Sun → Mon)
        "2026-06-19",
        "2026-07-01",
        "2026-09-26",  # day following Mid-Autumn (Sun → Sat per statute)
        "2026-10-01",
        "2026-10-19",  # day following Chung Yeung (Sun → Mon)
        "2026-12-25",
        "2026-12-26",
    }
    assert set(by_date) == expected


def test_skips_perennial_sunday_row():
    """The first row 'Every Sunday' has a blank date cell and must not appear
    as a dated holiday."""
    raw = FIXTURE_2026.read_bytes()
    holidays = parse_document(raw, 2026)
    for h in holidays:
        assert h["date"].startswith("2026-")
        # Date format should always be a real ISO date string, never blank.
        assert len(h["date"]) == 10


def test_each_entry_carries_per_year_source():
    raw = FIXTURE_2026.read_bytes()
    holidays = parse_document(raw, 2026)
    for h in holidays:
        src = h["source"]
        assert src is not None
        assert src["url"] == "https://www.gov.hk/en/about/abouthk/holiday/2026.htm"
        assert src["doc_title"] == "GovHK: General holidays for 2026"
        datetime.fromisoformat(src["fetched_at"].replace("Z", "+00:00"))


def test_decodes_html_entities_in_names():
    """Lunar New Year's Day in the HTML uses &rsquo; — name must be decoded."""
    raw = FIXTURE_2026.read_bytes()
    by_date = _by_date(parse_document(raw, 2026))
    assert "&rsquo;" not in by_date["2026-02-17"]["name"]
    assert "Lunar New Year" in by_date["2026-02-17"]["name"]


def test_payload_metadata_and_validity():
    raw = FIXTURE_2026.read_bytes()
    p = build_payload((2026, 2030), {2026: raw})
    assert p["currency"] == "HKD"
    assert p["calendar_kind"] == "RTGS"
    assert p["calendar_name"] == "HKD CHATS"
    # Validity clamped to the years for which we actually have pages.
    assert p["valid_from"] == "2026-01-01"
    assert p["valid_until"] == "2026-12-31"
    src = p["default_source"]
    assert src["url"].startswith("https://www.gov.hk/en/about/abouthk/holiday/")
    datetime.fromisoformat(src["fetched_at"].replace("Z", "+00:00"))


def test_build_payload_with_no_pages_falls_back_to_year_range():
    """When fetch finds nothing in range, build_payload should still produce
    a well-formed (if empty) payload rather than crashing."""
    p = build_payload((2026, 2030), {})
    assert p["holidays"] == []
    assert p["valid_from"] == "2026-01-01"
    assert p["valid_until"] == "2030-12-31"
