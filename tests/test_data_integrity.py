import json
from datetime import datetime
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).parents[1] / "data"
RTGS_DIR = DATA_DIR / "fx_rtgs"
EXCH_DIR = DATA_DIR / "fx_exchange"


def _all_calendar_files() -> list[Path]:
    files: list[Path] = []
    if RTGS_DIR.exists():
        files += sorted(p for p in RTGS_DIR.glob("*.json") if not p.name.startswith("_"))
    if EXCH_DIR.exists():
        files += sorted(p for p in EXCH_DIR.glob("*.json") if not p.name.startswith("_"))
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
