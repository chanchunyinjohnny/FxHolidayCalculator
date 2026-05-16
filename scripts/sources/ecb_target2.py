"""TARGET2 closure days — deterministic rule, no scraping.

Source citation: https://www.ecb.europa.eu/paym/target/t2/html/index.en.html
The rule is encoded directly in this module per docs/data-sources.md#eur--target2.

Note: in March 2023 the Eurosystem consolidated TARGET2 and T2S into the
new T2 RTGS service. The six TARGET closing days (1 Jan, Good Friday,
Easter Monday, 1 May, 25 Dec, 26 Dec) are unchanged from TARGET2.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from dateutil.easter import easter

from scripts.sources._provenance import now_iso_utc, write_calendar_json, write_raw

_URL = "https://www.ecb.europa.eu/paym/target/t2/html/index.en.html"
_DOC_TITLE = "T2 — Eurosystem RTGS service (operating days)"
_FETCHER = "scripts/sources/ecb_target2.py@v2"


def _holidays_for_year(year: int) -> list[dict]:
    e = easter(year)
    return [
        {
            "date": date(year, 1, 1).isoformat(),
            "name": "New Year's Day",
            "source": None,
            "note": None,
        },
        {
            "date": (e - timedelta(days=2)).isoformat(),
            "name": "Good Friday",
            "source": None,
            "note": None,
        },
        {
            "date": (e + timedelta(days=1)).isoformat(),
            "name": "Easter Monday",
            "source": None,
            "note": None,
        },
        {"date": date(year, 5, 1).isoformat(), "name": "Labour Day", "source": None, "note": None},
        {
            "date": date(year, 12, 25).isoformat(),
            "name": "Christmas Day",
            "source": None,
            "note": None,
        },
        {
            "date": date(year, 12, 26).isoformat(),
            "name": "Christmas Holiday",
            "source": None,
            "note": None,
        },
    ]


def build_payload(year_range: tuple[int, int]) -> dict:
    holidays: list[dict] = []
    for y in range(year_range[0], year_range[1] + 1):
        holidays += _holidays_for_year(y)
    holidays.sort(key=lambda h: h["date"])
    return {
        "schema_version": 3,
        "currency": "EUR",
        "calendar_kind": "RTGS",
        "calendar_name": "TARGET2",
        "operator": "Eurosystem (European Central Bank)",
        "valid_from": f"{year_range[0]}-01-01",
        "valid_until": f"{year_range[1]}-12-31",
        "default_source": {
            "url": _URL,
            "doc_title": _DOC_TITLE,
            "fetched_at": now_iso_utc(),
            "fetcher": _FETCHER,
        },
        "holidays": holidays,
    }


def fetch(year_range: tuple[int, int], data_root: Path) -> Path:
    payload = build_payload(year_range)
    out = data_root / "fx_rtgs" / "EUR.json"
    write_calendar_json(out, payload)
    raw_dir = data_root / "fx_rtgs" / "_raw"
    write_raw(
        raw_dir,
        "EUR.txt",
        f"# {_DOC_TITLE}\n# Source: {_URL}\n# Rule encoded in {_FETCHER}\n".encode(),
    )
    return out


if __name__ == "__main__":
    import sys

    fetch((2026, 2030), Path(__file__).parents[2] / "data")
    sys.exit(0)
