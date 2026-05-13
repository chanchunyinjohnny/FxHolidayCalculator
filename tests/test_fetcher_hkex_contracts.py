"""End-to-end test for `scripts/sources/hkex_contracts.py`.

The scrape stub returns nothing in v1, so we exercise the derive-fallback
path against the bundled RTGS + venue-holiday calendars and assert the
output is well-formed. The manual-row preservation test seeds a manual row,
runs the fetcher, and verifies the row survives.
"""

import json
from pathlib import Path

from scripts.sources.hkex_contracts import fetch


def _copy_seed(src_root: Path, dst_root: Path) -> None:
    """Copy the bundled RTGS + venue-holiday JSON into a tmp location so the
    fetcher can load them while writing into the tmp target."""
    import shutil

    for sub in ("fx_rtgs", "fx_exchange"):
        s = src_root / sub
        d = dst_root / sub
        d.mkdir(parents=True, exist_ok=True)
        for f in s.glob("*.json"):
            # Skip pre-existing contract files — the fetcher is what populates them.
            if f.name.endswith("_contracts.json"):
                continue
            shutil.copy(f, d / f.name)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_fetch_writes_derived_rows(tmp_path):
    _copy_seed(REPO_ROOT / "data", tmp_path)
    out = fetch((2026, 2027), tmp_path)
    blob = json.loads(out.read_text())
    assert blob["venue"] == "HKEX"
    assert blob["calendar_kind"] == "EXCHANGE_CONTRACTS"
    assert blob["default_source"]["default_derivation_mode"] == "derived"
    assert blob["contracts"], "Expected at least one derived row"
    for row in blob["contracts"]:
        assert row["derivation_mode"] == "derived"
        assert row["last_trading_day"] <= row["settlement_date"]
        assert row["code"]
        assert row["pair"]


def test_manual_row_survives_refresh(tmp_path):
    _copy_seed(REPO_ROOT / "data", tmp_path)
    # Pre-seed HKEX_contracts.json with a manual row at a non-standard month
    # so it cannot collide with the derived output keys.
    out_dir = tmp_path / "fx_exchange"
    out_dir.mkdir(parents=True, exist_ok=True)
    manual_blob = {
        "schema_version": 1,
        "venue": "HKEX",
        "calendar_kind": "EXCHANGE_CONTRACTS",
        "valid_from": "2026-01-01",
        "valid_until": "2027-12-31",
        "default_source": {
            "url": "https://www.hkex.com.hk/Products/Listed-Derivatives/Currency?sc_lang=en",
            "doc_title": "HKEX — Listed Currency Derivatives (Contract Specifications)",
            "fetched_at": "2026-01-01T00:00:00Z",
            "fetcher": "scripts/sources/hkex_contracts.py@v1",
            "default_derivation_mode": "scrape",
        },
        "contracts": [
            {
                "code": "HKD_CUSTOM",
                "pair": "HKD/CNH",
                "product_name": "HKD/CNH Futures (manual)",
                "contract_month": "2026-08",
                "last_trading_day": "2026-08-17",
                "settlement_date": "2026-08-19",
                "first_notice_day": None,
                "derivation_mode": "manual",
                "source": {
                    "url": "https://www.hkex.com.hk/Products/Listed-Derivatives/Currency/...",
                    "doc_title": "HKEX Notice 2026-08 HKD/CNH",
                    "fetched_at": "2026-07-01T00:00:00Z",
                    "fetcher": "manual",
                },
                "note": "Curated by maintainer.",
            }
        ],
    }
    (out_dir / "HKEX_contracts.json").write_text(json.dumps(manual_blob))

    fetch((2026, 2027), tmp_path)
    blob = json.loads((out_dir / "HKEX_contracts.json").read_text())
    codes_to_modes = {c["code"]: c["derivation_mode"] for c in blob["contracts"]}
    assert codes_to_modes.get("HKD_CUSTOM") == "manual"
    # Derived rows should also have been written.
    assert any(m == "derived" for m in codes_to_modes.values())
