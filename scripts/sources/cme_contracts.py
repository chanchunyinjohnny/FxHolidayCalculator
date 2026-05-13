"""CME FX-futures contract listings — `data/fx_exchange/CME_contracts.json`.

Hierarchy:
1. **Scrape** — HTTP GET the per-product `*_contract_specifications.html`
   page and parse listed-months rows. Currently a stub that returns no rows
   (the page is JS-heavy and a robust parser requires per-product fixtures);
   the hook is in place so future revisions can populate Tier 1 without
   touching the rest of the flow.
2. **Derive** — for any product where scrape returned no rows, generate the
   standard CME FX series (6 nearest quarterlies + 2 serials, starting from
   today's month) by calling `fx_holiday_calculator.future.calculate_future_dates`
   per (pair, month). LTD = 3rd-Wednesday − 2 BDs, settlement = 3rd-Wednesday
   mod-following, both against `USD-Fedwire ∪ base-currency-RTGS`.
3. **Manual rows** — any pre-existing `derivation_mode == "manual"` row in
   the target JSON is preserved via `merge_preserving_manual`.

Contract codes follow the CME convention: ``<product>+<month_letter>+<year_digit>``
where the product is e.g. ``6E`` for Euro FX. Year digit is the last digit
of the calendar year (collisions on a decadal cycle are accepted — the
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

_FETCHER = "scripts/sources/cme_contracts.py@v1"
_VENUE = "CME"
_SPECS_LANDING_URL = "https://www.cmegroup.com/markets/fx.html"
_DOC_TITLE = "CME Group — FX Futures Contract Specifications"

# Mapping from pair to (CME product code, product display name).
# Direction matches CME's listing convention so contract codes look familiar
# to a trader; the lookup is direction-agnostic so the pair filter still
# matches whichever orientation the caller uses.
_CME_PRODUCTS: dict[str, tuple[str, str]] = {
    "EUR/USD": ("6E", "Euro FX Futures"),
    "GBP/USD": ("6B", "British Pound Futures"),
    "USD/JPY": ("6J", "Japanese Yen Futures"),
    "USD/CHF": ("6S", "Swiss Franc Futures"),
    "AUD/USD": ("6A", "Australian Dollar Futures"),
    "NZD/USD": ("6N", "New Zealand Dollar Futures"),
    "USD/CAD": ("6C", "Canadian Dollar Futures"),
    "USD/CNH": ("CNH", "Standard-Size USD/Offshore RMB (CNH) Futures"),
}

# CME month letter codes (Jan..Dec).
_MONTH_LETTERS = "FGHJKMNQUVXZ"

# Standard CME FX series: quarterlies (Mar/Jun/Sep/Dec) — 6 of them, rolling.
_QUARTERLY_MONTHS = (3, 6, 9, 12)


def _contract_code(product_code: str, year: int, month: int) -> str:
    return f"{product_code}{_MONTH_LETTERS[month - 1]}{year % 10}"


def _quarterly_months(today: date, count: int = 6) -> list[tuple[int, int]]:
    """Return `count` consecutive quarterly contract months starting at the
    quarter on or after `today`'s month."""
    out: list[tuple[int, int]] = []
    year = today.year
    # Walk forward over quarterlies until we have `count` of them.
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
    """The next 2 non-quarterly months after `today` that aren't already a quarterly."""
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
    """Attempt to scrape the CME contract-specs pages. Returns an empty list
    if scraping fails or yields nothing — callers fall through to derive.

    Stub for v1: returns []. Future revisions populate this from per-product
    fixtures recorded under `tests/fixtures/sources/cme_contracts/`.
    """
    return []


def _derive_rows(year_range: tuple[int, int], target_root: Path) -> list[dict]:
    today = date.today()
    rtgs_root = target_root / "fx_rtgs"
    exch_root = target_root / "fx_exchange"
    # Cache lookups: load each RTGS calendar once.
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
    # Filter to requested year_range (inclusive).
    months = [(y, m) for (y, m) in months if year_range[0] <= y <= year_range[1]]

    for pair_str, (prod_code, prod_name) in _CME_PRODUCTS.items():
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
                # window doesn't cover this far), skip it rather than abort
                # the whole fetcher.
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
                        "Derived from CME's standard rule (LTD = 3rd-Wednesday "
                        "− 2 BDs against USD-Fedwire ∪ base RTGS; settlement = "
                        "3rd-Wednesday mod-following). Verify against the "
                        "official contract specs page before trading."
                    ),
                }
            )
    return rows


def _validity_window(rows: list[dict]) -> tuple[date, date]:
    if not rows:
        # Default to a one-year window from today so the file is loadable.
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
