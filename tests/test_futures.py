import json
from datetime import date
from pathlib import Path

import pytest

from fx_holiday_calculator.calendars.types import ContractEntry, SourceRef
from fx_holiday_calculator.futures import days_until, get_contract, list_contracts, list_venues


def _src() -> dict:
    return {
        "url": "https://example.test",
        "doc_title": "test",
        "fetched_at": "2026-01-01T00:00:00Z",
        "fetcher": "scripts/sources/cme_contracts.py@v1",
        "default_derivation_mode": "scrape",
    }


def _row(
    code: str,
    pair: str = "EUR/USD",
    ltd: str = "2026-06-15",
    settle: str = "2026-06-17",
    mode: str | None = None,
    contract_month: str = "2026-06",
) -> dict:
    return {
        "code": code,
        "pair": pair,
        "product_name": "Test Future",
        "contract_month": contract_month,
        "last_trading_day": ltd,
        "settlement_date": settle,
        "first_notice_day": None,
        "derivation_mode": mode,
        "source": None,
        "note": None,
    }


def _seed_venue(
    root: Path,
    venue: str,
    contracts: list[dict],
    default_mode: str = "scrape",
) -> None:
    d = root / "fx_exchange"
    d.mkdir(parents=True, exist_ok=True)
    src = dict(_src())
    src["default_derivation_mode"] = default_mode
    blob = {
        "schema_version": 1,
        "venue": venue,
        "calendar_kind": "EXCHANGE_CONTRACTS",
        "valid_from": "2026-01-01",
        "valid_until": "2027-12-31",
        "default_source": src,
        "contracts": contracts,
    }
    (d / f"{venue}_contracts.json").write_text(json.dumps(blob))


def test_list_venues_finds_seeded(tmp_path):
    _seed_venue(tmp_path, "CME", [_row("6EM6")])
    _seed_venue(tmp_path, "SGX", [_row("UCM6", pair="USD/CNH", ltd="2026-06-29")])
    venues = list_venues(root=tmp_path, cache_root=tmp_path / "no_cache")
    assert venues == ["CME", "SGX"]


def test_list_contracts_filters_by_pair_directionless(tmp_path):
    _seed_venue(
        tmp_path,
        "SGX",
        [
            _row("UCM6", pair="USD/CNH", ltd="2026-06-29"),
            _row("UCU6", pair="USD/CNH", ltd="2026-09-28", contract_month="2026-09"),
            _row("OTHER", pair="EUR/USD", ltd="2026-06-15"),
        ],
    )
    # Direction-agnostic match.
    cnh = list_contracts(
        "SGX", pair="CNH/USD", asof=date(2026, 1, 1), root=tmp_path, cache_root=tmp_path / "x"
    )
    assert [c.code for c in cnh] == ["UCM6", "UCU6"]


def test_list_contracts_hides_expired_by_default(tmp_path):
    _seed_venue(
        tmp_path,
        "CME",
        [
            _row("6EM6", ltd="2026-06-15", contract_month="2026-06"),
            _row("6EU6", ltd="2026-09-14", contract_month="2026-09"),
        ],
    )
    live = list_contracts("CME", asof=date(2026, 7, 1), root=tmp_path, cache_root=tmp_path / "x")
    assert [c.code for c in live] == ["6EU6"]


def test_get_contract_raises_on_unknown(tmp_path):
    _seed_venue(tmp_path, "CME", [_row("6EM6")])
    assert get_contract("CME", "6EM6", root=tmp_path, cache_root=tmp_path / "x").code == "6EM6"
    with pytest.raises(KeyError):
        get_contract("CME", "BOGUS", root=tmp_path, cache_root=tmp_path / "x")


def test_days_until_sign_conventions(tmp_path):
    _seed_venue(
        tmp_path,
        "CME",
        [_row("6EM6", ltd="2026-06-15", settle="2026-06-17")],
    )
    c = get_contract("CME", "6EM6", root=tmp_path, cache_root=tmp_path / "x")
    # Before LTD → positive
    forward = days_until(c, asof=date(2026, 6, 1), root=tmp_path, cache_root=tmp_path / "x")
    assert forward.business_days_to_ltd > 0
    assert forward.business_days_to_settlement > forward.business_days_to_ltd
    # On LTD → zero to LTD
    on = days_until(c, asof=date(2026, 6, 15), root=tmp_path, cache_root=tmp_path / "x")
    assert on.business_days_to_ltd == 0
    # Past LTD → negative
    past = days_until(c, asof=date(2026, 7, 1), root=tmp_path, cache_root=tmp_path / "x")
    assert past.business_days_to_ltd < 0
    assert past.business_days_to_settlement < 0


def test_days_until_drops_unbundled_leg_with_label(tmp_path):
    _seed_venue(
        tmp_path,
        "SGX",
        [_row("UCM6", pair="USD/INR", ltd="2026-06-29", settle="2026-06-30")],
    )
    c = get_contract("SGX", "UCM6", root=tmp_path, cache_root=tmp_path / "x")
    # No RTGS calendars bundled in tmp_path → label flags missing legs.
    cd = days_until(c, asof=date(2026, 6, 1), root=tmp_path, cache_root=tmp_path / "x")
    assert "USD" in cd.bd_calendar_used or "not bundled" in cd.bd_calendar_used
    # Calendar-day counts still work.
    assert cd.calendar_days_to_ltd == 28


def test_contract_entry_round_trip_carries_derivation_mode(tmp_path):
    _seed_venue(
        tmp_path,
        "CME",
        [
            _row("SCRAPE_ROW", mode="scrape"),
            _row("DERIVE_ROW", mode="derived", contract_month="2026-09", ltd="2026-09-14"),
        ],
    )
    contracts = list_contracts(
        "CME", asof=date(2026, 1, 1), include_expired=True, root=tmp_path, cache_root=tmp_path / "x"
    )
    by_code = {c.code: c for c in contracts}
    assert by_code["SCRAPE_ROW"].derivation_mode == "scrape"
    assert by_code["DERIVE_ROW"].derivation_mode == "derived"
    assert isinstance(by_code["SCRAPE_ROW"].source, SourceRef)
    assert isinstance(by_code["DERIVE_ROW"], ContractEntry)
