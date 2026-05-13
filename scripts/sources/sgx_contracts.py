"""SGX FX-futures contract listings — `data/fx_exchange/SGX_contracts.json`.

Hierarchy:
1. **Scrape** — HTTP GET the per-product contract-specifications page and
   parse listed-months rows. Currently a stub that returns no rows; the hook
   is in place so future revisions can populate Tier 1 without touching the
   rest of the flow.
2. **Derive** — for any product where scrape returned no rows, generate the
   standard SGX FX series (spot month + next 2 calendar months + 4
   quarterlies) by calling `fx_holiday_calculator.future.calculate_future_dates`
   per (pair, month). LTD = 3rd-Wednesday − 2 BDs, settlement = 3rd-Wednesday
   mod-following, both against `SGX ∪ base/quote RTGS`.
3. **Manual rows** — any pre-existing `derivation_mode == "manual"` row in
   the target JSON is preserved via `merge_preserving_manual`.

Contract codes follow the SGX convention: ``<product>+<month_letter>+<year_digit>``
where the product is e.g. ``UC`` for USD/CNH (TC). Year digit is the last
digit of the calendar year — `contract_month` carries the full ``YYYY-MM``
for disambiguation.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from fx_holiday_calculator.calendars.loader import load_exchange_calendar, load_rtgs_calendar
from fx_holiday_calculator.future import calculate_future_dates
from fx_holiday_calculator.pairs import parse_pair
from scripts.sources._contracts_io import merge_preserving_manual
from scripts.sources._provenance import now_iso_utc, write_calendar_json

_FETCHER = "scripts/sources/sgx_contracts.py@v1"
_VENUE = "SGX"
_SPECS_LANDING_URL = "https://www.sgx.com/derivatives/products/currency-futures"
_DOC_TITLE = "SGX — Currency Futures Contract Specifications"

# Mapping from pair to (SGX product code, product display name).
# Pairs not registered or not listed on SGX are filtered out at derive time.
_SGX_PRODUCTS: dict[str, tuple[str, str]] = {
    "USD/CNH": ("UC", "USD/CNH (TC) Futures"),
    "USD/INR": ("IU", "USD/INR Futures"),
    "KRW/USD": ("KU", "Korean Won / USD Futures"),
    "USD/SGD": ("US", "USD/SGD Futures"),
    "EUR/USD": ("EU", "EUR/USD Futures"),
    "GBP/USD": ("BU", "GBP/USD Futures"),
    "AUD/USD": ("AU", "AUD/USD Futures"),
}

# SGX month letter codes (Jan..Dec).
_MONTH_LETTERS = "FGHJKMNQUVXZ"

# Standard SGX FX quarterlies (Mar/Jun/Sep/Dec).
_QUARTERLY_MONTHS = (3, 6, 9, 12)


def _contract_code(product_code: str, year: int, month: int) -> str:
    return f"{product_code}{_MONTH_LETTERS[month - 1]}{year % 10}"


def _sgx_months(today: date, year_range: tuple[int, int]) -> list[tuple[int, int]]:
    """Return sorted unique (year, month) tuples covering the SGX standard
    listing window: spot month + next 2 calendar months + 4 quarterlies,
    filtered to `year_range` (inclusive)."""
    months: set[tuple[int, int]] = set()
    y, m = today.year, today.month
    # Spot + next 2 calendar months.
    for _ in range(3):
        months.add((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    # 4 quarterlies starting at the quarter on or after today's month.
    qcount = 0
    qy = today.year
    while qcount < 4:
        for qm in _QUARTERLY_MONTHS:
            if (qy, qm) < (today.year, today.month):
                continue
            months.add((qy, qm))
            qcount += 1
            if qcount >= 4:
                break
        qy += 1
    return sorted(ym for ym in months if year_range[0] <= ym[0] <= year_range[1])


def _try_scrape(year_range: tuple[int, int]) -> list[dict]:
    """Attempt to scrape the SGX contract-specs pages. Returns an empty list
    if scraping fails or yields nothing — callers fall through to derive.

    Stub for v1: returns []. Future revisions populate this from per-product
    fixtures recorded under `tests/fixtures/sources/sgx_contracts/`.
    """
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
    months = _sgx_months(today, year_range)

    for pair_str, (prod_code, prod_name) in _SGX_PRODUCTS.items():
        try:
            pair = parse_pair(pair_str)
        except Exception:
            continue
        if _VENUE not in pair.listed_on:
            continue
        # Skip pairs whose legs aren't both bundled — INR/KRW/SGD/etc.
        try:
            rtgs(pair.base)
            rtgs(pair.quote)
        except Exception as e:
            sys.stderr.write(f"[sgx_contracts] skipping {pair_str}: missing RTGS calendar ({e})\n")
            continue
        for y, m in months:
            try:
                result = calculate_future_dates(
                    pair=pair,
                    venue=_VENUE,
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
                    "code": _contract_code(prod_code, y, m),
                    "pair": pair_str,
                    "product_name": prod_name,
                    "contract_month": f"{y:04d}-{m:02d}",
                    "last_trading_day": result.last_trade_date.isoformat(),
                    "settlement_date": result.delivery_date.isoformat(),
                    "first_notice_day": None,
                    "derivation_mode": "derived",
                    "source": None,
                    "note": (
                        "Derived from SGX's standard rule (3rd-Wednesday IMM "
                        "convention, mod-following on SGX ∪ base/quote RTGS). "
                        "For products where a leg currency is not bundled "
                        "(e.g. INR, KRW), the BD-counting falls back to "
                        "whichever calendars are present. Verify against the "
                        "official contract specs page before trading."
                    ),
                }
            )
    return rows


def _validity_window(rows: list[dict]) -> tuple[date, date]:
    if not rows:
        today = date.today()
        return today, date(today.year + 1, 12, 31)
    ltds = [date.fromisoformat(r["last_trading_day"]) for r in rows]
    return min(ltds), max(ltds)


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
        "calendar_kind": "EXCHANGE_CONTRACTS",
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

    out_path = target_root / "fx_exchange" / f"{_VENUE}_contracts.json"
    merged = merge_preserving_manual(out_path, payload)
    write_calendar_json(out_path, merged)
    return out_path
