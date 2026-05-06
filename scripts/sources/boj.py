"""JPY BoJ-NET holiday calendar — Bank of Japan English page.

See docs/data-sources.md#jpy--bojnet.

Date authority: BoJ HTML page.
Name enrichment: python-holidays (Japan public holidays) + hardcoded
year-end map (Jan 2, 3, Dec 31 are Bank-only and not in python-holidays).
"""
from __future__ import annotations

from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import holidays as _hol_lib
import requests

from scripts.sources._provenance import now_iso_utc, write_calendar_json, write_raw

_URL = "https://www.boj.or.jp/en/about/outline/holi.htm"
_DOC_TITLE = "Holiday Schedule of the Bank — Bank of Japan"
_FETCHER = "scripts/sources/boj.py@v1"

_MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}

# BoJ-only days not in python-holidays
_BANK_ONLY: dict[tuple[int, int], str] = {
    (1, 2): "New Year Holiday (Bank-only)",
    (1, 3): "New Year Holiday (Bank-only)",
    (12, 31): "Year-end closure (Bank-only)",
}


class _BoJExtractor(HTMLParser):
    """Walk BoJ holiday-schedule HTML.

    Locates each <h3 id="pNN"> year header followed by a <table> with
    rows of (Month, comma-separated days). Yields (year, month, day) triples.
    """
    def __init__(self) -> None:
        super().__init__()
        self.entries: list[tuple[int, int, int]] = []
        self._current_year: int | None = None
        self._in_h3 = False
        self._h3_text: list[str] = []
        self._in_table = False
        self._row_cells: list[str] = []
        self._in_td = False
        self._td_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        ad = dict(attrs)
        if tag == "h3":
            self._in_h3 = True
            self._h3_text = []
        elif tag == "table" and self._current_year is not None:
            self._in_table = True
        elif tag == "tr" and self._in_table:
            self._row_cells = []
        elif tag == "td" and self._in_table:
            self._in_td = True
            self._td_text = []

    def handle_data(self, data):
        if self._in_h3:
            self._h3_text.append(data)
        elif self._in_td:
            self._td_text.append(data)

    def handle_endtag(self, tag):
        if tag == "h3":
            self._in_h3 = False
            text = "".join(self._h3_text).strip()
            try:
                y = int(text)
                if 2000 <= y <= 2100:
                    self._current_year = y
            except ValueError:
                pass
        elif tag == "td" and self._in_td:
            self._in_td = False
            self._row_cells.append("".join(self._td_text).strip())
        elif tag == "tr" and self._in_table and len(self._row_cells) >= 2:
            month_name = self._row_cells[0]
            days_text = self._row_cells[1]
            if month_name in _MONTHS and self._current_year:
                month = _MONTHS[month_name]
                for tok in days_text.split(","):
                    tok = tok.strip().rstrip(",").strip()
                    if not tok or tok == "--":
                        continue
                    try:
                        d = int(tok)
                        self.entries.append((self._current_year, month, d))
                    except ValueError:
                        pass
        elif tag == "table":
            self._in_table = False


def _name_for(d: date) -> str:
    bank = _BANK_ONLY.get((d.month, d.day))
    if bank:
        return bank
    cal = _hol_lib.Japan(years=d.year)
    name = cal.get(d)
    if name:
        return name
    return "BoJ closure (unspecified)"


def parse_document(raw: bytes, year_range: tuple[int, int]) -> list[dict]:
    """Pure: extract dates from BoJ HTML. Names enriched via library + hardcoded year-end map."""
    parser = _BoJExtractor()
    parser.feed(raw.decode("utf-8", errors="replace"))
    out: list[dict] = []
    seen: set[tuple[int, int, int]] = set()
    for y, m, d in parser.entries:
        if not (year_range[0] <= y <= year_range[1]):
            continue
        if (y, m, d) in seen:
            continue
        seen.add((y, m, d))
        try:
            real = date(y, m, d)
        except ValueError:
            continue
        out.append({
            "date": real.isoformat(),
            "name": _name_for(real),
            "source": None,
            "note": None,
        })
    out.sort(key=lambda h: h["date"])
    return out


def build_payload(year_range: tuple[int, int], raw: bytes) -> dict:
    return {
        "schema_version": 1,
        "currency": "JPY",
        "calendar_kind": "RTGS",
        "calendar_name": "BoJ-NET",
        "operator": "Bank of Japan",
        "default_source": {
            "url": _URL,
            "doc_title": _DOC_TITLE,
            "fetched_at": now_iso_utc(),
            "fetcher": _FETCHER,
        },
        "holidays": parse_document(raw, year_range),
    }


def fetch(year_range: tuple[int, int], data_root: Path) -> Path:
    resp = requests.get(_URL, timeout=30,
                        headers={"User-Agent": "fx-holiday-calculator/0.1"})
    resp.raise_for_status()
    raw = resp.content
    payload = build_payload(year_range, raw)
    out = data_root / "fx_rtgs" / "JPY.json"
    write_calendar_json(out, payload)
    raw_dir = data_root / "fx_rtgs" / "_raw"
    write_raw(raw_dir, "JPY.html", raw)
    return out


if __name__ == "__main__":
    import sys
    fetch((2026, 2027), Path(__file__).parents[2] / "data")
    sys.exit(0)
