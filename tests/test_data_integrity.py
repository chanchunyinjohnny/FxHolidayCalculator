import json
from datetime import date, datetime
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).parents[1] / "data"
RTGS_DIR = DATA_DIR / "fx_rtgs"
EXCH_DIR = DATA_DIR / "fx_exchange"
FIXING_DIR = DATA_DIR / "fx_fixing"


def _all_calendar_files() -> list[Path]:
    """Holiday-schema calendars only (RTGS / EXCHANGE / FIXING). Contract-listings
    files (`*_contracts.json`) live under the same directory but follow a
    different schema and are covered by `_all_contract_files`."""
    files: list[Path] = []
    for d in (RTGS_DIR, EXCH_DIR, FIXING_DIR):
        if d.exists():
            files += sorted(
                p
                for p in d.glob("*.json")
                if not p.name.startswith("_") and not p.name.endswith("_contracts.json")
            )
    return files


def _all_contract_files() -> list[Path]:
    if not EXCH_DIR.exists():
        return []
    return sorted(p for p in EXCH_DIR.glob("*_contracts.json"))


def _resolve_source(raw_entry: dict, default: dict) -> dict:
    return raw_entry["source"] if raw_entry.get("source") else default


@pytest.mark.parametrize("path", _all_calendar_files(), ids=lambda p: p.name)
def test_every_entry_has_resolvable_source(path: Path):
    blob = json.loads(path.read_text())
    default = blob["default_source"]
    for raw in blob.get("holidays", []) + blob.get("informational_dates", []):
        src = _resolve_source(raw, default)
        assert src["url"], f"{path}: entry {raw['date']} missing source.url"
        assert src["doc_title"], f"{path}: entry {raw['date']} missing source.doc_title"
        assert src["fetched_at"], f"{path}: entry {raw['date']} missing source.fetched_at"
        # parse fetched_at to confirm it is ISO-8601
        datetime.fromisoformat(src["fetched_at"].replace("Z", "+00:00"))


@pytest.mark.parametrize("path", _all_calendar_files(), ids=lambda p: p.name)
def test_default_source_complete(path: Path):
    blob = json.loads(path.read_text())
    src = blob["default_source"]
    assert src["url"]
    assert src["doc_title"]
    assert src["fetched_at"]
    assert src["fetcher"]


@pytest.mark.parametrize("path", _all_calendar_files(), ids=lambda p: p.name)
def test_validity_window_declared_and_covers_entries(path: Path):
    blob = json.loads(path.read_text())
    assert "valid_from" in blob, f"{path}: missing required field 'valid_from'"
    assert "valid_until" in blob, f"{path}: missing required field 'valid_until'"
    vf = date.fromisoformat(blob["valid_from"])
    vu = date.fromisoformat(blob["valid_until"])
    assert vu >= vf, f"{path}: valid_until precedes valid_from"
    for raw in blob.get("holidays", []) + blob.get("informational_dates", []):
        d = date.fromisoformat(raw["date"])
        assert (
            vf <= d <= vu
        ), f"{path}: entry {raw['date']} is outside declared window [{vf} .. {vu}]"


# ----- contract-listings files -----

_ALLOWED_MODES = {"scrape", "derived", "manual"}


@pytest.mark.parametrize("path", _all_contract_files(), ids=lambda p: p.name)
def test_contract_file_metadata_complete(path: Path):
    blob = json.loads(path.read_text())
    assert blob.get("calendar_kind") == "EXCHANGE_CONTRACTS", path
    assert blob.get("venue"), path
    src = blob["default_source"]
    assert src["url"]
    assert src["doc_title"]
    assert src["fetched_at"]
    assert src["fetcher"]
    assert src.get("default_derivation_mode") in _ALLOWED_MODES, path


@pytest.mark.parametrize("path", _all_contract_files(), ids=lambda p: p.name)
def test_every_contract_has_required_fields(path: Path):
    blob = json.loads(path.read_text())
    default = blob["default_source"]
    default_mode = default["default_derivation_mode"]
    for raw in blob.get("contracts", []):
        code = raw.get("code")
        assert code, f"{path}: contract missing 'code'"
        for fld in ("pair", "product_name", "contract_month"):
            assert raw.get(fld), f"{path}: contract {code} missing {fld!r}"
        # LTD and settlement are mandatory
        ltd = date.fromisoformat(raw["last_trading_day"])
        settle = date.fromisoformat(raw["settlement_date"])
        assert ltd <= settle, f"{path}: contract {code} has settlement {settle} < LTD {ltd}"
        # derivation_mode resolved (entry override OR file default)
        mode = raw.get("derivation_mode") or default_mode
        assert mode in _ALLOWED_MODES, f"{path}: contract {code} bad mode {mode!r}"
        # manual rows MUST carry a per-entry source override
        if mode == "manual":
            assert raw.get(
                "source"
            ), f"{path}: manual contract {code} missing per-entry source override"
            for k in ("url", "doc_title", "fetched_at"):
                assert raw["source"].get(k), f"{path}: manual {code} source missing {k!r}"
        else:
            # scrape/derived may inherit from default_source
            src = raw.get("source") or default
            for k in ("url", "doc_title", "fetched_at"):
                assert src.get(k), f"{path}: contract {code} source missing {k!r}"
            # ISO-8601 sanity
            datetime.fromisoformat(src["fetched_at"].replace("Z", "+00:00"))
