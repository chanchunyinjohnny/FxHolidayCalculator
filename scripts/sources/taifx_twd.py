"""TWD fixing calendar — Taipei Forex Inc. (USD/TWD reference rate).

Upstream: Taipei Forex Inc. publishes the TAIFX1 (USD/TWD reference rate)
market trading calendar. This fetcher parses the published HTML table into
the v3 calendar schema.

See docs/data-sources.md#twd--taipei-forex for source documentation.
"""

from __future__ import annotations

import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from scripts.sources._provenance import now_iso_utc, write_calendar_json, write_raw

_URL = "https://www.tpefx.com.tw/"
_DOC_TITLE = "Taipei Forex Inc. USD/TWD Market Trading Calendar"
_FETCHER = "scripts/sources/taifx_twd.py@v1"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class _RowExtractor(HTMLParser):
    """Walk <tr><td>YYYY-MM-DD</td><td>Name</td></tr> rows from any table."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._cur_row: list[str] | None = None
        self._cur_text: list[str] = []
        self._in_td = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._cur_row = []
        elif tag == "td":
            self._in_td = True
            self._cur_text = []

    def handle_data(self, data):
        if self._in_td:
            self._cur_text.append(data)

    def handle_endtag(self, tag):
        if tag == "td":
            self._in_td = False
            if self._cur_row is not None:
                self._cur_row.append("".join(self._cur_text).strip())
        elif tag == "tr":
            if self._cur_row and len(self._cur_row) >= 2:
                self.rows.append(self._cur_row)
            self._cur_row = None


def parse_document(raw: bytes, year_range: tuple[int, int]) -> list[dict]:
    parser = _RowExtractor()
    parser.feed(raw.decode("utf-8", errors="replace"))
    seen: set[str] = set()
    out: list[dict] = []
    for row in parser.rows:
        d, name = row[0], row[1]
        if not _DATE_RE.match(d):
            continue
        year = int(d[:4])
        if not (year_range[0] <= year <= year_range[1]):
            continue
        if d in seen:
            continue
        seen.add(d)
        out.append({"date": d, "name": name, "source": None, "note": None})
    out.sort(key=lambda h: h["date"])
    return out


def build_payload(year_range: tuple[int, int], raw: bytes) -> dict:
    return {
        "schema_version": 3,
        "currency": "TWD",
        "calendar_kind": "FIXING",
        "calendar_name": "Taipei Forex USD/TWD",
        "operator": "Taipei Forex Inc.",
        "valid_from": f"{year_range[0]}-01-01",
        "valid_until": f"{year_range[1]}-12-31",
        "default_source": {
            "url": _URL,
            "doc_title": _DOC_TITLE,
            "fetched_at": now_iso_utc(),
            "fetcher": _FETCHER,
        },
        "holidays": parse_document(raw, year_range),
    }


def fetch(year_range: tuple[int, int], data_root: Path) -> Path:
    req = urllib.request.Request(
        _URL, headers={"User-Agent": "fx-holiday-calculator/0.1"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    payload = build_payload(year_range, raw)
    out = data_root / "fx_fixing" / "TWD.json"
    write_calendar_json(out, payload)
    raw_dir = data_root / "fx_fixing" / "_raw"
    write_raw(raw_dir, "TWD.html", raw)
    return out


if __name__ == "__main__":
    import sys

    fetch((2026, 2030), Path(__file__).parents[2] / "data")
    sys.exit(0)
