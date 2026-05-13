"""CME FX-options contract listings — `data/fx_exchange/CME_options_contracts.json`.

Hierarchy mirrors `cme_contracts.py`:
1. **Scrape** — stub (returns []) pending per-product fixtures.
2. **Derive** — generates the standard CME FX series via
   `fx_holiday_calculator.option_listed.derive_contract` for each (pair, month).
3. **Manual rows** — preserved by `merge_preserving_manual`.

Contract codes follow `<product_root>+<month_letter>+<year_digit>` where the
product root is e.g. `EUO` for Euro FX Options on Futures. Year digit is the
last digit of the calendar year.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fx_holiday_calculator.calendars.loader import load_exchange_calendar, load_rtgs_calendar
from fx_holiday_calculator.option_listed import derive_contract
from fx_holiday_calculator.pairs import parse_pair
from scripts.sources._contracts_io import merge_preserving_manual
from scripts.sources._provenance import now_iso_utc, write_calendar_json

_FETCHER = "scripts/sources/cme_options_contracts.py@v1"
_VENUE = "CME"
_SPECS_LANDING_URL = "https://www.cmegroup.com/markets/fx.html"
_DOC_TITLE = "CME Group — FX Options Contract Specifications"

# Mapping from pair to (product root code, descriptive name). Root codes are
# venue-defined; the {month_letter}{year_digit} suffix is appended at format
# time. For listed FX options on futures the canonical root differs per product
# at CME; we use a stable shorthand here keyed off the underlying futures root
# (e.g. 6E -> EUO) and surface the full product_name in the JSON.
_CME_PRODUCTS: dict[str, tuple[str, str]] = {
    "EUR/USD": ("EUO", "Options on Euro FX Futures"),
    "GBP/USD": ("GBO", "Options on British Pound Futures"),
    "USD/JPY": ("JYO", "Options on Japanese Yen Futures"),
    "AUD/USD": ("ADO", "Options on Australian Dollar Futures"),
    "USD/CAD": ("CDO", "Options on Canadian Dollar Futures"),
    "USD/CHF": ("SFO", "Options on Swiss Franc Futures"),
    "NZD/USD": ("NEO", "Options on New Zealand Dollar Futures"),
}

_MONTH_LETTERS = "FGHJKMNQUVXZ"
_QUARTERLY_MONTHS = (3, 6, 9, 12)


def _contract_code(product_root: str, year: int, month: int) -> str:
    return f"{product_root}{_MONTH_LETTERS[month - 1]}{year % 10}"


def _quarterly_months(today: date, count: int = 6) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    year = today.year
    while len(out) < count:
        for m in _QUARTERLY_MONTHS:
            if (year, m) < (today.year, today.month):
                continue
            out.append((year, m))
            if len(out) >= count:
                break
        year += 1
    return out


def _serial_months(today: date, quarterlies: list[tuple[int, int]]) -> list[tuple[int, int]]:
    qset = set(quarterlies)
    out: list[tuple[int, int]] = []
    y, m = today.year, today.month
    while len(out) < 2:
        m += 1
        if m > 12:
            m = 1
            y += 1
        if m in _QUARTERLY_MONTHS:
            continue
        if (y, m) in qset:
            continue
        out.append((y, m))
    return out


def _try_scrape(year_range: tuple[int, int]) -> list[dict]:
    return []


def _derive_rows(year_range: tuple[int, int], target_root: Path) -> list[dict]:
    today = date.today()
    rtgs_root = target_root / "fx_rtgs"
    exch_root = target_root / "fx_exchange"
    _rtgs_cache: dict[str, object] = {}

    def rtgs(c: str):
        if c not in _rtgs_cache:
            _rtgs_cache[c] = load_rtgs_calendar(c, root=rtgs_root)
        return _rtgs_cache[c]

    exch_cal = load_exchange_calendar(_VENUE, root=exch_root)

    rows: list[dict] = []
    quarterlies = _quarterly_months(today, count=6)
    serials = _serial_months(today, quarterlies)
    months = sorted(quarterlies + serials)
    months = [(y, m) for (y, m) in months if year_range[0] <= y <= year_range[1]]

    for pair_str, (prod_root, prod_name) in _CME_PRODUCTS.items():
        try:
            pair = parse_pair(pair_str)
        except Exception:
            continue
        if _VENUE not in pair.listed_on:
            continue
        for y, m in months:
            try:
                result = derive_contract(
                    venue=_VENUE,
                    pair=pair,
                    contract_month=(y, m),
                    rtgs_calendars={
                        pair.base: rtgs(pair.base),  # type: ignore[arg-type]
                        pair.quote: rtgs(pair.quote),  # type: ignore[arg-type]
                    },
                    exchange_calendar=exch_cal,
                )
            except Exception:
                continue
            rows.append(
                {
                    "code": _contract_code(prod_root, y, m),
                    "pair": pair_str,
                    "product_name": prod_name,
                    "contract_month": f"{y:04d}-{m:02d}",
                    "expiry_date": result.expiry_date.isoformat(),
                    "delivery_date": result.delivery_date.isoformat(),
                    "derivation_mode": "derived",
                    "source": None,
                    "note": (
                        "Derived from CME's standard rule (expiry = 2 BDs prior "
                        "to 3rd Wed of contract month on CME calendar; delivery "
                        "= expiry + spot offset on RTGS{base, quote}). Verify "
                        "against the official contract specs page before trading."
                    ),
                }
            )
    return rows


def _validity_window(rows: list[dict]) -> tuple[date, date]:
    if not rows:
        today = date.today()
        return today, date(today.year + 1, 12, 31)
    expiries = [date.fromisoformat(r["expiry_date"]) for r in rows]
    return min(expiries), max(expiries)


def fetch(year_range: tuple[int, int], target_root: Path) -> Path:
    scraped = _try_scrape(year_range)
    if scraped:
        rows = scraped
        default_mode = "scrape"
    else:
        rows = _derive_rows(year_range, target_root)
        default_mode = "derived"

    vf, vu = _validity_window(rows)
    payload = {
        "schema_version": 1,
        "venue": _VENUE,
        "calendar_kind": "EXCHANGE_OPTIONS_CONTRACTS",
        "valid_from": vf.isoformat(),
        "valid_until": vu.isoformat(),
        "default_source": {
            "url": _SPECS_LANDING_URL,
            "doc_title": _DOC_TITLE,
            "fetched_at": now_iso_utc(),
            "fetcher": _FETCHER,
            "default_derivation_mode": default_mode,
        },
        "contracts": rows,
    }

    out_path = target_root / "fx_exchange" / f"{_VENUE}_options_contracts.json"
    merged = merge_preserving_manual(out_path, payload)
    write_calendar_json(out_path, merged)
    return out_path
