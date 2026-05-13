import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from fx_holiday_calculator.calendars.contracts import OptionsContractCalendar
from fx_holiday_calculator.calendars.loader import load_options_contract_calendar
from fx_holiday_calculator.calendars.types import OptionContractEntry, SourceRef


def _src() -> SourceRef:
    return SourceRef(
        url="https://x",
        doc_title="x",
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        fetcher="t",
    )


def _entry(code: str, pair: str, month: str, expiry: date, delivery: date) -> OptionContractEntry:
    return OptionContractEntry(
        venue="CME",
        code=code,
        pair=pair,
        product_name="Options on Test Futures",
        contract_month=month,
        expiry_date=expiry,
        delivery_date=delivery,
        derivation_mode="derived",
        source=_src(),
        source_origin="bundled",
        note=None,
    )


def test_options_contract_calendar_get_by_code():
    e1 = _entry("X1", "EUR/USD", "2026-06", date(2026, 6, 5), date(2026, 6, 9))
    cal = OptionsContractCalendar(venue="CME", entries=(e1,))
    assert cal.get("X1") is e1
    assert cal.get("X1".lower()) is e1
    assert cal.get("MISSING") is None


def test_options_contract_calendar_iter_listing_sorted_and_filtered():
    e_late = _entry("X9", "EUR/USD", "2026-09", date(2026, 9, 15), date(2026, 9, 17))
    e_early = _entry("X6", "EUR/USD", "2026-06", date(2026, 6, 5), date(2026, 6, 9))
    e_other = _entry("Y6", "GBP/USD", "2026-06", date(2026, 6, 5), date(2026, 6, 9))
    cal = OptionsContractCalendar(venue="CME", entries=(e_late, e_early, e_other))
    rows = cal.iter_listing()
    assert [r.code for r in rows] == ["X6", "Y6", "X9"]
    eu_only = cal.iter_listing(pair="EUR/USD")
    assert [r.code for r in eu_only] == ["X6", "X9"]
    asof_skip_past = cal.iter_listing(asof=date(2026, 8, 1))
    assert [r.code for r in asof_skip_past] == ["X9"]
    asof_keep_past = cal.iter_listing(asof=date(2026, 8, 1), include_expired=True)
    assert [r.code for r in asof_keep_past] == ["X6", "Y6", "X9"]


def _write_json(p: Path, payload: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2) + "\n")


def _minimal_payload(venue: str) -> dict:
    return {
        "schema_version": 1,
        "venue": venue,
        "calendar_kind": "EXCHANGE_OPTIONS_CONTRACTS",
        "valid_from": "2026-06-01",
        "valid_until": "2026-12-31",
        "default_source": {
            "url": "https://example.test",
            "doc_title": "Test",
            "fetched_at": "2026-05-13T00:00:00Z",
            "fetcher": "scripts/sources/test_options.py@v1",
            "default_derivation_mode": "derived",
        },
        "contracts": [
            {
                "code": "X1",
                "pair": "EUR/USD",
                "product_name": "Options on Euro FX Futures",
                "contract_month": "2026-06",
                "expiry_date": "2026-06-05",
                "delivery_date": "2026-06-09",
                "derivation_mode": "derived",
                "source": None,
                "note": "test",
            }
        ],
    }


def test_load_options_contract_calendar_minimal(tmp_path):
    _write_json(tmp_path / "CME_options_contracts.json", _minimal_payload("CME"))
    cal = load_options_contract_calendar("CME", root=tmp_path)
    assert cal.venue == "CME"
    assert len(cal.entries) == 1
    e = cal.entries[0]
    assert e.code == "X1"
    assert e.expiry_date == date(2026, 6, 5)
    assert e.delivery_date == date(2026, 6, 9)
    assert e.derivation_mode == "derived"
    assert cal.default_derivation_mode_is_derived is True


def test_load_options_contract_calendar_rejects_wrong_kind(tmp_path):
    bad = _minimal_payload("CME")
    bad["calendar_kind"] = "EXCHANGE_CONTRACTS"
    _write_json(tmp_path / "CME_options_contracts.json", bad)
    with pytest.raises(ValueError, match="not an EXCHANGE_OPTIONS_CONTRACTS"):
        load_options_contract_calendar("CME", root=tmp_path)


def test_load_options_contract_calendar_rejects_bad_mode(tmp_path):
    bad = _minimal_payload("CME")
    bad["contracts"][0]["derivation_mode"] = "telephone"
    _write_json(tmp_path / "CME_options_contracts.json", bad)
    with pytest.raises(ValueError, match="invalid derivation_mode"):
        load_options_contract_calendar("CME", root=tmp_path)
