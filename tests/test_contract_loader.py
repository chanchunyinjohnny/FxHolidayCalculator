import json
from datetime import date

import pytest

from fx_holiday_calculator.calendars.loader import load_contract_calendar


def _payload(
    venue: str = "CME",
    default_mode: str = "scrape",
    contracts=None,
) -> dict:
    if contracts is None:
        contracts = []
    return {
        "schema_version": 1,
        "venue": venue,
        "calendar_kind": "EXCHANGE_CONTRACTS",
        "valid_from": "2026-01-01",
        "valid_until": "2027-12-31",
        "default_source": {
            "url": "https://example.test/specs",
            "doc_title": "Test specs",
            "fetched_at": "2026-01-01T00:00:00Z",
            "fetcher": "scripts/sources/cme_contracts.py@v1",
            "default_derivation_mode": default_mode,
        },
        "contracts": contracts,
    }


def _row(
    code: str = "6EM6",
    mode: str | None = None,
    src: dict | None = None,
    settlement: str = "2026-06-17",
) -> dict:
    return {
        "code": code,
        "pair": "EUR/USD",
        "product_name": "Euro FX Futures",
        "contract_month": "2026-06",
        "last_trading_day": "2026-06-15",
        "settlement_date": settlement,
        "first_notice_day": None,
        "derivation_mode": mode,
        "source": src,
        "note": None,
    }


def test_loads_bundled_when_no_cache(tmp_path):
    bundled = tmp_path / "fx_exchange"
    bundled.mkdir()
    payload = _payload(contracts=[_row()])
    (bundled / "CME_contracts.json").write_text(json.dumps(payload))

    cal = load_contract_calendar("CME", root=bundled, cache_root=None)
    assert cal.venue == "CME"
    assert len(cal.entries) == 1
    e = cal.entries[0]
    assert e.code == "6EM6"
    assert e.last_trading_day == date(2026, 6, 15)
    assert e.derivation_mode == "scrape"
    assert e.source_origin == "bundled"
    assert cal.default_derivation_mode_is_derived is False


def test_cache_overlays_bundled(tmp_path):
    bundled = tmp_path / "fx_exchange"
    cache = tmp_path / "cache"
    bundled.mkdir()
    cache.mkdir()
    (bundled / "CME_contracts.json").write_text(
        json.dumps(_payload(contracts=[_row(settlement="2026-06-17")]))
    )
    (cache / "CME_contracts.json").write_text(
        json.dumps(_payload(contracts=[_row(settlement="2026-06-19")]))
    )
    cal = load_contract_calendar("CME", root=bundled, cache_root=cache)
    assert cal.entries[0].settlement_date == date(2026, 6, 19)
    assert cal.entries[0].source_origin == "cache"


def test_manual_row_uses_per_entry_source_override(tmp_path):
    bundled = tmp_path / "fx_exchange"
    bundled.mkdir()
    override = {
        "url": "https://venue.test/circular-2026-07",
        "doc_title": "Venue circular 2026-07",
        "fetched_at": "2026-07-01T00:00:00Z",
        "fetcher": "manual",
    }
    payload = _payload(
        contracts=[_row(mode="manual", src=override)],
    )
    (bundled / "CME_contracts.json").write_text(json.dumps(payload))
    cal = load_contract_calendar("CME", root=bundled, cache_root=None)
    e = cal.entries[0]
    assert e.derivation_mode == "manual"
    assert e.source.url == "https://venue.test/circular-2026-07"
    assert e.source.fetcher == "manual"


def test_per_entry_derivation_mode_overrides_default(tmp_path):
    bundled = tmp_path / "fx_exchange"
    bundled.mkdir()
    payload = _payload(
        default_mode="scrape",
        contracts=[_row(mode="derived")],
    )
    (bundled / "CME_contracts.json").write_text(json.dumps(payload))
    cal = load_contract_calendar("CME", root=bundled, cache_root=None)
    assert cal.entries[0].derivation_mode == "derived"
    assert cal.has_derived_rows() is True


def test_invalid_derivation_mode_raises(tmp_path):
    bundled = tmp_path / "fx_exchange"
    bundled.mkdir()
    payload = _payload(default_mode="bogus", contracts=[])
    (bundled / "CME_contracts.json").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="default_derivation_mode"):
        load_contract_calendar("CME", root=bundled, cache_root=None)


def test_default_derivation_mode_is_derived_flag(tmp_path):
    bundled = tmp_path / "fx_exchange"
    bundled.mkdir()
    payload = _payload(default_mode="derived", contracts=[_row()])
    (bundled / "CME_contracts.json").write_text(json.dumps(payload))
    cal = load_contract_calendar("CME", root=bundled, cache_root=None)
    assert cal.default_derivation_mode_is_derived is True
