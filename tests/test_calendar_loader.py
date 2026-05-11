import json as _json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.fixing import FixingCalendar
from fx_holiday_calculator.calendars.loader import (
    load_exchange_calendar,
    load_fixing_calendar,
    load_rtgs_calendar,
)
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import CalendarRangeError

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
        "schema_version": 3,
        "currency": "USD",
        "calendar_kind": "RTGS",
        "calendar_name": "Fedwire",
        "operator": "Federal Reserve System",
        "valid_from": "2026-01-01",
        "valid_until": "2026-12-31",
        "default_source": {
            "url": "https://x",
            "doc_title": "x",
            "fetched_at": "2026-05-06T00:00:00Z",
            "fetcher": "test",
        },
        "holidays": [{"date": "2026-01-01", "name": "NYD", "source": None, "note": None}],
        "informational_dates": [
            {
                "date": "2026-11-27",
                "name": "Day after T",
                "source": None,
                "note": "thin",
                "liquidity": "thin",
            },
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


def test_validity_window_is_loaded():
    cal = load_rtgs_calendar("USD", root=FIXTURE_DIR)
    assert cal.valid_from == date(2026, 1, 1)
    assert cal.valid_until == date(2026, 12, 31)


def test_is_holiday_raises_outside_validity_window():
    cal = load_rtgs_calendar("USD", root=FIXTURE_DIR)
    with pytest.raises(CalendarRangeError) as ei:
        cal.is_holiday(date(2027, 1, 1))
    assert ei.value.valid_from == date(2026, 1, 1)
    assert ei.value.valid_until == date(2026, 12, 31)
    assert "2027-01-01" in str(ei.value)
    assert "2026-12-31" in str(ei.value)


def test_get_holiday_raises_outside_validity_window():
    cal = load_rtgs_calendar("USD", root=FIXTURE_DIR)
    with pytest.raises(CalendarRangeError):
        cal.get_holiday(date(2025, 12, 31))


def test_exchange_calendar_range_check():
    cal = load_exchange_calendar("HKEX", root=FIXTURE_DIR)
    with pytest.raises(CalendarRangeError):
        cal.is_holiday(date(2030, 1, 1))


def test_loader_rejects_missing_validity_window(tmp_path):
    blob = {
        "schema_version": 3,
        "currency": "USD",
        "calendar_kind": "RTGS",
        "calendar_name": "Fedwire",
        "operator": "Federal Reserve System",
        "default_source": {
            "url": "https://x",
            "doc_title": "x",
            "fetched_at": "2026-05-06T00:00:00Z",
            "fetcher": "test",
        },
        "holidays": [],
    }
    p = tmp_path / "USD.json"
    p.write_text(_json.dumps(blob))
    with pytest.raises(ValueError, match="valid_from"):
        load_rtgs_calendar("USD", root=tmp_path)


def test_stale_v1_cache_falls_back_to_bundled(tmp_path, caplog):
    # Repro: a cache file written by a pre-schema-v3 version of this tool
    # lacks valid_from/valid_until. The loader must skip it and use the
    # bundled file rather than crash. The original incident: the UI showed
    # a raw ValueError traceback to the user when their cache predated a
    # schema bump.
    cache = tmp_path / "cache"
    cache.mkdir()
    stale = {
        "schema_version": 1,
        "currency": "USD",
        "calendar_kind": "RTGS",
        "calendar_name": "Fedwire",
        "operator": "Federal Reserve System",
        "default_source": {
            "url": "https://x",
            "doc_title": "x",
            "fetched_at": "2026-04-15T03:00:00Z",
            "fetcher": "test",
        },
        "holidays": [
            {"date": "2026-01-01", "name": "NYD (stale)", "source": None, "note": None},
        ],
    }
    (cache / "USD.json").write_text(_json.dumps(stale))
    import logging

    with caplog.at_level(logging.WARNING):
        cal = load_rtgs_calendar("USD", root=FIXTURE_DIR, cache_root=cache)
    # Came from bundled, not cache
    entry = cal.get_holiday(date(2026, 1, 1))
    assert entry is not None
    assert "(stale)" not in entry.name
    assert entry.source_origin == "bundled"
    # Warning logged
    assert any("predates schema_version 3" in r.message for r in caplog.records)


def test_corrupt_cache_falls_back_to_bundled(tmp_path, caplog):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "USD.json").write_text("{ not valid json")
    import logging

    with caplog.at_level(logging.WARNING):
        cal = load_rtgs_calendar("USD", root=FIXTURE_DIR, cache_root=cache)
    assert cal.currency == "USD"  # loaded successfully via bundled
    assert any("corrupt" in r.message for r in caplog.records)


def test_cache_overlays_bundled(tmp_path):
    # Bundled fixture has 2 USD holidays; cache adds a 3rd.
    cache = tmp_path / "cache"
    cache.mkdir()
    bundled_blob = _json.loads((FIXTURE_DIR / "USD.json").read_text())
    bundled_blob["default_source"]["fetched_at"] = "2026-05-06T14:00:00Z"
    bundled_blob["holidays"].append(
        {
            "date": "2026-12-25",
            "name": "Christmas Day (live cache)",
            "source": None,
            "note": None,
        }
    )
    (cache / "USD.json").write_text(_json.dumps(bundled_blob))

    cal = load_rtgs_calendar("USD", root=FIXTURE_DIR, cache_root=cache)
    assert cal.is_holiday(date(2026, 12, 25)) is True
    entry = cal.get_holiday(date(2026, 12, 25))
    assert entry.source_origin == "cache"


def _write_fixing_blob(tmp_path: Path, currency: str, holidays: list[dict]) -> Path:
    blob = {
        "schema_version": 3,
        "currency": currency,
        "calendar_kind": "FIXING",
        "calendar_name": f"{currency} fixing",
        "operator": "test",
        "valid_from": "2026-01-01",
        "valid_until": "2030-12-31",
        "default_source": {
            "url": "https://x",
            "doc_title": "x",
            "fetched_at": "2026-01-01T00:00:00Z",
            "fetcher": "test",
        },
        "holidays": holidays,
    }
    out = tmp_path / f"{currency}.json"
    out.write_text(_json.dumps(blob))
    return out


def test_load_fixing_calendar_basic(tmp_path):
    _write_fixing_blob(
        tmp_path,
        "CNY",
        [{"date": "2026-10-01", "name": "National Day", "source": None, "note": None}],
    )
    cal = load_fixing_calendar("CNY", root=tmp_path)
    assert isinstance(cal, FixingCalendar)
    assert cal.currency == "CNY"
    assert cal.is_holiday(date(2026, 10, 1)) is True
    entry = cal.get_holiday(date(2026, 10, 1))
    assert entry is not None
    assert entry.source.url == "https://x"
    assert entry.source_origin == "bundled"


def test_load_fixing_calendar_rejects_wrong_kind(tmp_path):
    blob = {
        "schema_version": 3,
        "currency": "CNY",
        "calendar_kind": "RTGS",  # wrong kind
        "calendar_name": "x",
        "operator": "x",
        "valid_from": "2026-01-01",
        "valid_until": "2030-12-31",
        "default_source": {
            "url": "https://x",
            "doc_title": "x",
            "fetched_at": "2026-01-01T00:00:00Z",
            "fetcher": "t",
        },
        "holidays": [],
    }
    (tmp_path / "CNY.json").write_text(_json.dumps(blob))
    with pytest.raises(ValueError, match="not a FIXING calendar"):
        load_fixing_calendar("CNY", root=tmp_path)


def test_load_fixing_calendar_marks_library_sourced_when_fetcher_says_so(tmp_path):
    blob = {
        "schema_version": 3,
        "currency": "CNY",
        "calendar_kind": "FIXING",
        "calendar_name": "x",
        "operator": "x",
        "valid_from": "2026-01-01",
        "valid_until": "2030-12-31",
        "default_source": {
            "url": "https://x",
            "doc_title": "x",
            "fetched_at": "2026-01-01T00:00:00Z",
            "fetcher": "scripts/sources/library_fixing.py@v1",
        },
        "holidays": [],
    }
    (tmp_path / "CNY.json").write_text(_json.dumps(blob))
    cal = load_fixing_calendar("CNY", root=tmp_path)
    assert cal.library_sourced is True


def test_load_fixing_calendar_primary_fetcher_not_marked_library(tmp_path):
    blob = {
        "schema_version": 3,
        "currency": "CNY",
        "calendar_kind": "FIXING",
        "calendar_name": "x",
        "operator": "x",
        "valid_from": "2026-01-01",
        "valid_until": "2030-12-31",
        "default_source": {
            "url": "https://x",
            "doc_title": "x",
            "fetched_at": "2026-01-01T00:00:00Z",
            "fetcher": "scripts/sources/cfets_cny.py@v1",
        },
        "holidays": [],
    }
    (tmp_path / "CNY.json").write_text(_json.dumps(blob))
    cal = load_fixing_calendar("CNY", root=tmp_path)
    assert cal.library_sourced is False


def test_load_fixing_calendar_cache_overlays_bundled(tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    cache = tmp_path / "cache"
    cache.mkdir()
    _write_fixing_blob(
        bundled,
        "CNY",
        [{"date": "2026-10-01", "name": "National Day", "source": None, "note": None}],
    )
    _write_fixing_blob(
        cache,
        "CNY",
        [{"date": "2026-10-02", "name": "Extra closure", "source": None, "note": None}],
    )
    cal = load_fixing_calendar("CNY", root=bundled, cache_root=cache)
    # Cache wins
    assert cal.is_holiday(date(2026, 10, 2)) is True
    assert cal.is_holiday(date(2026, 10, 1)) is False
    entry = cal.get_holiday(date(2026, 10, 2))
    assert entry.source_origin == "cache"
