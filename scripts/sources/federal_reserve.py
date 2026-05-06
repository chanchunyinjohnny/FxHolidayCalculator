"""USD Fedwire holiday calendar — see docs/data-sources.md#usd--fedwire."""
from __future__ import annotations

from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path
import urllib.request

from scripts.sources._provenance import now_iso_utc, write_calendar_json, write_raw

_URL = "https://www.federalreserve.gov/aboutthefed/k8.htm"
_DOC_TITLE = "Federal Reserve Bank Holiday Schedule (K.8)"
_FETCHER = "scripts/sources/federal_reserve.py@v1"

_MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}


class _TableExtractor(HTMLParser):
    """Walk the K.8 holiday table; collect (years header row, holiday rows)."""

    def __init__(self) -> None:
        super().__init__()
        self.in_target_table = False
        self.years: list[int] = []
        self.rows: list[tuple[str, list[str]]] = []  # [(name, [dates])]
        self._cur_row: list[str] | None = None
        self._cur_name: str | None = None
        self._cur_text: list[str] = []
        self._in_th_col = False
        self._in_th_row = False
        self._in_td = False

    def handle_starttag(self, tag, attrs):
        ad = dict(attrs)
        if tag == "table" and "table--noBorder" in (ad.get("class") or ""):
            self.in_target_table = True
        if not self.in_target_table:
            return
        if tag == "tr":
            self._cur_row = []
            self._cur_name = None
        elif tag == "th":
            scope = ad.get("scope")
            if scope == "col":
                self._in_th_col = True
                self._cur_text = []
            elif scope == "row":
                self._in_th_row = True
                self._cur_text = []
        elif tag == "td":
            self._in_td = True
            self._cur_text = []

    def handle_data(self, data):
        if self._in_th_col or self._in_th_row or self._in_td:
            self._cur_text.append(data)

    def handle_endtag(self, tag):
        if not self.in_target_table:
            return
        text = "".join(self._cur_text).strip()
        if tag == "th" and self._in_th_col:
            self._in_th_col = False
            try:
                self.years.append(int(text))
            except ValueError:
                pass
        elif tag == "th" and self._in_th_row:
            self._in_th_row = False
            self._cur_name = text
        elif tag == "td":
            self._in_td = False
            if self._cur_row is not None:
                self._cur_row.append(text)
        elif tag == "tr":
            if self._cur_name and self._cur_row:
                self.rows.append((self._cur_name, self._cur_row))
            self._cur_row = None
        elif tag == "table":
            self.in_target_table = False


def _parse_cell(text: str, year: int) -> tuple[date, int]:
    """Returns (parsed_date, asterisk_count).

    Saturday marker: single '*'
    Sunday marker: double '**'
    """
    raw = text.strip()
    # Count trailing asterisks
    star_count = 0
    while raw.endswith("*"):
        star_count += 1
        raw = raw[:-1]
    raw = raw.strip()
    # "January 1" -> split into month, day
    parts = raw.split()
    if len(parts) != 2:
        raise ValueError(f"Cannot parse cell: {text!r}")
    month = _MONTHS[parts[0]]
    day = int(parts[1])
    return date(year, month, day), star_count


def parse_document(raw: bytes, year_range: tuple[int, int]) -> list[dict]:
    """Pure function: bytes -> list of {date, name, source, note} dicts.

    Applies the Saturday/Sunday rule strictly:
    - Plain date (no marker) -> include as-is.
    - Date with '*' (Saturday) -> EXCLUDE entirely. Fedwire is open that Friday.
    - Date with '**' (Sunday) -> CONVERT to following Monday, include with note.
    """
    parser = _TableExtractor()
    parser.feed(raw.decode("utf-8", errors="replace"))
    if not parser.years:
        raise RuntimeError("Could not find year header in Fed K.8 table")
    out: list[dict] = []
    for name, cells in parser.rows:
        for col_idx, cell in enumerate(cells):
            if col_idx >= len(parser.years):
                break
            year = parser.years[col_idx]
            if not (year_range[0] <= year <= year_range[1]):
                continue
            try:
                d, stars = _parse_cell(cell, year)
            except (ValueError, KeyError):
                continue
            if stars == 0:
                out.append({
                    "date": d.isoformat(),
                    "name": name,
                    "source": None,
                    "note": None,
                })
            elif stars == 1:
                # Saturday — Fedwire OPEN on preceding Friday; neither date is a closure. EXCLUDE.
                continue
            else:
                # Sunday — observed Monday is the Fedwire closure
                observed = d + timedelta(days=1)
                out.append({
                    "date": observed.isoformat(),
                    "name": name,
                    "source": None,
                    "note": "Following Monday observed; original holiday fell on Sunday",
                })
    out.sort(key=lambda h: h["date"])
    return out


def build_payload(year_range: tuple[int, int], raw: bytes) -> dict:
    """Wraps parse_document with calendar metadata + default_source."""
    return {
        "schema_version": 1,
        "currency": "USD",
        "calendar_kind": "RTGS",
        "calendar_name": "Fedwire",
        "operator": "Federal Reserve System",
        "default_source": {
            "url": _URL,
            "doc_title": _DOC_TITLE,
            "fetched_at": now_iso_utc(),
            "fetcher": _FETCHER,
        },
        "holidays": parse_document(raw, year_range),
    }


def fetch(year_range: tuple[int, int], data_root: Path) -> Path:
    """HTTP GET the live URL, persist raw HTML to _raw/USD.html, write JSON."""
    req = urllib.request.Request(
        _URL,
        headers={"User-Agent": "fx-holiday-calculator/0.1"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    payload = build_payload(year_range, raw)
    out = data_root / "fx_rtgs" / "USD.json"
    write_calendar_json(out, payload)
    raw_dir = data_root / "fx_rtgs" / "_raw"
    write_raw(raw_dir, "USD.html", raw)
    return out


if __name__ == "__main__":
    import sys
    fetch((2026, 2030), Path(__file__).parents[2] / "data")
    sys.exit(0)
