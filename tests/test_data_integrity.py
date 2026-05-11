import json
from datetime import date, datetime
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).parents[1] / "data"
RTGS_DIR = DATA_DIR / "fx_rtgs"
EXCH_DIR = DATA_DIR / "fx_exchange"
FIXING_DIR = DATA_DIR / "fx_fixing"


def _all_calendar_files() -> list[Path]:
    files: list[Path] = []
    for d in (RTGS_DIR, EXCH_DIR, FIXING_DIR):
        if d.exists():
            files += sorted(p for p in d.glob("*.json") if not p.name.startswith("_"))
    return files


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
