import json
from datetime import date
from pathlib import Path

import pytest

from fx_holiday_calculator.options import (
    ContractNotFoundError,
    days_until,
    get_contract,
    list_contracts,
    list_venues,
)


def _payload(venue: str, contracts: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "venue": venue,
        "calendar_kind": "EXCHANGE_OPTIONS_CONTRACTS",
        "valid_from": "2026-01-01",
        "valid_until": "2026-12-31",
        "default_source": {
            "url": "https://example.test",
            "doc_title": "Test",
            "fetched_at": "2026-05-13T00:00:00Z",
            "fetcher": "scripts/sources/test_options.py@v1",
            "default_derivation_mode": "derived",
        },
        "contracts": contracts,
    }


def _row(code: str, pair: str, month: str, expiry: str, delivery: str) -> dict:
    return {
        "code": code,
        "pair": pair,
        "product_name": "Test",
        "contract_month": month,
        "expiry_date": expiry,
        "delivery_date": delivery,
        "derivation_mode": "derived",
        "source": None,
        "note": None,
    }


def _bundle(tmp_path: Path, venue: str, rows: list[dict]) -> Path:
    d = tmp_path / "fx_exchange"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{venue}_options_contracts.json").write_text(
        json.dumps(_payload(venue, rows), indent=2) + "\n"
    )
    return tmp_path


def test_list_venues_discovers_options_contract_files(tmp_path):
    _bundle(tmp_path, "CME", [_row("X1", "EUR/USD", "2026-06", "2026-06-15", "2026-06-17")])
    _bundle(tmp_path, "HKEX", [_row("Y1", "USD/CNH", "2026-06", "2026-06-15", "2026-06-17")])
    assert list_venues(root=tmp_path, cache_root=tmp_path / "_no_cache") == ["CME", "HKEX"]


def test_list_contracts_filters_by_pair_and_asof(tmp_path):
    _bundle(
        tmp_path,
        "CME",
        [
            _row("EUEM6", "EUR/USD", "2026-06", "2026-06-15", "2026-06-17"),
            _row("EUEN6", "EUR/USD", "2026-07", "2026-07-13", "2026-07-15"),
            _row("BPEM6", "GBP/USD", "2026-06", "2026-06-15", "2026-06-17"),
        ],
    )
    rows = list_contracts("CME", pair="EUR/USD", root=tmp_path, cache_root=tmp_path / "_no_cache")
    assert [r.code for r in rows] == ["EUEM6", "EUEN6"]

    future_only = list_contracts(
        "CME",
        asof=date(2026, 7, 1),
        root=tmp_path,
        cache_root=tmp_path / "_no_cache",
    )
    assert [r.code for r in future_only] == ["EUEN6"]


def test_get_contract_raises_when_missing(tmp_path):
    _bundle(tmp_path, "CME", [_row("EUEM6", "EUR/USD", "2026-06", "2026-06-15", "2026-06-17")])
    with pytest.raises(ContractNotFoundError):
        get_contract("CME", "NOPE", root=tmp_path, cache_root=tmp_path / "_no_cache")


def test_days_until_counts_business_days(tmp_path):
    _bundle(tmp_path, "CME", [_row("EUEM6", "EUR/USD", "2026-06", "2026-06-15", "2026-06-17")])
    contract = get_contract("CME", "EUEM6", root=tmp_path, cache_root=tmp_path / "_no_cache")
    cd = days_until(
        contract, asof=date(2026, 6, 8), root=tmp_path, cache_root=tmp_path / "_no_cache"
    )
    assert cd.calendar_days_to_expiry == 7
    assert cd.calendar_days_to_delivery == 9
