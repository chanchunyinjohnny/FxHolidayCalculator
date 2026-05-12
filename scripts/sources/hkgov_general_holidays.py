"""HKD CHATS settlement holidays — Hong Kong general holidays (Cap. 149).

Regulatory chain
----------------

HKICL's *HKD Clearing House Rules* (the operating-rules document the HKMA-
appointed system operator publishes for HKD CHATS participants) define a
"Working Day" as::

    a day other than a Saturday, a general holiday as specified in the
    General Holidays Ordinance (Cap. 149 of the Laws of Hong Kong) and
    any other day on which a relevant GTRS or BOJ-NET JGB Services does
    not operate.

In other words, HKD CHATS settles on Mondays-Fridays excluding statutory
general holidays. The statutory list is published annually by the HKSAR
Government in the General Holidays Ordinance (Cap. 149) and re-published
in human-readable form at:

    https://www.gov.hk/en/about/abouthk/holiday/<YYYY>.htm

This page is the primary source for HKD settlement holidays — it carries
the same legal authority as the Ordinance itself (and, unlike the
Ordinance schedule, expresses each entry with a concrete date for the
relevant year, including substitution where a holiday falls on a Sunday).

See docs/data-sources.md#hkd--chats for source documentation.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from scripts.sources._provenance import now_iso_utc, write_calendar_json, write_raw

_BASE = "https://www.gov.hk/en/about/abouthk/holiday/"
_INDEX_URL = _BASE + "index.htm"
_INDEX_DOC_TITLE = "GovHK: General holidays (annual index)"
_FETCHER = "scripts/sources/hkgov_general_holidays.py@v1"
_USER_AGENT = "fx-holiday-calculator/0.1"

_MONTHS = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}

_ROW_RE = re.compile(
    r"<tr[^>]*>\s*"
    r'<td class="desc"[^>]*>(?P<desc>.*?)</td>\s*'
    r'<td class="date"[^>]*>(?P<date>.*?)</td>\s*'
    r'<td class="weekday"[^>]*>(?P<weekday>.*?)</td>\s*'
    r"</tr>",
    re.DOTALL | re.IGNORECASE,
)

_ENTITIES = {
    "&nbsp;": " ",
    "&rsquo;": "’",
    "&lsquo;": "‘",
    "&ldquo;": "“",
    "&rdquo;": "”",
    "&amp;": "&",
}


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    for ent, ch in _ENTITIES.items():
        s = s.replace(ent, ch)
    return s.strip()


def _parse_day_month(s: str, year: int) -> date | None:
    parts = s.strip().split()
    if len(parts) < 2:
        return None
    try:
        day = int(parts[0])
    except ValueError:
        return None
    month = _MONTHS.get(parts[1])
    if month is None:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _year_source(year: int, fetched_at: str) -> dict:
    return {
        "url": f"{_BASE}{year}.htm",
        "doc_title": f"GovHK: General holidays for {year}",
        "fetched_at": fetched_at,
        "fetcher": _FETCHER,
    }


def parse_document(raw: bytes, year: int, fetched_at: str | None = None) -> list[dict]:
    """Parse one year's gov.hk general-holidays page into v3 holiday dicts.

    Every entry carries a per-entry ``source`` override pointing to the
    specific year page (so multi-year payloads preserve which page each
    date came from). ``fetched_at`` defaults to the current UTC time
    stamp; it is injectable so tests can pin it.
    """
    html = raw.decode("utf-8", errors="replace")
    stamp = fetched_at or now_iso_utc()
    src = _year_source(year, stamp)
    out: list[dict] = []
    seen: set[str] = set()
    for m in _ROW_RE.finditer(html):
        date_text = _strip_html(m.group("date"))
        if not date_text:
            # The perennial "Every Sunday" row has a blank date cell.
            continue
        d = _parse_day_month(date_text, year)
        if d is None:
            continue
        iso = d.isoformat()
        if iso in seen:
            continue
        seen.add(iso)
        name = _strip_html(m.group("desc"))
        out.append({"date": iso, "name": name, "source": src, "note": None})
    out.sort(key=lambda h: h["date"])
    return out


def build_payload(year_range: tuple[int, int], pages: dict[int, bytes]) -> dict:
    """Combine one-or-more year pages into a v3 HKD CHATS payload.

    Years not in ``pages`` are dropped silently — gov.hk publishes one
    page per year and only the years it has officially gazetted exist.
    ``valid_from`` / ``valid_until`` are clamped to the years actually
    parsed, so downstream RtgsCalendar raises CalendarRangeError beyond.
    """
    stamp = now_iso_utc()
    holidays: list[dict] = []
    covered: list[int] = []
    for year in sorted(pages):
        if not (year_range[0] <= year <= year_range[1]):
            continue
        holidays.extend(parse_document(pages[year], year, fetched_at=stamp))
        covered.append(year)
    if covered:
        vf = f"{covered[0]}-01-01"
        vu = f"{covered[-1]}-12-31"
    else:
        vf = f"{year_range[0]}-01-01"
        vu = f"{year_range[1]}-12-31"
    return {
        "schema_version": 3,
        "currency": "HKD",
        "calendar_kind": "RTGS",
        "calendar_name": "HKD CHATS",
        "operator": "HKICL (operator) / HKMA (settlement institution)",
        "valid_from": vf,
        "valid_until": vu,
        "default_source": {
            "url": _INDEX_URL,
            "doc_title": _INDEX_DOC_TITLE,
            "fetched_at": stamp,
            "fetcher": _FETCHER,
        },
        "holidays": holidays,
    }


def _fetch_year_page(year: int, timeout: float = 30.0) -> bytes | None:
    """Return raw bytes for a year page, or ``None`` if the page is 404."""
    url = f"{_BASE}{year}.htm"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def fetch_pages(year_range: tuple[int, int], raw_dir: Path | None = None) -> dict[int, bytes]:
    """Fetch all available year pages in ``year_range``. Persist raw bytes
    if ``raw_dir`` is given. Returns a dict ``{year: raw_bytes}``."""
    pages: dict[int, bytes] = {}
    for year in range(year_range[0], year_range[1] + 1):
        raw = _fetch_year_page(year)
        if raw is None:
            continue
        pages[year] = raw
        if raw_dir is not None:
            write_raw(raw_dir, f"HKD-{year}.html", raw)
    return pages


def fetch(year_range: tuple[int, int], data_root: Path) -> Path:
    raw_dir = data_root / "fx_rtgs" / "_raw"
    pages = fetch_pages(year_range, raw_dir)
    if not pages:
        raise RuntimeError(
            "gov.hk has not published any general-holidays page in range "
            f"{year_range[0]}..{year_range[1]}"
        )
    payload = build_payload(year_range, pages)
    out = data_root / "fx_rtgs" / "HKD.json"
    write_calendar_json(out, payload)
    return out


if __name__ == "__main__":
    import sys

    fetch((2026, 2030), Path(__file__).parents[2] / "data")
    sys.exit(0)
