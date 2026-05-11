from datetime import datetime
from pathlib import Path

from scripts.sources.kftc_krw import build_payload, parse_document

FIXTURE = Path(__file__).parent / "fixtures" / "sources" / "kftc_krw" / "sample.html"


def test_payload_metadata():
    raw = FIXTURE.read_bytes()
    payload = build_payload((2026, 2030), raw)
    assert payload["currency"] == "KRW"
    assert payload["calendar_kind"] == "FIXING"
    assert payload["calendar_name"].startswith("KFTC")
    src = payload["default_source"]
    datetime.fromisoformat(src["fetched_at"].replace("Z", "+00:00"))


def test_chuseok_two_days_present():
    raw = FIXTURE.read_bytes()
    holidays = parse_document(raw, (2026, 2026))
    by_date = {h["date"]: h for h in holidays}
    assert "2026-09-24" in by_date
    assert "2026-09-25" in by_date
    assert by_date["2026-09-24"]["name"] == "Chuseok"


def test_year_count_2026():
    raw = FIXTURE.read_bytes()
    assert len(parse_document(raw, (2026, 2026))) == 14
