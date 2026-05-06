import json as _json
from datetime import date, datetime, timezone
from pathlib import Path

from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.loader import load_exchange_calendar, load_rtgs_calendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "calendars"


def test_loads_usd_calendar():
    cal = load_rtgs_calendar("USD", root=FIXTURE_DIR)
    assert isinstance(cal, RtgsCalendar)
    assert cal.currency == "USD"
    assert cal.calendar_name == "Fedwire"


def test_is_holiday_for_listed_date():
    cal = load_rtgs_calendar("USD", root=FIXTURE_DIR)
    assert cal.is_holiday(date(2026, 1, 1)) is True
    assert cal.is_holiday(date(2026, 1, 2)) is False


def test_get_holiday_carries_source():
    cal = load_rtgs_calendar("USD", root=FIXTURE_DIR)
    entry = cal.get_holiday(date(2026, 7, 3))
    assert entry is not None
    assert entry.name == "Independence Day (observed)"
    assert entry.source.url.startswith("https://www.federalreserve.gov")
    assert entry.source.fetched_at == datetime(2026, 4, 15, 3, 0, tzinfo=timezone.utc)
    assert entry.source_origin == "bundled"


def test_get_holiday_for_good_day_returns_none():
    cal = load_rtgs_calendar("USD", root=FIXTURE_DIR)
    assert cal.get_holiday(date(2026, 1, 2)) is None


def test_loads_hkex_exchange_calendar():
    cal = load_exchange_calendar("HKEX", root=FIXTURE_DIR)
    assert isinstance(cal, ExchangeCalendar)
    assert cal.venue == "HKEX"
    assert "USD/CNH Futures" in cal.products
    assert cal.is_holiday(date(2026, 2, 17)) is True
    entry = cal.get_holiday(date(2026, 1, 1))
    assert entry is not None
    assert entry.source.url.startswith("https://www.hkex.com.hk")


def test_loader_reads_informational_dates(tmp_path):
    blob = {
        "schema_version": 2,
        "currency": "USD",
        "calendar_kind": "RTGS",
        "calendar_name": "Fedwire",
        "operator": "Federal Reserve System",
        "default_source": {
            "url": "https://x", "doc_title": "x",
            "fetched_at": "2026-05-06T00:00:00Z", "fetcher": "test",
        },
        "holidays": [
            {"date": "2026-01-01", "name": "NYD", "source": None, "note": None}
        ],
        "informational_dates": [
            {"date": "2026-11-27", "name": "Day after T",
             "source": None, "note": "thin", "liquidity": "thin"},
        ],
    }
    p = tmp_path / "USD.json"
    p.write_text(_json.dumps(blob))
    cal = load_rtgs_calendar("USD", root=tmp_path)
    # The closure date is a holiday; the informational date is not.
    assert cal.is_holiday(date(2026, 1, 1)) is True
    assert cal.is_holiday(date(2026, 11, 27)) is False  # informational, NOT a closure
    # But get_holiday returns the entry for the informational date too
    info = cal.get_holiday(date(2026, 11, 27))
    assert info is not None
    assert info.is_closure is False
    assert info.liquidity == "thin"


def test_cache_overlays_bundled(tmp_path):
    # Bundled fixture has 2 USD holidays; cache adds a 3rd.
    cache = tmp_path / "cache"
    cache.mkdir()
    bundled_blob = _json.loads((FIXTURE_DIR / "USD.json").read_text())
    bundled_blob["default_source"]["fetched_at"] = "2026-05-06T14:00:00Z"
    bundled_blob["holidays"].append({
        "date": "2026-12-25", "name": "Christmas Day (live cache)",
        "source": None, "note": None,
    })
    (cache / "USD.json").write_text(_json.dumps(bundled_blob))

    cal = load_rtgs_calendar("USD", root=FIXTURE_DIR, cache_root=cache)
    assert cal.is_holiday(date(2026, 12, 25)) is True
    entry = cal.get_holiday(date(2026, 12, 25))
    assert entry.source_origin == "cache"
