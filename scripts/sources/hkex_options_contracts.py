"""HKEX FX-options contract listings — `data/fx_exchange/HKEX_options_contracts.json`.

Mirrors `hkex_contracts.py` but for the USD/CNH Options (CNHO) product.
Reference: HKEX CNHO-S-2 (July 2022 infosheet) — "Expiry Day: Two Trading
Days prior to the Final Settlement Day"; FSD = 3rd Wed rolled to next BD.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fx_holiday_calculator.calendars.loader import load_exchange_calendar, load_rtgs_calendar
from fx_holiday_calculator.option_listed import derive_contract
from fx_holiday_calculator.pairs import parse_pair
from scripts.sources._contracts_io import merge_preserving_manual
from scripts.sources._provenance import now_iso_utc, write_calendar_json

_FETCHER = "scripts/sources/hkex_options_contracts.py@v1"
_VENUE = "HKEX"
_SPECS_LANDING_URL = "https://www.hkex.com.hk/Products/Listed-Derivatives/Currency?sc_lang=en"
_DOC_TITLE = "HKEX — Listed Currency Derivatives (Contract Specifications, USD/CNH Options)"

_HKEX_PRODUCTS: dict[str, tuple[str, str]] = {
    "USD/CNH": ("CUSO", "USD/CNH Options (CNHO)"),
}

_MONTH_LETTERS = "FGHJKMNQUVXZ"
_QUARTERLY_MONTHS = (3, 6, 9, 12)


def _contract_code(product_root: str, year: int, month: int) -> str:
    return f"{product_root}{_MONTH_LETTERS[month - 1]}{year % 10}"


def _hkex_months(today: date, year_range: tuple[int, int]) -> list[tuple[int, int]]:
    out: set[tuple[int, int]] = set()
    y, m = today.year, today.month
    for _ in range(4):
        out.add((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
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

    for pair_str, (prod_root, prod_name) in _HKEX_PRODUCTS.items():
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
                        "Derived from HKEX CNHO-S-2 (expiry = 2 Trading Days prior "
                        "to FSD; FSD = 3rd-Wed rolled to next BD on HKEX). Verify "
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
