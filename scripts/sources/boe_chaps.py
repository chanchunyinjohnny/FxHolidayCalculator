"""GBP CHAPS holidays — gov.uk bank-holidays JSON API.

See docs/data-sources.md#gbp--chaps."""
from __future__ import annotations

import json
from pathlib import Path

import requests

from scripts.sources._provenance import now_iso_utc, write_calendar_json, write_raw

_URL = "https://www.gov.uk/bank-holidays.json"
_DOC_TITLE = "UK government bank holidays (England and Wales)"
_FETCHER = "scripts/sources/boe_chaps.py@v1"
_DIVISION = "england-and-wales"


def parse_document(raw: bytes, year_range: tuple[int, int]) -> list[dict]:
    """Pure: bytes (gov.uk JSON content) -> list of holiday dicts."""
    blob = json.loads(raw.decode("utf-8"))
    division = blob.get(_DIVISION)
    if not division or "events" not in division:
        raise RuntimeError(f"gov.uk JSON missing {_DIVISION} division")
    out: list[dict] = []
    for ev in division["events"]:
        date_str = ev.get("date", "")
        if len(date_str) < 4:
            continue
        try:
            year = int(date_str[:4])
        except ValueError:
            continue
        if not (year_range[0] <= year <= year_range[1]):
            continue
        notes = ev.get("notes") or None
        out.append({
            "date": date_str,
            "name": ev.get("title", ""),
            "source": None,
            "note": notes if notes else None,
        })
    out.sort(key=lambda h: h["date"])
    return out


def build_payload(year_range: tuple[int, int], raw: bytes) -> dict:
    """Wraps parse_document with calendar metadata."""
    return {
        "schema_version": 1,
        "currency": "GBP",
        "calendar_kind": "RTGS",
        "calendar_name": "CHAPS",
        "operator": "Bank of England",
        "default_source": {
            "url": _URL,
            "doc_title": _DOC_TITLE,
            "fetched_at": now_iso_utc(),
            "fetcher": _FETCHER,
        },
        "holidays": parse_document(raw, year_range),
    }


def fetch(year_range: tuple[int, int], data_root: Path) -> Path:
    """HTTP GET https://www.gov.uk/bank-holidays.json; persist raw + JSON."""
    resp = requests.get(_URL, timeout=30,
                        headers={"User-Agent": "fx-holiday-calculator/0.1"})
    resp.raise_for_status()
    raw = resp.content
    payload = build_payload(year_range, raw)
    out = data_root / "fx_rtgs" / "GBP.json"
    write_calendar_json(out, payload)
    raw_dir = data_root / "fx_rtgs" / "_raw"
    write_raw(raw_dir, "GBP.json", raw)
    return out


if __name__ == "__main__":
    import sys
    fetch((2026, 2030), Path(__file__).parents[2] / "data")
    sys.exit(0)
