"""CAD Lynx holidays — Payments Canada system-closure schedule.

See docs/data-sources.md#cad--lynx."""

from __future__ import annotations

import html
import re
from pathlib import Path

import requests

from scripts.sources._provenance import now_iso_utc, write_calendar_json, write_raw

_URL = "https://www.payments.ca/system-closure-schedule"
_DOC_TITLE = "Payments Canada — System closure schedule (Lynx)"
_FETCHER = "scripts/sources/payments_canada_lynx.py@v1"

_MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}
_MONTH_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2})"
)
_YEAR_BLOCK_RE = re.compile(
    r'<h2[^>]*class="[^"]*payments-h2--accent[^"]*"[^>]*>\s*(\d{4})\s*</h2>'
    r"(?P<body>.*?)(?=<h2|</div>)",
    re.DOTALL,
)
_TABLE_RE = re.compile(r"<table[^>]*>(?P<inner>.*?)</table>", re.DOTALL)
_ROW_RE = re.compile(r"<tr[^>]*>(?P<inner>.*?)</tr>", re.DOTALL)
_CELL_RE = re.compile(r"<td[^>]*>(?P<inner>.*?)</td>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(cell: str) -> str:
    return html.unescape(_TAG_RE.sub("", cell)).strip()


def _parse_month_day(text: str, year: int) -> str | None:
    m = _MONTH_RE.search(text)
    if not m:
        return None
    month = _MONTHS[m.group(1)]
    day = int(m.group(2))
    return f"{year:04d}-{month:02d}-{day:02d}"


def parse_document(raw: bytes, year_range: tuple[int, int]) -> list[dict]:
    """Pure: bytes (system-closure HTML) -> list of holiday dicts."""
    text = raw.decode("utf-8", errors="replace")
    out: list[dict] = []
    for ym in _YEAR_BLOCK_RE.finditer(text):
        year = int(ym.group(1))
        if not (year_range[0] <= year <= year_range[1]):
            continue
        tm = _TABLE_RE.search(ym.group("body"))
        if not tm:
            continue
        for rm in _ROW_RE.finditer(tm.group("inner")):
            cells = [_clean(c.group("inner")) for c in _CELL_RE.finditer(rm.group("inner"))]
            if len(cells) < 3:
                continue  # header row (uses <th>) or malformed
            name, federal_text, closure_text = cells[0], cells[1], cells[2]
            closure_iso = _parse_month_day(closure_text, year)
            if not closure_iso:
                continue
            federal_iso = _parse_month_day(federal_text, year)
            note = None
            if federal_iso and federal_iso != closure_iso:
                note = f"Substitute day — federal holiday {federal_text.strip()} fell on a weekend"
            out.append(
                {
                    "date": closure_iso,
                    "name": name,
                    "source": None,
                    "note": note,
                }
            )
    # Dedupe + sort (in case the page ever lists overlapping ranges).
    seen: dict[str, dict] = {}
    for h in out:
        seen.setdefault(h["date"], h)
    return sorted(seen.values(), key=lambda h: h["date"])


def _published_year_span(raw: bytes, year_range: tuple[int, int]) -> tuple[int, int] | None:
    """Return (min, max) of years actually published in the page within range."""
    text = raw.decode("utf-8", errors="replace")
    years = sorted(
        {
            int(m.group(1))
            for m in _YEAR_BLOCK_RE.finditer(text)
            if year_range[0] <= int(m.group(1)) <= year_range[1]
        }
    )
    return (years[0], years[-1]) if years else None


def build_payload(year_range: tuple[int, int], raw: bytes) -> dict:
    """Wraps parse_document with calendar metadata.

    valid_from/valid_until are clamped to the years actually present on the
    page so callers can't ask about a year Payments Canada has not yet
    published (the loader raises CalendarRangeError on out-of-window dates).
    """
    holidays = parse_document(raw, year_range)
    span = _published_year_span(raw, year_range)
    if span is None:
        valid_from = f"{year_range[0]}-01-01"
        valid_until = f"{year_range[1]}-12-31"
    else:
        valid_from = f"{span[0]}-01-01"
        valid_until = f"{span[1]}-12-31"
    return {
        "schema_version": 3,
        "currency": "CAD",
        "calendar_kind": "RTGS",
        "calendar_name": "Lynx",
        "operator": "Payments Canada",
        "valid_from": valid_from,
        "valid_until": valid_until,
        "default_source": {
            "url": _URL,
            "doc_title": _DOC_TITLE,
            "fetched_at": now_iso_utc(),
            "fetcher": _FETCHER,
        },
        "holidays": holidays,
    }


def fetch(year_range: tuple[int, int], data_root: Path) -> Path:
    """HTTP GET the system-closure schedule; persist raw + JSON.

    Payments Canada's CDN rejects non-browser User-Agents with a 403, so we
    advertise as a recent desktop browser. The fx-holiday-calculator/0.1
    UA used by the other fetchers does not work against this host.
    """
    resp = requests.get(
        _URL,
        timeout=30,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    resp.raise_for_status()
    raw = resp.content
    payload = build_payload(year_range, raw)
    out = data_root / "fx_rtgs" / "CAD.json"
    write_calendar_json(out, payload)
    raw_dir = data_root / "fx_rtgs" / "_raw"
    write_raw(raw_dir, "CAD.html", raw)
    return out


if __name__ == "__main__":
    import sys

    fetch((2026, 2030), Path(__file__).parents[2] / "data")
    sys.exit(0)
