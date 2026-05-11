from datetime import datetime
from pathlib import Path

from scripts.sources.taifx_twd import build_payload, parse_document

FIXTURE = Path(__file__).parent / "fixtures" / "sources" / "taifx_twd" / "sample.html"


def test_payload_metadata():
    raw = FIXTURE.read_bytes()
    payload = build_payload((2026, 2030), raw)
    assert payload["currency"] == "TWD"
    assert payload["calendar_kind"] == "FIXING"
    assert payload["calendar_name"].startswith("Taipei Forex")
    src = payload["default_source"]
    datetime.fromisoformat(src["fetched_at"].replace("Z", "+00:00"))


def test_double_tenth_day():
    raw = FIXTURE.read_bytes()
    by_date = {h["date"]: h for h in parse_document(raw, (2026, 2026))}
    assert "2026-10-10" in by_date
    assert by_date["2026-10-10"]["name"] == "Double Tenth Day"


def test_year_count_2026():
    raw = FIXTURE.read_bytes()
    assert len(parse_document(raw, (2026, 2026))) == 15
