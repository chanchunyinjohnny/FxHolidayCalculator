"""Library-sourced exchange holiday calendars (hybrid v1 floor).

This generator produces ``data/fx_exchange/<VENUE>.json`` files from the
``exchange_calendars`` library as the v1 floor for SGX / HKEX / CME holidays.

Why a library and not a primary-source scrape:
- SGX has rearchitected the holiday page into a JS SPA; the static HTML is an
  empty shell. The PDF available at SGX is a per-product calendar that does
  not lend itself to a single "venue is closed" signal.
- HKEX and CME pages are similarly hostile to plain-HTTP parsing.

See ``docs/data-sources.md`` for the full hybrid strategy and the caveats users
must understand (equity-session vs FX-derivative, per-product nature, library
coverage-horizon lag).

Primary-source overrides land in a follow-up phase. When a bundled JSON file
written by a primary-source fetcher exists, the loader prefers it; this
generator only fills in venues that have no primary-source data.
"""

from __future__ import annotations

import sys
from datetime import date
from importlib.metadata import version
from pathlib import Path

import exchange_calendars as ec
import holidays as _hol_lib
import pandas as pd

from scripts.sources._provenance import now_iso_utc, write_calendar_json

_LIB_VERSION = version("exchange_calendars")
_FETCHER = "scripts/sources/library_exchange.py@v1"
_LIBRARY_NOTE = (
    "library-sourced (exchange_calendars equity session). "
    "Not FX-product-specific — see docs/data-sources.md."
)

# Per-venue config: library code, product list (from docs/data-sources.md),
# and the python-holidays calendar to enrich adhoc-date names.
_VENUES: dict[str, dict] = {
    "SGX": {
        "library_code": "XSES",
        "products": [
            "USD/CNH Futures",
            "USD/INR Futures",
            "KRW/USD Futures",
            "JPY/SGD Futures",
            "EUR/USD Futures",
            "GBP/USD Futures",
            "AUD/USD Futures",
        ],
        "naming_calendar": "Singapore",
    },
    "HKEX": {
        "library_code": "XHKG",
        "products": [
            "USD/CNH Futures",
            "Mini USD/CNH Futures",
            "EUR/CNH Futures",
            "JPY/CNH Futures",
            "AUD/CNH Futures",
            "USD/HKD Futures",
        ],
        "naming_calendar": "HongKong",
    },
    "CME": {
        "library_code": "CMES",
        "products": [
            "EUR/USD Futures",
            "JPY/USD Futures",
            "GBP/USD Futures",
            "USD/CNH Futures",
            "USD/MXN Futures",
            "USD/BRL Futures",
            "USD/ZAR Futures",
        ],
        "naming_calendar": "UnitedStates",
    },
}


def _name_via_python_holidays(d: date, country_name: str) -> str | None:
    cls = getattr(_hol_lib, country_name, None)
    if cls is None:
        return None
    try:
        cal = cls(years=d.year)
    except Exception:
        return None
    return cal.get(d)


def _extract_holidays(
    library_code: str,
    naming_country: str,
    year_range: tuple[int, int],
) -> tuple[date, date, list[dict]]:
    """Return (effective_valid_from, effective_valid_until, holidays_list).

    Clamps the requested year_range to what the library can actually answer.
    """
    cal = ec.get_calendar(library_code)
    requested_from = date(year_range[0], 1, 1)
    requested_until = date(year_range[1], 12, 31)
    lib_first = cal.first_session.date()
    lib_last = cal.last_session.date()
    valid_from = max(requested_from, lib_first)
    valid_until = min(requested_until, lib_last)
    if valid_until < valid_from:
        raise RuntimeError(
            f"{library_code}: no overlap between requested range "
            f"[{requested_from} .. {requested_until}] and library coverage "
            f"[{lib_first} .. {lib_last}]"
        )

    start_ts = pd.Timestamp(valid_from)
    end_ts = pd.Timestamp(valid_until)
    sessions = set(cal.sessions_in_range(start_ts, end_ts))
    weekdays = pd.bdate_range(start_ts, end_ts)
    closed = sorted({d.date() for d in weekdays if d not in sessions})

    # Names: prefer regular_holidays rule calendar (named recurring rules),
    # fall back to python-holidays for adhoc lunar/Islamic dates.
    rule_names: dict[date, str] = {}
    if cal.regular_holidays is not None:
        named = cal.regular_holidays.holidays(start_ts, end_ts, return_name=True)
        for ts, nm in named.items():
            rule_names[ts.date()] = nm

    holidays_list: list[dict] = []
    for d in closed:
        name = rule_names.get(d) or _name_via_python_holidays(d, naming_country)
        if not name:
            name = "Exchange closure (library, unnamed adhoc)"
        holidays_list.append(
            {
                "date": d.isoformat(),
                "name": name,
                "source": None,
                "note": _LIBRARY_NOTE,
            }
        )
    return valid_from, valid_until, holidays_list


def build_payload(venue: str, year_range: tuple[int, int]) -> dict:
    cfg = _VENUES[venue]
    valid_from, valid_until, holidays_list = _extract_holidays(
        cfg["library_code"], cfg["naming_calendar"], year_range
    )
    return {
        "schema_version": 3,
        "venue": venue,
        "calendar_kind": "EXCHANGE",
        "products": cfg["products"],
        "valid_from": valid_from.isoformat(),
        "valid_until": valid_until.isoformat(),
        "default_source": {
            "url": "https://pypi.org/project/exchange-calendars/",
            "doc_title": (
                f"exchange_calendars v{_LIB_VERSION}, "
                f"calendar={cfg['library_code']} (equity session)"
            ),
            "fetched_at": now_iso_utc(),
            "fetcher": _FETCHER,
        },
        "holidays": holidays_list,
    }


def fetch(year_range: tuple[int, int], data_root: Path, venue: str) -> Path:
    """Write data/fx_exchange/<venue>.json from the library.

    Does not overwrite a file marked source_origin="primary" — primary-source
    fetchers are authoritative when they exist.
    """
    payload = build_payload(venue, year_range)
    out = data_root / "fx_exchange" / f"{venue}.json"
    if out.exists():
        # Be conservative: if the existing file's fetcher does NOT mention
        # this script, treat it as primary-source data and leave it alone.
        import json

        existing = json.loads(out.read_text())
        existing_fetcher = existing.get("default_source", {}).get("fetcher", "")
        if "library_exchange" not in existing_fetcher:
            return out
    write_calendar_json(out, payload)
    return out


def fetch_all(year_range: tuple[int, int], data_root: Path) -> list[Path]:
    return [fetch(year_range, data_root, v) for v in _VENUES]


if __name__ == "__main__":
    out_paths = fetch_all((2026, 2030), Path(__file__).parents[2] / "data")
    for p in out_paths:
        print(f"  [OK] {p}")
    sys.exit(0)
