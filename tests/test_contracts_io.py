import json
from pathlib import Path

from scripts.sources._contracts_io import merge_preserving_manual


def _payload(*contracts) -> dict:
    return {
        "schema_version": 1,
        "venue": "CME",
        "calendar_kind": "EXCHANGE_CONTRACTS",
        "default_source": {
            "url": "https://example.test",
            "doc_title": "test",
            "fetched_at": "2026-01-01T00:00:00Z",
            "fetcher": "scripts/sources/cme_contracts.py@v1",
            "default_derivation_mode": "scrape",
        },
        "contracts": list(contracts),
    }


def _row(code, mode="scrape", month="2026-06"):
    return {
        "code": code,
        "pair": "EUR/USD",
        "product_name": "Euro FX",
        "contract_month": month,
        "last_trading_day": "2026-06-15",
        "settlement_date": "2026-06-17",
        "first_notice_day": None,
        "derivation_mode": mode,
        "source": None,
        "note": None,
    }


def test_no_existing_file_returns_new_payload(tmp_path: Path):
    new = _payload(_row("6EM6"))
    out = merge_preserving_manual(tmp_path / "missing.json", new)
    assert out == new


def test_no_manual_rows_in_existing_returns_new_payload(tmp_path: Path):
    p = tmp_path / "CME_contracts.json"
    p.write_text(json.dumps(_payload(_row("OLD"))))
    new = _payload(_row("6EM6"))
    out = merge_preserving_manual(p, new)
    assert [c["code"] for c in out["contracts"]] == ["6EM6"]


def test_manual_row_survives_refresh(tmp_path: Path):
    p = tmp_path / "CME_contracts.json"
    p.write_text(json.dumps(_payload(_row("CUSTOM1", mode="manual", month="2026-08"))))
    new = _payload(_row("6EM6", mode="scrape", month="2026-06"))
    out = merge_preserving_manual(p, new)
    codes_modes = {c["code"]: c["derivation_mode"] for c in out["contracts"]}
    assert codes_modes == {"CUSTOM1": "manual", "6EM6": "scrape"}


def test_manual_row_wins_on_key_collision(tmp_path: Path):
    p = tmp_path / "CME_contracts.json"
    manual_with_note = _row("6EM6", mode="manual", month="2026-06")
    manual_with_note["note"] = "Curated by maintainer; venue page wrong on settlement"
    p.write_text(json.dumps(_payload(manual_with_note)))

    new_scrape = _row("6EM6", mode="scrape", month="2026-06")
    new_scrape["settlement_date"] = "2026-06-19"  # different from manual
    out = merge_preserving_manual(p, _payload(new_scrape))
    # Only one row for (6EM6, 2026-06); it's the manual one.
    rows = out["contracts"]
    assert len(rows) == 1
    assert rows[0]["derivation_mode"] == "manual"
    assert rows[0]["settlement_date"] == "2026-06-17"
    assert rows[0]["note"].startswith("Curated by maintainer")


def test_corrupt_existing_file_falls_back_to_new(tmp_path: Path):
    p = tmp_path / "CME_contracts.json"
    p.write_text("{ not valid json")
    new = _payload(_row("6EM6"))
    out = merge_preserving_manual(p, new)
    assert out == new
