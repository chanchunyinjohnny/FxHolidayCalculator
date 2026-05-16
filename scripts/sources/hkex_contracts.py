"""HKEX FX-futures contract listings — `data/fx_exchange/HKEX_contracts.json`.

Hierarchy:
1. **Scrape** — HTTP GET the per-product HKEX contract-spec pages and parse
   the listed-months table. Currently a stub that returns no rows (the page
   is JS-heavy and a robust parser requires per-product fixtures); the hook
   is in place so future revisions can populate Tier 1 without touching the
   rest of the flow.
2. **Derive** — for any product where scrape returned no rows, generate the
   standard HKEX FX series (spot month + next 3 calendar months + 4
   quarterlies, up to 7 unique months per product) by calling
   `fx_holiday_calculator.future.calculate_future_dates` per (pair, month).
   LTD = 3rd-Wednesday − 2 BDs, settlement = 3rd-Wednesday mod-following,
   both against `HKEX ∪ base/quote-RTGS`.
3. **Manual rows** — any pre-existing `derivation_mode == "manual"` row in
   the target JSON is preserved via `merge_preserving_manual`.

Contract codes follow the HKEX convention: ``<product>+<month_letter>+<year_digit>``
where the product is e.g. ``CUS`` for USD/CNH Futures. Year digit is the last
digit of the calendar year (collisions on a decadal cycle are accepted — the
contract_month field carries the full ``YYYY-MM`` for disambiguation).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fx_holiday_calculator.calendars.loader import load_exchange_calendar, load_rtgs_calendar
from fx_holiday_calculator.future import calculate_future_dates
from fx_holiday_calculator.pairs import parse_pair
from scripts.sources._contracts_io import merge_preserving_manual
from scripts.sources._provenance import now_iso_utc, write_calendar_json

_FETCHER = "scripts/sources/hkex_contracts.py@v1"
_VENUE = "HKEX"
_SPECS_LANDING_URL = (
    "https://www.hkex.com.hk/Products/Listed-Derivatives/Foreign-Exchange?sc_lang=en"
)
_DOC_TITLE = "HKEX — Foreign Exchange (Listed Derivatives, Contract Specifications)"

# Mapping from pair to (HKEX product code, product display name).
_HKEX_PRODUCTS: dict[str, tuple[str, str]] = {
    "USD/CNH": ("CUS", "USD/CNH Futures"),
    "USD/HKD": ("UHD", "USD/HKD Futures"),
    "EUR/CNH": ("EUC", "EUR/CNH Futures"),
    "JPY/CNH": ("JPC", "JPY/CNH Futures"),
    "AUD/CNH": ("AUC", "AUD/CNH Futures"),
}

# HKEX month letter codes (Jan..Dec) — same convention as CME.
_MONTH_LETTERS = "FGHJKMNQUVXZ"

# Quarterly months (Mar/Jun/Sep/Dec).
_QUARTERLY_MONTHS = (3, 6, 9, 12)


def _contract_code(product_code: str, year: int, month: int) -> str:
    return f"{product_code}{_MONTH_LETTERS[month - 1]}{year % 10}"


def _hkex_months(today: date, year_range: tuple[int, int]) -> list[tuple[int, int]]:
    """Return the standard HKEX listed months for FX futures: the spot month
    plus the next 3 calendar months plus the next 4 quarterlies (March, June,
    September, December), deduplicated, sorted, and filtered to `year_range`."""
    out: set[tuple[int, int]] = set()
    # Spot month + next 3 calendar months (4 consecutive months total).
    y, m = today.year, today.month
    for _ in range(4):
        out.add((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    # Next 4 quarterlies on or after today's month.
    quarterlies: list[tuple[int, int]] = []
    yy = today.year
    while len(quarterlies) < 4:
        for qm in _QUARTERLY_MONTHS:
            if (yy, qm) < (today.year, today.month):
                continue
            quarterlies.append((yy, qm))
            if len(quarterlies) >= 4:
                break
        yy += 1
    out.update(quarterlies)
    months = sorted(out)
    return [(yy, mm) for (yy, mm) in months if year_range[0] <= yy <= year_range[1]]


def _try_scrape(year_range: tuple[int, int]) -> list[dict]:
    """Attempt to scrape the HKEX contract-specs pages. Returns an empty list
    if scraping fails or yields nothing — callers fall through to derive.

    Stub for v1: returns []. Future revisions populate this from per-product
    fixtures recorded under `tests/fixtures/sources/hkex_contracts/`.
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
    months = _hkex_months(today, year_range)

    for pair_str, (prod_code, prod_name) in _HKEX_PRODUCTS.items():
        try:
            pair = parse_pair(pair_str)
        except Exception:
            continue
        if _VENUE not in pair.listed_on:
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
                # If derivation fails for a particular month (e.g. calendar
                # window doesn't cover this far, or LTD already passed), skip
                # it rather than abort the whole fetcher.
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
                        "Derived from HKEX's standard rule (3rd-Wednesday IMM "
                        "convention, mod-following on HKEX ∪ base/quote RTGS). "
                        "Verify against the official contract specs page before "
                        "trading."
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
