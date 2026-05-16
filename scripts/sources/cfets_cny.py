"""CNY fixing calendar — CFETS / China Foreign Exchange Trade System (PBoC).

Upstream: the public CFETS trading-calendar page at
``https://www.chinamoney.com.cn/english/svctcd/`` loads its data via a JSON
API at ``/ags/ms/cm-s-holiday/depFxTradingCal``. This fetcher calls that API
directly and extracts the per-currency CNY closure dates from the response.

Each API call returns approximately three consecutive years (typically
previous / current / next) under ``data.currency[year]["CNY"]`` as strings
of the form ``"Jan 01"``. Holiday names are not part of the API payload, so
they are enriched at parse time via ``python-holidays.China`` (en_US locale).

See docs/data-sources.md#cny--cfets for source documentation.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import date
from pathlib import Path

import holidays as _holidays_lib

from scripts.sources._provenance import now_iso_utc, write_calendar_json, write_raw

_PAGE_URL = "https://www.chinamoney.com.cn/english/svctcd/"
_API_BASE = "https://www.chinamoney.com.cn/ags/ms/cm-s-holiday/depFxTradingCal"
_DOC_TITLE = "CFETS FX Trading Calendar (Foreign Exchange Services)"
_FETCHER = "scripts/sources/cfets_cny.py@v2"
_USER_AGENT = "fx-holiday-calculator/0.1"
_FALLBACK_NAME = "CFETS CNY market closure"

# Public re-exports for downstream fetchers (e.g. hkma_chats_cnh) that need to
# cite the CFETS page as the source for the PRC leg of CNH closures. These are
# the canonical, contract-stable names; the underscore-prefixed originals
# remain for internal callers but should be considered an implementation detail.
PAGE_URL = _PAGE_URL
DOC_TITLE = _DOC_TITLE
FETCHER = _FETCHER

_MONTH_ABBR = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


def _parse_mmm_dd(s: str, year: int) -> date | None:
    parts = s.strip().split()
    if len(parts) != 2:
        return None
    month = _MONTH_ABBR.get(parts[0])
    if month is None:
        return None
    try:
        return date(year, month, int(parts[1]))
    except ValueError:
        return None


def _holiday_name(d: date) -> str | None:
    """Look up the English (en_US) Chinese-holiday name for a given date.

    CFETS does not publish names alongside dates in the API; well-known
    mainland public holidays are labelled from python-holidays. CFETS-specific
    closures not in python-holidays (e.g. working-Saturday make-up days) fall
    back to a generic label at the caller.
    """
    cls = getattr(_holidays_lib, "China", None)
    if cls is None:
        return None
    try:
        cal = cls(years=d.year, language="en_US")
    except Exception:
        return None
    name = cal.get(d)
    return str(name) if name else None


def parse_document(raw: bytes, year_range: tuple[int, int]) -> list[dict]:
    """Parse a single CFETS API JSON response into v3 holiday entries
    for years within ``year_range``.

    Each response carries multiple years' data under
    ``data.currency[year_str]["CNY"]``. Out-of-range years are filtered out
    and duplicates (across overlapping responses) are deduped at the caller.
    """
    blob = json.loads(raw.decode("utf-8", errors="replace"))
    by_year = (blob.get("data") or {}).get("currency") or {}
    out: list[dict] = []
    seen: set[str] = set()
    for year_key, currencies in by_year.items():
        try:
            year = int(year_key)
        except (TypeError, ValueError):
            continue
        if not (year_range[0] <= year <= year_range[1]):
            continue
        for s in currencies.get("CNY") or []:
            d = _parse_mmm_dd(s, year)
            if d is None:
                continue
            iso = d.isoformat()
            if iso in seen:
                continue
            seen.add(iso)
            name = _holiday_name(d) or _FALLBACK_NAME
            out.append({"date": iso, "name": name, "source": None, "note": None})
    out.sort(key=lambda h: h["date"])
    return out


def _year_list(raw: bytes) -> list[int]:
    try:
        blob = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return []
    out: list[int] = []
    for y in (blob.get("data") or {}).get("yearList") or []:
        try:
            out.append(int(y))
        except (TypeError, ValueError):
            continue
    return out


def build_payload(year_range: tuple[int, int], raw: bytes) -> dict:
    """Build a v3 calendar payload from a single API response.

    The validity window is clamped to the intersection of ``year_range`` and
    the years actually returned by the response (``data.yearList``), so the
    downstream FixingCalendar correctly raises CalendarRangeError for years
    CFETS has not yet published.
    """
    holidays_list = parse_document(raw, year_range)
    covered = sorted(set(_year_list(raw)) & set(range(year_range[0], year_range[1] + 1)))
    if covered:
        vf = f"{covered[0]}-01-01"
        vu = f"{covered[-1]}-12-31"
    else:
        vf = f"{year_range[0]}-01-01"
        vu = f"{year_range[1]}-12-31"
    return {
        "schema_version": 3,
        "currency": "CNY",
        "calendar_kind": "FIXING",
        "calendar_name": "CFETS FX Trading Calendar (CNY)",
        "operator": "China Foreign Exchange Trade System (PBoC)",
        "valid_from": vf,
        "valid_until": vu,
        "default_source": {
            "url": _PAGE_URL,
            "doc_title": _DOC_TITLE,
            "fetched_at": now_iso_utc(),
            "fetcher": _FETCHER,
        },
        "holidays": holidays_list,
    }


def _fetch_year(year: int, timeout: float = 30.0) -> bytes:
    req = urllib.request.Request(
        f"{_API_BASE}?selectedYear={year}",
        headers={"User-Agent": _USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch(year_range: tuple[int, int], data_root: Path) -> Path:
    """Fetch live CFETS data and write ``data/fx_fixing/CNY.json``.

    Each API call returns ~3 consecutive years. We start at ``year_range[0]``
    and step forward to the year just past the last yearList we received,
    stopping early when a response fails to extend coverage (i.e. CFETS has
    not yet published further years).
    """
    raw_dir = data_root / "fx_fixing" / "_raw"
    merged: dict[str, dict] = {}
    covered: set[int] = set()
    last_exc: Exception | None = None
    next_year = year_range[0]
    while next_year <= year_range[1]:
        try:
            raw = _fetch_year(next_year)
        except Exception as exc:
            last_exc = exc
            break
        write_raw(raw_dir, f"CNY-{next_year}.json", raw)
        api_years = _year_list(raw)
        api_max = max(api_years, default=-1)
        prev_max = max(covered, default=-1)
        covered.update(api_years)
        for h in parse_document(raw, year_range):
            merged[h["date"]] = h
        if api_max <= prev_max:
            break
        next_year = api_max + 1

    if not merged:
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("CFETS API returned no in-range data")

    in_range = sorted(covered & set(range(year_range[0], year_range[1] + 1)))
    vf_year = in_range[0] if in_range else year_range[0]
    vu_year = in_range[-1] if in_range else year_range[1]
    payload = {
        "schema_version": 3,
        "currency": "CNY",
        "calendar_kind": "FIXING",
        "calendar_name": "CFETS FX Trading Calendar (CNY)",
        "operator": "China Foreign Exchange Trade System (PBoC)",
        "valid_from": f"{vf_year}-01-01",
        "valid_until": f"{vu_year}-12-31",
        "default_source": {
            "url": _PAGE_URL,
            "doc_title": _DOC_TITLE,
            "fetched_at": now_iso_utc(),
            "fetcher": _FETCHER,
        },
        "holidays": [merged[k] for k in sorted(merged)],
    }
    out = data_root / "fx_fixing" / "CNY.json"
    write_calendar_json(out, payload)
    return out


if __name__ == "__main__":
    import sys

    fetch((2026, 2030), Path(__file__).parents[2] / "data")
    sys.exit(0)
