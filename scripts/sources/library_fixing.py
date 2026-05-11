"""Library-sourced fixing calendars (stopgap until primary fetchers run live).

When `scripts/sources/{cfets_cny,kftc_krw,taifx_twd}.py` can be run against
live upstream URLs (Task 1.6 of the FX Products plan), the JSON files they
produce will REPLACE the library-sourced ones generated here. Until then, we
use `python-holidays` country calendars as a faithful approximation of the
financial-market closure days:

  CNY: holidays.China        -> covers mainland China public holidays. CFETS
                                trading calendar closely tracks these.
  KRW: holidays.SouthKorea   -> KFTC FX market calendar closely tracks these.
  TWD: holidays.Taiwan       -> Taipei Forex calendar closely tracks these.

NDF computations using library-sourced fixing data are still authoritative
(the engine uses `is_holiday`/`get_holiday` regardless of `source_origin`),
but the UI surfaces a caveat banner so operators know to verify against the
official document for high-stakes decisions.
"""

from __future__ import annotations

import sys
from pathlib import Path

import holidays as _holidays

from scripts.sources._provenance import now_iso_utc, write_calendar_json

_FETCHER = "scripts/sources/library_fixing.py@v1"

# Per-currency metadata for the produced JSON. The default_source `url` and
# `doc_title` point to python-holidays itself (honest provenance), with a
# `note` in each holiday entry naming the underlying country calendar.
_CURRENCIES: dict[str, dict] = {
    "CNY": {
        "country_class": "China",
        "calendar_name": "CFETS USD/CNY Central Parity (library-sourced)",
        "operator": "python-holidays (CFETS pending live fetch)",
    },
    "KRW": {
        "country_class": "SouthKorea",
        "calendar_name": "KFTC USD/KRW MAR (library-sourced)",
        "operator": "python-holidays (KFTC pending live fetch)",
    },
    "TWD": {
        "country_class": "Taiwan",
        "calendar_name": "Taipei Forex USD/TWD (library-sourced)",
        "operator": "python-holidays (Taipei Forex pending live fetch)",
    },
}


def _holidays_for(country_class: str, year_range: tuple[int, int]) -> list[dict]:
    cls = getattr(_holidays, country_class)
    years = list(range(year_range[0], year_range[1] + 1))
    hol = cls(years=years)
    out: list[dict] = []
    for d, name in sorted(hol.items()):
        out.append(
            {
                "date": d.isoformat(),
                "name": str(name),
                "source": None,
                "note": f"python-holidays {country_class}; v{_holidays.__version__}",
            }
        )
    return out


def build_payload(year_range: tuple[int, int], currency: str) -> dict:
    meta = _CURRENCIES[currency]
    return {
        "schema_version": 3,
        "currency": currency,
        "calendar_kind": "FIXING",
        "calendar_name": meta["calendar_name"],
        "operator": meta["operator"],
        "valid_from": f"{year_range[0]}-01-01",
        "valid_until": f"{year_range[1]}-12-31",
        "default_source": {
            "url": "https://pypi.org/project/holidays/",
            "doc_title": (
                f"python-holidays library, calendar={meta['country_class']} "
                f"(stopgap until primary fetch from CFETS/KFTC/Taipei Forex)"
            ),
            "fetched_at": now_iso_utc(),
            "fetcher": _FETCHER,
        },
        "holidays": _holidays_for(meta["country_class"], year_range),
    }


def fetch(year_range: tuple[int, int], data_root: Path, currency: str) -> Path:
    """Refresh-CLI entry point: produce data/fx_fixing/<CCY>.json from python-holidays."""
    payload = build_payload(year_range, currency)
    out = data_root / "fx_fixing" / f"{currency}.json"
    write_calendar_json(out, payload)
    return out


if __name__ == "__main__":
    for ccy in _CURRENCIES:
        out_path = fetch((2026, 2030), Path(__file__).parents[2] / "data", ccy)
        print(f"  [OK] {out_path}")
    sys.exit(0)
