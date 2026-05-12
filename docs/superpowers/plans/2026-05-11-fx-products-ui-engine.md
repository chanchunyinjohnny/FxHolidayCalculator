# FX Products — UI Restructure & Engine Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Amendment 2026-05-12:** Task 5.1 of this plan renamed `tab_swap.py` to `product_spot_swap.py` and registered it as a single "Spot / Swap" sub-tab. That tab has since been split into separate **Spot** and **Swap** sub-tabs; `product_spot_swap.py` was renamed to `product_swap.py` and a new `product_spot.py` was added. References to `product_spot_swap.py` and the combined "Spot / Swap" sub-tab below are historical — current state lives in `docs/superpowers/plans/2026-05-12-split-spot-and-swap-tabs.md`.

**Goal:** Extend the FX Holiday Calculator from a single "Swap Date Calculator" tab into a product-aware tool: Spot/Swap (existing), NDF (new — CNY/KRW/TWD fixing calendars), FX Option (new — OTC + Listed), FX Futures (new — CME/HKEX/SGX). Adds three new primary-source fixing calendars and four engine modules.

**Architecture:** Per-product engine modules (`ndf.py`, `option.py`, `future.py`) sitting alongside the existing `swap.py`, all composing shared helpers from `conventions/`. New `calendars/fixing.py` mirrors the RTGS calendar pattern. UI restructures into nested tabs: `Calculator | Holidays | About`, with the Calculator parent hosting four product sub-tabs.

**Tech Stack:** Python 3.10/3.11, Streamlit 1.30 (pinned), `python-holidays` (pinned), `requests` / `urllib`, `pdfplumber`. No ruff (project uses flake8/black/isort). All tests offline & fixture-based.

**Conventions reference:** `docs/superpowers/specs/2026-05-11-fx-products-ui-engine-design.md`

**Commit policy:** Per `CLAUDE.md` the user owns all commits. Commit steps in this plan are commands the **user** runs after reviewing the diff — the agent does not run `git commit`.

---

## Phase 0 — Pair table additions

### Task 0.1: Extend `Pair` dataclass with `ndf` and `fixing_currency` fields

**Files:**
- Modify: `fx_holiday_calculator/pairs.py`
- Test: `tests/test_pairs.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pairs.py`:

```python
def test_pair_dataclass_has_ndf_field_default_false():
    p = parse_pair("EUR/USD")
    assert p.ndf is False
    assert p.fixing_currency is None


def test_pair_dataclass_supports_ndf_fields():
    from fx_holiday_calculator.pairs import Pair
    p = Pair(
        base="USD",
        quote="CNY",
        spot_offset_days=2,
        listed_on=(),
        ndf=True,
        fixing_currency="CNY",
    )
    assert p.ndf is True
    assert p.fixing_currency == "CNY"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_pairs.py::test_pair_dataclass_has_ndf_field_default_false tests/test_pairs.py::test_pair_dataclass_supports_ndf_fields -v
```

Expected: `AttributeError: 'Pair' object has no attribute 'ndf'` (or the constructor rejects the kwargs).

- [ ] **Step 3: Extend `Pair` and `_add()` in `pairs.py`**

Replace the `Pair` dataclass and `_add()` helper at the top of `fx_holiday_calculator/pairs.py`:

```python
@dataclass(frozen=True)
class Pair:
    base: str
    quote: str
    spot_offset_days: int
    listed_on: tuple[str, ...]
    ndf: bool = False
    fixing_currency: str | None = None


_PAIRS: dict[tuple[str, str], Pair] = {}


def _add(
    base: str,
    quote: str,
    *,
    t: int = 2,
    listed_on: tuple[str, ...] = (),
    ndf: bool = False,
    fixing_currency: str | None = None,
) -> None:
    _PAIRS[(base, quote)] = Pair(
        base=base,
        quote=quote,
        spot_offset_days=t,
        listed_on=listed_on,
        ndf=ndf,
        fixing_currency=fixing_currency,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_pairs.py -v
```

Expected: all green, including pre-existing tests.

- [ ] **Step 5: Commit (user action)**

User runs:

```bash
git add fx_holiday_calculator/pairs.py tests/test_pairs.py
git commit -m "feat(pairs): add ndf and fixing_currency fields to Pair"
```

---

### Task 0.2: Add USD/CNY, USD/KRW, USD/TWD NDF pair entries

**Files:**
- Modify: `fx_holiday_calculator/pairs.py`
- Test: `tests/test_pairs.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pairs.py`:

```python
def test_usd_cny_is_ndf_pair():
    p = parse_pair("USD/CNY")
    assert p.ndf is True
    assert p.fixing_currency == "CNY"
    assert p.spot_offset_days == 2
    assert p.listed_on == ()


def test_usd_krw_is_ndf_pair():
    p = parse_pair("USD/KRW")
    assert p.ndf is True
    assert p.fixing_currency == "KRW"


def test_usd_twd_is_ndf_pair():
    p = parse_pair("USD/TWD")
    assert p.ndf is True
    assert p.fixing_currency == "TWD"


def test_krw_usd_remains_deliverable_sgx_listed():
    # Distinct from USD/KRW (the NDF) — KRW/USD is the SGX-listed deliverable contract.
    p = parse_pair("KRW/USD")
    assert p.ndf is False
    assert "SGX" in p.listed_on
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_pairs.py -k "ndf or krw_usd_remains" -v
```

Expected: `PairNotFoundError: Unsupported pair: USD/CNY` etc.

- [ ] **Step 3: Add the NDF pair entries**

Append in `fx_holiday_calculator/pairs.py` after the existing pair list, before `parse_pair`:

```python
# NDF pairs (East-Asia). Non-deliverable; USD-settled; fixing on local primary source.
_add("USD", "CNY", t=2, listed_on=(), ndf=True, fixing_currency="CNY")
_add("USD", "KRW", t=2, listed_on=(), ndf=True, fixing_currency="KRW")
_add("USD", "TWD", t=2, listed_on=(), ndf=True, fixing_currency="TWD")
```

- [ ] **Step 4: Run all pair tests**

```bash
pytest tests/test_pairs.py -v
```

Expected: all green. The pre-existing `KRW/USD` entry is untouched and still SGX-listed.

- [ ] **Step 5: Commit (user action)**

```bash
git add fx_holiday_calculator/pairs.py tests/test_pairs.py
git commit -m "feat(pairs): add USD/CNY, USD/KRW, USD/TWD NDF pairs"
```

---

## Phase 1 — Fixing calendar data layer

### Task 1.1: `FixingCalendar` dataclass

**Files:**
- Create: `fx_holiday_calculator/calendars/fixing.py`
- Create: `tests/test_calendars_fixing.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_calendars_fixing.py`:

```python
from datetime import date, datetime, timezone

import pytest

from fx_holiday_calculator.calendars.fixing import FixingCalendar
from fx_holiday_calculator.calendars.types import (
    CalendarRangeError,
    HolidayEntry,
    SourceRef,
)


def _src() -> SourceRef:
    return SourceRef(
        url="https://x",
        doc_title="x",
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        fetcher="t",
    )


def _entry(d: date, name: str = "Holiday") -> HolidayEntry:
    return HolidayEntry(
        date=d,
        name=name,
        note=None,
        source=_src(),
        source_origin="bundled",
        is_closure=True,
    )


def test_fixing_calendar_is_holiday_true_when_present():
    cal = FixingCalendar(
        currency="CNY",
        calendar_name="CFETS",
        operator="PBoC",
        entries_by_date={date(2026, 10, 1): _entry(date(2026, 10, 1), "National Day")},
        valid_from=date(2026, 1, 1),
        valid_until=date(2026, 12, 31),
    )
    assert cal.is_holiday(date(2026, 10, 1)) is True
    assert cal.is_holiday(date(2026, 10, 2)) is False


def test_fixing_calendar_get_holiday_returns_entry():
    e = _entry(date(2026, 10, 1), "National Day")
    cal = FixingCalendar(
        currency="CNY",
        calendar_name="CFETS",
        operator="PBoC",
        entries_by_date={date(2026, 10, 1): e},
        valid_from=date(2026, 1, 1),
        valid_until=date(2026, 12, 31),
    )
    assert cal.get_holiday(date(2026, 10, 1)) is e
    assert cal.get_holiday(date(2026, 10, 2)) is None


def test_fixing_calendar_raises_on_out_of_range_query():
    cal = FixingCalendar(
        currency="CNY",
        calendar_name="CFETS",
        operator="PBoC",
        entries_by_date={},
        valid_from=date(2026, 1, 1),
        valid_until=date(2026, 12, 31),
    )
    with pytest.raises(CalendarRangeError):
        cal.is_holiday(date(2025, 12, 31))
    with pytest.raises(CalendarRangeError):
        cal.is_holiday(date(2027, 1, 1))


def test_fixing_calendar_label_includes_currency_and_name():
    cal = FixingCalendar(
        currency="CNY",
        calendar_name="CFETS USD/CNY Central Parity",
        operator="PBoC",
        entries_by_date={},
        valid_from=date(2026, 1, 1),
        valid_until=date(2026, 12, 31),
    )
    try:
        cal.is_holiday(date(2025, 1, 1))
    except CalendarRangeError as exc:
        assert "CNY" in exc.calendar_label
        assert "CFETS" in exc.calendar_label
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_calendars_fixing.py -v
```

Expected: `ModuleNotFoundError: No module named 'fx_holiday_calculator.calendars.fixing'`.

- [ ] **Step 3: Create `fx_holiday_calculator/calendars/fixing.py`**

```python
from dataclasses import dataclass
from datetime import date

from fx_holiday_calculator.calendars.types import CalendarRangeError, HolidayEntry


@dataclass
class FixingCalendar:
    """Calendar of non-business days for an FX fixing source.

    Used by NDF date math: the fixing date must be a good day on the
    non-deliverable currency's fixing-source calendar (e.g. CFETS for CNY,
    KFTC for KRW, Taipei Forex for TWD).
    """

    currency: str
    calendar_name: str
    operator: str
    entries_by_date: dict[date, HolidayEntry]
    valid_from: date
    valid_until: date

    def _label(self) -> str:
        return f"{self.currency} ({self.calendar_name})"

    def _check_range(self, d: date) -> None:
        if d < self.valid_from or d > self.valid_until:
            raise CalendarRangeError(self._label(), d, self.valid_from, self.valid_until)

    def is_holiday(self, d: date) -> bool:
        self._check_range(d)
        e = self.entries_by_date.get(d)
        return e is not None and e.is_closure

    def get_holiday(self, d: date) -> HolidayEntry | None:
        self._check_range(d)
        return self.entries_by_date.get(d)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_calendars_fixing.py -v
```

Expected: all four tests green.

- [ ] **Step 5: Commit (user action)**

```bash
git add fx_holiday_calculator/calendars/fixing.py tests/test_calendars_fixing.py
git commit -m "feat(calendars): add FixingCalendar dataclass for NDF fixing days"
```

---

### Task 1.2: `load_fixing_calendar` in `loader.py`

**Files:**
- Modify: `fx_holiday_calculator/calendars/loader.py`
- Test: `tests/test_calendar_loader.py` (existing — extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_calendar_loader.py`:

```python
import json
from datetime import date
from pathlib import Path

import pytest

from fx_holiday_calculator.calendars.fixing import FixingCalendar
from fx_holiday_calculator.calendars.loader import load_fixing_calendar


def _write_fixing_blob(tmp_path: Path, currency: str, holidays: list[dict]) -> Path:
    blob = {
        "schema_version": 3,
        "currency": currency,
        "calendar_kind": "FIXING",
        "calendar_name": f"{currency} fixing",
        "operator": "test",
        "valid_from": "2026-01-01",
        "valid_until": "2030-12-31",
        "default_source": {
            "url": "https://x",
            "doc_title": "x",
            "fetched_at": "2026-01-01T00:00:00Z",
            "fetcher": "test",
        },
        "holidays": holidays,
    }
    out = tmp_path / f"{currency}.json"
    out.write_text(json.dumps(blob))
    return out


def test_load_fixing_calendar_basic(tmp_path):
    _write_fixing_blob(
        tmp_path,
        "CNY",
        [{"date": "2026-10-01", "name": "National Day", "source": None, "note": None}],
    )
    cal = load_fixing_calendar("CNY", root=tmp_path)
    assert isinstance(cal, FixingCalendar)
    assert cal.currency == "CNY"
    assert cal.is_holiday(date(2026, 10, 1)) is True
    entry = cal.get_holiday(date(2026, 10, 1))
    assert entry is not None
    assert entry.source.url == "https://x"
    assert entry.source_origin == "bundled"


def test_load_fixing_calendar_rejects_wrong_kind(tmp_path):
    blob = {
        "schema_version": 3,
        "currency": "CNY",
        "calendar_kind": "RTGS",  # wrong kind
        "calendar_name": "x",
        "operator": "x",
        "valid_from": "2026-01-01",
        "valid_until": "2030-12-31",
        "default_source": {
            "url": "https://x",
            "doc_title": "x",
            "fetched_at": "2026-01-01T00:00:00Z",
            "fetcher": "t",
        },
        "holidays": [],
    }
    (tmp_path / "CNY.json").write_text(json.dumps(blob))
    with pytest.raises(ValueError, match="not a FIXING calendar"):
        load_fixing_calendar("CNY", root=tmp_path)


def test_load_fixing_calendar_cache_overlays_bundled(tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    cache = tmp_path / "cache"
    cache.mkdir()
    _write_fixing_blob(
        bundled,
        "CNY",
        [{"date": "2026-10-01", "name": "National Day", "source": None, "note": None}],
    )
    _write_fixing_blob(
        cache,
        "CNY",
        [{"date": "2026-10-02", "name": "Extra closure", "source": None, "note": None}],
    )
    cal = load_fixing_calendar("CNY", root=bundled, cache_root=cache)
    # Cache wins
    assert cal.is_holiday(date(2026, 10, 2)) is True
    assert cal.is_holiday(date(2026, 10, 1)) is False
    entry = cal.get_holiday(date(2026, 10, 2))
    assert entry.source_origin == "cache"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_calendar_loader.py -k fixing -v
```

Expected: `ImportError: cannot import name 'load_fixing_calendar'`.

- [ ] **Step 3: Add `load_fixing_calendar` to `loader.py`**

Add an import at the top of `fx_holiday_calculator/calendars/loader.py`:

```python
from fx_holiday_calculator.calendars.fixing import FixingCalendar
```

Append at the bottom of the file:

```python
def load_fixing_calendar(
    currency: str, root: Path, cache_root: Path | None = None
) -> FixingCalendar:
    blob, origin = _load_calendar_blob(currency, root, cache_root)
    if blob.get("calendar_kind") != "FIXING":
        raise ValueError(f"{currency}.json is not a FIXING calendar")
    if blob.get("currency") != currency:
        raise ValueError(f"{currency}.json currency mismatch")
    vf, vu = _parse_window(blob, f"{currency}.json")
    return FixingCalendar(
        currency=blob["currency"],
        calendar_name=blob["calendar_name"],
        operator=blob["operator"],
        entries_by_date=_build_entries(blob, origin),
        valid_from=vf,
        valid_until=vu,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_calendar_loader.py -v
```

Expected: all green, including pre-existing tests.

- [ ] **Step 5: Commit (user action)**

```bash
git add fx_holiday_calculator/calendars/loader.py tests/test_calendar_loader.py
git commit -m "feat(loader): add load_fixing_calendar for FIXING-kind JSON"
```

---

### Task 1.3: CFETS (USD/CNY) fetcher — `cfets_cny.py`

**Files:**
- Create: `scripts/sources/cfets_cny.py`
- Create: `tests/test_fetcher_cfets_cny.py`
- Create: `tests/fixtures/sources/cfets_cny/sample.html`

**Background:** The CFETS trading calendar is published on `www.chinamoney.com.cn` (English mirror of CFETS) as an HTML page listing CFETS market closures. We model the fetcher on `scripts/sources/federal_reserve.py` (HTML parse, fixture-driven test).

- [ ] **Step 1: Create a minimal HTML fixture**

Create `tests/fixtures/sources/cfets_cny/sample.html`:

```html
<!DOCTYPE html><html><body>
<table class="calendar">
  <thead><tr><th>Date</th><th>Holiday</th></tr></thead>
  <tbody>
    <tr><td>2026-01-01</td><td>New Year's Day</td></tr>
    <tr><td>2026-02-17</td><td>Spring Festival</td></tr>
    <tr><td>2026-02-18</td><td>Spring Festival</td></tr>
    <tr><td>2026-02-19</td><td>Spring Festival</td></tr>
    <tr><td>2026-04-06</td><td>Qingming Festival</td></tr>
    <tr><td>2026-05-01</td><td>Labour Day</td></tr>
    <tr><td>2026-06-19</td><td>Dragon Boat Festival</td></tr>
    <tr><td>2026-09-25</td><td>Mid-Autumn Festival</td></tr>
    <tr><td>2026-10-01</td><td>National Day</td></tr>
    <tr><td>2026-10-02</td><td>National Day</td></tr>
    <tr><td>2026-10-03</td><td>National Day</td></tr>
    <tr><td>2026-10-04</td><td>National Day</td></tr>
    <tr><td>2026-10-05</td><td>National Day</td></tr>
    <tr><td>2026-10-06</td><td>National Day</td></tr>
    <tr><td>2026-10-07</td><td>National Day</td></tr>
  </tbody>
</table>
</body></html>
```

> Note: this fixture is a simplified canonical shape, not the verbatim CFETS HTML. The real `parse_document` will need adjustment when the engineer runs the live fetcher against the upstream page. Treat fixture-shape and live-shape as separate concerns; the fixture exists to lock the parser contract.

- [ ] **Step 2: Write the failing test**

Create `tests/test_fetcher_cfets_cny.py`:

```python
from datetime import datetime
from pathlib import Path

from scripts.sources.cfets_cny import build_payload, parse_document

FIXTURE = Path(__file__).parent / "fixtures" / "sources" / "cfets_cny" / "sample.html"


def _by_date(holidays):
    return {h["date"]: h for h in holidays}


def test_payload_metadata():
    raw = FIXTURE.read_bytes()
    payload = build_payload((2026, 2030), raw)
    assert payload["currency"] == "CNY"
    assert payload["calendar_kind"] == "FIXING"
    assert payload["calendar_name"].startswith("CFETS")
    src = payload["default_source"]
    assert src["url"].startswith("https://")
    assert src["doc_title"]
    datetime.fromisoformat(src["fetched_at"].replace("Z", "+00:00"))


def test_national_day_present():
    raw = FIXTURE.read_bytes()
    holidays = parse_document(raw, (2026, 2026))
    by_date = _by_date(holidays)
    assert "2026-10-01" in by_date
    assert by_date["2026-10-01"]["name"] == "National Day"


def test_year_range_filters_out_of_scope():
    raw = FIXTURE.read_bytes()
    holidays = parse_document(raw, (2027, 2027))
    assert holidays == []


def test_holidays_sorted_and_unique():
    raw = FIXTURE.read_bytes()
    holidays = parse_document(raw, (2026, 2026))
    dates = [h["date"] for h in holidays]
    assert dates == sorted(dates)
    assert len(dates) == len(set(dates))


def test_default_source_complete():
    raw = FIXTURE.read_bytes()
    payload = build_payload((2026, 2026), raw)
    src = payload["default_source"]
    assert src["url"]
    assert src["doc_title"]
    assert src["fetched_at"]
    assert src["fetcher"]
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/test_fetcher_cfets_cny.py -v
```

Expected: `ModuleNotFoundError: scripts.sources.cfets_cny`.

- [ ] **Step 4: Implement `scripts/sources/cfets_cny.py`**

```python
"""CNY fixing calendar — CFETS / China Foreign Exchange Trade System (PBoC).

Upstream: CFETS publishes the USD/CNY central parity (中间价) trading calendar
on chinamoney.com.cn. This fetcher parses the published HTML table into the
v3 calendar schema.

See docs/data-sources.md#cny--cfets for source documentation.
"""

from __future__ import annotations

import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from scripts.sources._provenance import now_iso_utc, write_calendar_json, write_raw

_URL = "https://www.chinamoney.com.cn/english/svcrmm/"
_DOC_TITLE = "CFETS Trading Calendar (USD/CNY Central Parity)"
_FETCHER = "scripts/sources/cfets_cny.py@v1"

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
        "currency": "CNY",
        "calendar_kind": "FIXING",
        "calendar_name": "CFETS USD/CNY Central Parity",
        "operator": "China Foreign Exchange Trade System (PBoC)",
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
    out = data_root / "fx_fixing" / "CNY.json"
    write_calendar_json(out, payload)
    raw_dir = data_root / "fx_fixing" / "_raw"
    write_raw(raw_dir, "CNY.html", raw)
    return out


if __name__ == "__main__":
    import sys
    fetch((2026, 2030), Path(__file__).parents[2] / "data")
    sys.exit(0)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_fetcher_cfets_cny.py -v
```

Expected: all five tests green.

- [ ] **Step 6: Commit (user action)**

```bash
git add scripts/sources/cfets_cny.py tests/test_fetcher_cfets_cny.py tests/fixtures/sources/cfets_cny/
git commit -m "feat(sources): add CFETS USD/CNY fixing-calendar fetcher"
```

---

### Task 1.4: KFTC (USD/KRW) fetcher — `kftc_krw.py`

**Files:**
- Create: `scripts/sources/kftc_krw.py`
- Create: `tests/test_fetcher_kftc_krw.py`
- Create: `tests/fixtures/sources/kftc_krw/sample.html`

**Background:** Korea Financial Telecommunications & Clearings Institute (KFTC) publishes the Korean FX market trading calendar (used for the USD/KRW MAR fix). Same parsing pattern as CFETS.

- [ ] **Step 1: Create fixture `tests/fixtures/sources/kftc_krw/sample.html`**

```html
<!DOCTYPE html><html><body>
<table class="calendar">
  <thead><tr><th>Date</th><th>Holiday</th></tr></thead>
  <tbody>
    <tr><td>2026-01-01</td><td>New Year's Day</td></tr>
    <tr><td>2026-02-16</td><td>Seollal</td></tr>
    <tr><td>2026-02-17</td><td>Seollal</td></tr>
    <tr><td>2026-02-18</td><td>Seollal</td></tr>
    <tr><td>2026-03-01</td><td>Independence Movement Day</td></tr>
    <tr><td>2026-05-05</td><td>Children's Day</td></tr>
    <tr><td>2026-05-25</td><td>Buddha's Birthday</td></tr>
    <tr><td>2026-06-06</td><td>Memorial Day</td></tr>
    <tr><td>2026-08-15</td><td>Liberation Day</td></tr>
    <tr><td>2026-09-24</td><td>Chuseok</td></tr>
    <tr><td>2026-09-25</td><td>Chuseok</td></tr>
    <tr><td>2026-10-03</td><td>National Foundation Day</td></tr>
    <tr><td>2026-10-09</td><td>Hangeul Day</td></tr>
    <tr><td>2026-12-25</td><td>Christmas</td></tr>
  </tbody>
</table>
</body></html>
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_fetcher_kftc_krw.py`:

```python
from datetime import datetime
from pathlib import Path

from scripts.sources.kftc_krw import build_payload, parse_document

FIXTURE = Path(__file__).parent / "fixtures" / "sources" / "kftc_krw" / "sample.html"


def test_payload_metadata():
    raw = FIXTURE.read_bytes()
    payload = build_payload((2026, 2030), raw)
    assert payload["currency"] == "KRW"
    assert payload["calendar_kind"] == "FIXING"
    assert payload["calendar_name"].startswith("KFTC")
    src = payload["default_source"]
    datetime.fromisoformat(src["fetched_at"].replace("Z", "+00:00"))


def test_chuseok_two_days_present():
    raw = FIXTURE.read_bytes()
    holidays = parse_document(raw, (2026, 2026))
    by_date = {h["date"]: h for h in holidays}
    assert "2026-09-24" in by_date
    assert "2026-09-25" in by_date
    assert by_date["2026-09-24"]["name"] == "Chuseok"


def test_year_count_2026():
    raw = FIXTURE.read_bytes()
    assert len(parse_document(raw, (2026, 2026))) == 14
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/test_fetcher_kftc_krw.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 4: Implement `scripts/sources/kftc_krw.py`**

The parser is identical to CFETS — same HTML row shape. Reuse the row-extractor pattern. Copy `cfets_cny.py` into `kftc_krw.py` with these substitutions:

```python
_URL = "https://www.kftc.or.kr/en/..."   # KFTC English market-calendar page
_DOC_TITLE = "KFTC Korean FX Market Trading Calendar (USD/KRW MAR)"
_FETCHER = "scripts/sources/kftc_krw.py@v1"
```

And in `build_payload`:

```python
return {
    "schema_version": 3,
    "currency": "KRW",
    "calendar_kind": "FIXING",
    "calendar_name": "KFTC USD/KRW MAR",
    "operator": "Korea Financial Telecommunications & Clearings Institute",
    ...
}
```

And in `fetch()`, change output path to `data_root / "fx_fixing" / "KRW.json"` and raw file name to `"KRW.html"`.

The `parse_document` body is identical to `cfets_cny.parse_document` — same `_RowExtractor`, same year-filter logic. Don't extract into a shared helper yet; YAGNI until a fourth fetcher would justify it.

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_fetcher_kftc_krw.py -v
```

Expected: all three tests green.

- [ ] **Step 6: Commit (user action)**

```bash
git add scripts/sources/kftc_krw.py tests/test_fetcher_kftc_krw.py tests/fixtures/sources/kftc_krw/
git commit -m "feat(sources): add KFTC USD/KRW fixing-calendar fetcher"
```

---

### Task 1.5: Taipei Forex (USD/TWD) fetcher — `taifx_twd.py`

**Files:**
- Create: `scripts/sources/taifx_twd.py`
- Create: `tests/test_fetcher_taifx_twd.py`
- Create: `tests/fixtures/sources/taifx_twd/sample.html`

**Background:** Taipei Forex Inc. publishes the TAIFX1 (USD/TWD reference rate) market calendar. Same parsing pattern.

- [ ] **Step 1: Create fixture `tests/fixtures/sources/taifx_twd/sample.html`**

```html
<!DOCTYPE html><html><body>
<table>
  <thead><tr><th>Date</th><th>Holiday</th></tr></thead>
  <tbody>
    <tr><td>2026-01-01</td><td>Founding Day</td></tr>
    <tr><td>2026-02-16</td><td>Lunar New Year</td></tr>
    <tr><td>2026-02-17</td><td>Lunar New Year</td></tr>
    <tr><td>2026-02-18</td><td>Lunar New Year</td></tr>
    <tr><td>2026-02-19</td><td>Lunar New Year</td></tr>
    <tr><td>2026-02-20</td><td>Lunar New Year</td></tr>
    <tr><td>2026-02-27</td><td>Peace Memorial Day Holiday</td></tr>
    <tr><td>2026-02-28</td><td>Peace Memorial Day</td></tr>
    <tr><td>2026-04-03</td><td>Tomb-Sweeping Day Holiday</td></tr>
    <tr><td>2026-04-06</td><td>Tomb-Sweeping Day</td></tr>
    <tr><td>2026-05-01</td><td>Labour Day</td></tr>
    <tr><td>2026-06-19</td><td>Dragon Boat Festival</td></tr>
    <tr><td>2026-09-25</td><td>Mid-Autumn Festival</td></tr>
    <tr><td>2026-10-09</td><td>Double Tenth Day Holiday</td></tr>
    <tr><td>2026-10-10</td><td>Double Tenth Day</td></tr>
  </tbody>
</table>
</body></html>
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_fetcher_taifx_twd.py`:

```python
from datetime import datetime
from pathlib import Path

from scripts.sources.taifx_twd import build_payload, parse_document

FIXTURE = Path(__file__).parent / "fixtures" / "sources" / "taifx_twd" / "sample.html"


def test_payload_metadata():
    raw = FIXTURE.read_bytes()
    payload = build_payload((2026, 2030), raw)
    assert payload["currency"] == "TWD"
    assert payload["calendar_kind"] == "FIXING"
    assert payload["calendar_name"].startswith("Taipei Forex")
    src = payload["default_source"]
    datetime.fromisoformat(src["fetched_at"].replace("Z", "+00:00"))


def test_double_tenth_day():
    raw = FIXTURE.read_bytes()
    by_date = {h["date"]: h for h in parse_document(raw, (2026, 2026))}
    assert "2026-10-10" in by_date
    assert by_date["2026-10-10"]["name"] == "Double Tenth Day"


def test_year_count_2026():
    raw = FIXTURE.read_bytes()
    assert len(parse_document(raw, (2026, 2026))) == 15
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/test_fetcher_taifx_twd.py -v
```

- [ ] **Step 4: Implement `scripts/sources/taifx_twd.py`**

Same shape as `cfets_cny.py` and `kftc_krw.py`. Substitute:

```python
_URL = "https://www.taifex.com.tw/..."   # Taipei Forex Inc. market-calendar page
_DOC_TITLE = "Taipei Forex Inc. USD/TWD Market Trading Calendar"
_FETCHER = "scripts/sources/taifx_twd.py@v1"
```

And in `build_payload`:

```python
return {
    "schema_version": 3,
    "currency": "TWD",
    "calendar_kind": "FIXING",
    "calendar_name": "Taipei Forex USD/TWD",
    "operator": "Taipei Forex Inc.",
    ...
}
```

`fetch()` writes to `data_root / "fx_fixing" / "TWD.json"` and raw to `TWD.html`.

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_fetcher_taifx_twd.py -v
```

Expected: all three tests green.

- [ ] **Step 6: Commit (user action)**

```bash
git add scripts/sources/taifx_twd.py tests/test_fetcher_taifx_twd.py tests/fixtures/sources/taifx_twd/
git commit -m "feat(sources): add Taipei Forex USD/TWD fixing-calendar fetcher"
```

---

### Task 1.6: Generate bundled fixing calendar JSON files

**Files:**
- Create: `data/fx_fixing/CNY.json`
- Create: `data/fx_fixing/KRW.json`
- Create: `data/fx_fixing/TWD.json`
- Create: `data/fx_fixing/_raw/CNY.html`, `KRW.html`, `TWD.html`

**Note:** This task produces the v1.1 bundled data files. Live upstream URLs may need adjustment from the placeholders in Task 1.3–1.5. The engineer should resolve the actual URLs by visiting the source organisation websites, update `_URL` constants in the three fetchers, then run them.

- [ ] **Step 1: Verify upstream URLs are live**

For each of the three sources, manually open the page in a browser to confirm the URL still serves the trading calendar. Update `_URL` in the fetcher module if the URL has changed. If the fetcher's HTML parser pattern needs adjustment to match the real upstream shape, update `parse_document` accordingly and re-run the fixture test to confirm the shape contract still holds.

- [ ] **Step 2: Run each fetcher in bundled-write mode**

```bash
python -m fx_holiday_calculator.refresh --source CNY --write-bundled --year-from 2026 --year-to 2030
python -m fx_holiday_calculator.refresh --source KRW --write-bundled --year-from 2026 --year-to 2030
python -m fx_holiday_calculator.refresh --source TWD --write-bundled --year-from 2026 --year-to 2030
```

> These commands will fail until Task 1.7 (refresh integration) is done. Skip this step if executing the plan in strict phase order; the bundled files can also be created by directly running each fetcher's `if __name__ == "__main__"` block:
>
> ```bash
> python -m scripts.sources.cfets_cny
> python -m scripts.sources.kftc_krw
> python -m scripts.sources.taifx_twd
> ```

- [ ] **Step 3: Verify the JSON files are well-formed and contract-compliant**

```bash
python -c "import json; json.loads(open('data/fx_fixing/CNY.json').read())"
python -c "import json; json.loads(open('data/fx_fixing/KRW.json').read())"
python -c "import json; json.loads(open('data/fx_fixing/TWD.json').read())"
```

Expected: no output (clean parse).

- [ ] **Step 4: Commit (user action)**

```bash
git add data/fx_fixing/
git commit -m "data(fixing): bundle CFETS, KFTC, Taipei Forex 2026-2030"
```

---

### Task 1.7: Refresh integration

**Files:**
- Modify: `fx_holiday_calculator/refresh.py`
- Test: `tests/test_refresh.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_refresh.py`:

```python
from fx_holiday_calculator.refresh import _SOURCES


def test_refresh_sources_include_fixing_currencies():
    assert "CNY" in _SOURCES
    assert "KRW" in _SOURCES
    assert "TWD" in _SOURCES


def test_refresh_fixing_sources_target_fx_fixing_subdir():
    _, subdir_cny, file_cny = _SOURCES["CNY"]
    assert subdir_cny == "fx_fixing"
    assert file_cny == "CNY.json"
    _, subdir_krw, file_krw = _SOURCES["KRW"]
    assert subdir_krw == "fx_fixing"
    assert file_krw == "KRW.json"
    _, subdir_twd, file_twd = _SOURCES["TWD"]
    assert subdir_twd == "fx_fixing"
    assert file_twd == "TWD.json"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_refresh.py -k fixing -v
```

Expected: `KeyError: 'CNY'`.

- [ ] **Step 3: Add fixing fetchers to `_SOURCES`**

In `fx_holiday_calculator/refresh.py`, extend the `_SOURCES` dict:

```python
_SOURCES: dict[str, tuple[str, str, str]] = {
    "EUR": ("scripts.sources.ecb_target2", "fx_rtgs", "EUR.json"),
    "USD": ("scripts.sources.federal_reserve", "fx_rtgs", "USD.json"),
    "GBP": ("scripts.sources.boe_chaps", "fx_rtgs", "GBP.json"),
    "JPY": ("scripts.sources.boj", "fx_rtgs", "JPY.json"),
    "CNY": ("scripts.sources.cfets_cny", "fx_fixing", "CNY.json"),
    "KRW": ("scripts.sources.kftc_krw", "fx_fixing", "KRW.json"),
    "TWD": ("scripts.sources.taifx_twd", "fx_fixing", "TWD.json"),
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_refresh.py -v
```

Expected: all green.

- [ ] **Step 5: Commit (user action)**

```bash
git add fx_holiday_calculator/refresh.py tests/test_refresh.py
git commit -m "feat(refresh): register CNY/KRW/TWD fixing-calendar fetchers"
```

---

### Task 1.8: Extend data-integrity test to scan `fx_fixing/`

**Files:**
- Modify: `tests/test_data_integrity.py`

- [ ] **Step 1: Modify `_all_calendar_files()`**

In `tests/test_data_integrity.py`, replace `_all_calendar_files()`:

```python
DATA_DIR = Path(__file__).parents[1] / "data"
RTGS_DIR = DATA_DIR / "fx_rtgs"
EXCH_DIR = DATA_DIR / "fx_exchange"
FIXING_DIR = DATA_DIR / "fx_fixing"


def _all_calendar_files() -> list[Path]:
    files: list[Path] = []
    for d in (RTGS_DIR, EXCH_DIR, FIXING_DIR):
        if d.exists():
            files += sorted(p for p in d.glob("*.json") if not p.name.startswith("_"))
    return files
```

- [ ] **Step 2: Run the data-integrity test**

```bash
pytest tests/test_data_integrity.py -v
```

Expected: all parametrised tests pass — the existing RTGS/Exchange files plus the three new fixing files (assuming Task 1.6 has been completed). If fixing files don't exist yet, the parametrise list simply doesn't include them, which is OK.

- [ ] **Step 3: Commit (user action)**

```bash
git add tests/test_data_integrity.py
git commit -m "test(integrity): include fx_fixing/ in calendar-file scan"
```

---

### Task 1.9: Sidebar refresh-source wiring & bundled-fetched timestamp scan

**Files:**
- Modify: `fx_holiday_calculator/ui/sidebar.py`

- [ ] **Step 1: Update bundled-fetched-timestamp scan**

In `fx_holiday_calculator/ui/sidebar.py`, modify `_bundled_fetched_at()` to also scan `fx_fixing`:

```python
def _bundled_fetched_at() -> str:
    earliest = None
    for sub in ("fx_rtgs", "fx_exchange", "fx_fixing"):
        d = BUNDLED_DIR / sub
        if not d.exists():
            continue
        for p in d.glob("*.json"):
            try:
                blob = json.loads(p.read_text())
                stamp = blob["default_source"]["fetched_at"]
                if earliest is None or stamp < earliest:
                    earliest = stamp
            except Exception:
                continue
    return earliest or "(no data)"
```

(No new code besides adding `"fx_fixing"` to the tuple.)

- [ ] **Step 2: Verify the sidebar renders without error**

```bash
python -c "from fx_holiday_calculator.ui import sidebar; sidebar._bundled_fetched_at()"
```

Expected: prints nothing (function returns a string), no exception.

- [ ] **Step 3: Update the per-source-refresh footer copy**

Replace the closing caption in `render()`:

```python
sb.caption(
    "v1.1 covers 4 RTGS sources + 3 fixing sources (CFETS / KFTC / Taipei Forex). "
    "Exchange and additional sources deferred."
)
```

- [ ] **Step 4: Commit (user action)**

```bash
git add fx_holiday_calculator/ui/sidebar.py
git commit -m "feat(ui): sidebar covers fixing sources in refresh list and timestamp scan"
```

---

### Task 1.10: Library tripwire — fixing-calendar parallel block

**Files:**
- Modify: `tests/test_library_exchange.py` (the closest existing tripwire test) **or** create new `tests/test_library_tripwire_fixing.py`

For clean separation, create a new file.

- [ ] **Step 1: Write the tripwire test**

Create `tests/test_library_tripwire_fixing.py`:

```python
"""Tripwire: surface drift between bundled fixing calendars and python-holidays
public holidays for the corresponding country. Soft warnings only — fixing
calendars legitimately differ from public holidays (settlement vs. public
closure), so this never hard-fails CI.
"""
from datetime import date
from pathlib import Path

import pytest

from fx_holiday_calculator.calendars.loader import load_fixing_calendar

DATA_DIR = Path(__file__).parents[1] / "data"

_FIXING_TO_PYHOLIDAY = {
    "CNY": "CN",
    "KRW": "KR",
    "TWD": "TW",
}


def _fixing_dates(currency: str, year: int) -> set[date]:
    try:
        cal = load_fixing_calendar(currency, root=DATA_DIR / "fx_fixing")
    except FileNotFoundError:
        pytest.skip(f"No bundled fixing data for {currency}")
    return {d for d in cal.entries_by_date if d.year == year}


def _pyholiday_dates(country_code: str, year: int) -> set[date]:
    import holidays  # python-holidays
    cls = getattr(holidays, {"CN": "China", "KR": "SouthKorea", "TW": "Taiwan"}[country_code])
    return {d for d in cls(years=[year])}


@pytest.mark.parametrize("currency,country", list(_FIXING_TO_PYHOLIDAY.items()))
def test_fixing_calendar_overlaps_python_holidays(currency, country):
    """Verify that bundled fixing dates and python-holidays have meaningful overlap.
    A complete divergence usually indicates a parser bug or stale data.
    """
    year = 2026
    fixing = _fixing_dates(currency, year)
    pyhol = _pyholiday_dates(country, year)
    if not fixing:
        pytest.skip(f"No {currency} fixing entries for {year}")
    overlap = fixing & pyhol
    coverage = len(overlap) / max(len(pyhol), 1)
    # Expect >= 50% overlap; below that, raise a soft warning, but don't fail.
    if coverage < 0.5:
        import warnings
        warnings.warn(
            f"{currency} fixing calendar overlaps python-holidays {country} by only "
            f"{coverage:.0%} for {year}. Verify the bundled data is current and "
            f"the parser is intact."
        )
```

- [ ] **Step 2: Run the test**

```bash
pytest tests/test_library_tripwire_fixing.py -v
```

Expected: pass or skip (depending on whether bundled fixing JSON exists).

- [ ] **Step 3: Commit (user action)**

```bash
git add tests/test_library_tripwire_fixing.py
git commit -m "test(tripwire): warn on drift between fixing calendars and python-holidays"
```

---

## Phase 2 — NDF engine

### Task 2.1: `ndf.py` module skeleton — `NdfResult` and `InvalidNdfPairError`

**Files:**
- Create: `fx_holiday_calculator/ndf.py`
- Create: `tests/test_ndf.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ndf.py`:

```python
from datetime import date, datetime, timezone

import pytest

from fx_holiday_calculator.calendars.fixing import FixingCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import HolidayEntry, SourceRef
from fx_holiday_calculator.ndf import (
    InvalidNdfPairError,
    NdfResult,
    calculate_ndf_dates,
)
from fx_holiday_calculator.pairs import parse_pair
from fx_holiday_calculator.tenor import parse_tenor

WINDOW = dict(valid_from=date(2020, 1, 1), valid_until=date(2030, 12, 31))


def _src() -> SourceRef:
    return SourceRef(
        url="https://x",
        doc_title="x",
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        fetcher="t",
    )


def _empty_rtgs(c: str) -> RtgsCalendar:
    return RtgsCalendar(currency=c, calendar_name=c, operator="x", entries_by_date={}, **WINDOW)


def _empty_fixing(c: str) -> FixingCalendar:
    return FixingCalendar(
        currency=c, calendar_name=c, operator="x", entries_by_date={}, **WINDOW
    )


def test_reject_non_ndf_pair():
    cals = {"USD": _empty_rtgs("USD"), "EUR": _empty_rtgs("EUR")}
    fix = _empty_fixing("EUR")  # placeholder; will be rejected before use
    with pytest.raises(InvalidNdfPairError):
        calculate_ndf_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("EUR/USD"),
            tenor=parse_tenor("3M"),
            rtgs_calendars=cals,
            fixing_calendar=fix,
        )


def test_result_dataclass_shape():
    r = NdfResult(
        trade_date=date(2026, 5, 6),
        spot_date=date(2026, 5, 8),
        fixing_date=date(2026, 8, 6),
        settlement_date=date(2026, 8, 10),
        spot_trace=[],
        settlement_trace=[],
        fixing_trace=[],
        calendars_used=[],
        warnings=[],
    )
    assert r.trade_date == date(2026, 5, 6)
    assert r.fixing_date < r.settlement_date
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_ndf.py -v
```

Expected: `ModuleNotFoundError: fx_holiday_calculator.ndf`.

- [ ] **Step 3: Implement `fx_holiday_calculator/ndf.py` skeleton**

```python
"""NDF date math.

Non-deliverable forwards settle in USD only; the non-deliverable side fixes
against a primary-source fixing rate (CFETS for CNY, KFTC for KRW, Taipei
Forex for TWD). This module computes spot, settlement, and fixing dates
with full provenance traces.

Conventions: see docs/conventions.md §9.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from fx_holiday_calculator.calendars.fixing import FixingCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.conventions.business_day import (
    AdjustmentStep,
    CalendarSet,
    apply_eom_with_trace,
    is_good_business_day,
    roll_with_trace,
)
from fx_holiday_calculator.conventions.dates import add_period, next_imm_date
from fx_holiday_calculator.conventions.spot_offset import apply_spot_offset
from fx_holiday_calculator.pairs import Pair
from fx_holiday_calculator.tenor import InvalidTenorError, Tenor


class InvalidNdfPairError(ValueError):
    """Raised when calculate_ndf_dates is given a deliverable pair."""


class InvalidTradeDateError(ValueError):
    """Trade date is not a good USD-RTGS business day."""


class InvalidBrokenDateError(ValueError):
    """Settlement date rolls to ≤ spot."""


@dataclass
class NdfResult:
    trade_date: date
    spot_date: date
    fixing_date: date
    settlement_date: date
    spot_trace: list[AdjustmentStep]
    settlement_trace: list[AdjustmentStep]
    fixing_trace: list[AdjustmentStep]
    calendars_used: list[str]
    warnings: list[str] = field(default_factory=list)


def calculate_ndf_dates(
    *,
    trade_date: date,
    pair: Pair,
    tenor: Optional[Tenor] = None,
    target_settlement: Optional[date] = None,
    rtgs_calendars: dict[str, RtgsCalendar],
    fixing_calendar: FixingCalendar,
) -> NdfResult:
    if not pair.ndf:
        raise InvalidNdfPairError(
            f"{pair.base}/{pair.quote} is not configured as an NDF pair "
            f"(pair.ndf is False)."
        )
    # Tenor-driven path implementation will be added in Task 2.2.
    # Maturity-driven path in Task 2.3.
    raise NotImplementedError("body added in Task 2.2 / 2.3")
```

- [ ] **Step 4: Run tests — `test_reject_non_ndf_pair` and `test_result_dataclass_shape` pass**

```bash
pytest tests/test_ndf.py -v
```

Expected: those two tests green. Other tests in this file will be added by subsequent tasks.

- [ ] **Step 5: Commit (user action)**

```bash
git add fx_holiday_calculator/ndf.py tests/test_ndf.py
git commit -m "feat(ndf): scaffold NdfResult and InvalidNdfPairError"
```

---

### Task 2.2: NDF tenor-driven path

**Files:**
- Modify: `fx_holiday_calculator/ndf.py`
- Modify: `tests/test_ndf.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ndf.py`:

```python
def test_tenor_driven_3m_clean_dates():
    cals = {"USD": _empty_rtgs("USD")}
    fix = _empty_fixing("CNY")
    r = calculate_ndf_dates(
        trade_date=date(2026, 5, 6),  # Wed
        pair=parse_pair("USD/CNY"),
        tenor=parse_tenor("3M"),
        rtgs_calendars=cals,
        fixing_calendar=fix,
    )
    # Spot is T+2 on USD only -> 2026-05-08 (Fri)
    assert r.spot_date == date(2026, 5, 8)
    # Settlement = spot + 3M = 2026-08-08 (Sat) -> mod-following -> Mon 2026-08-10
    assert r.settlement_date == date(2026, 8, 10)
    # Fixing = settlement - 2BD on fixing cal -> 2026-08-06 (Thu)
    assert r.fixing_date == date(2026, 8, 6)
    assert r.fixing_date < r.settlement_date


def test_tenor_driven_fixing_skips_fixing_holiday():
    # CNY fixing has a holiday on Mon 2026-08-10 -> settlement rolls forward,
    # but if 2026-08-10 is good USD/RTGS but bad fixing, settlement must roll.
    cny_hol = HolidayEntry(
        date=date(2026, 8, 10),
        name="Mock holiday",
        note=None,
        source=_src(),
        source_origin="bundled",
        is_closure=True,
    )
    fix = FixingCalendar(
        currency="CNY",
        calendar_name="CNY",
        operator="x",
        entries_by_date={date(2026, 8, 10): cny_hol},
        **WINDOW,
    )
    cals = {"USD": _empty_rtgs("USD")}
    r = calculate_ndf_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("USD/CNY"),
        tenor=parse_tenor("3M"),
        rtgs_calendars=cals,
        fixing_calendar=fix,
    )
    # Settlement must skip 2026-08-10 -> 2026-08-11
    assert r.settlement_date == date(2026, 8, 11)
    # Fixing = settlement - 2BD on fixing cal
    assert r.fixing_date == date(2026, 8, 7)


def test_tenor_driven_imm_tenor():
    cals = {"USD": _empty_rtgs("USD")}
    fix = _empty_fixing("CNY")
    r = calculate_ndf_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("USD/CNY"),
        tenor=parse_tenor("IMM1"),  # next IMM after spot
        rtgs_calendars=cals,
        fixing_calendar=fix,
    )
    # IMM1 after spot 2026-05-08 -> June IMM = 2026-06-17 (3rd Wed)
    assert r.settlement_date == date(2026, 6, 17)
    # Fixing = 2 BD before, all good days -> 2026-06-15
    assert r.fixing_date == date(2026, 6, 15)


def test_trade_date_not_good_usd_rtgs():
    cals = {"USD": _empty_rtgs("USD")}
    fix = _empty_fixing("CNY")
    with pytest.raises(InvalidTradeDateError):
        calculate_ndf_dates(
            trade_date=date(2026, 5, 9),  # Sat
            pair=parse_pair("USD/CNY"),
            tenor=parse_tenor("3M"),
            rtgs_calendars=cals,
            fixing_calendar=fix,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_ndf.py -v
```

Expected: `NotImplementedError`.

- [ ] **Step 3: Implement the tenor-driven body**

Replace the `raise NotImplementedError(...)` body of `calculate_ndf_dates` in `fx_holiday_calculator/ndf.py`:

```python
    # USD-only RTGS set for spot offset and settlement.
    if "USD" not in rtgs_calendars:
        raise KeyError("rtgs_calendars must contain 'USD'")
    usd = rtgs_calendars["USD"]
    usd_cs = CalendarSet(members={"USD": usd})

    # Combined USD + fixing for settlement roll.
    settle_cs = CalendarSet(
        members={"USD": usd, pair.fixing_currency: fixing_calendar}  # type: ignore[dict-item]
    )

    # Fixing-only set for back-counting fixing date.
    fixing_cs = CalendarSet(members={pair.fixing_currency: fixing_calendar})  # type: ignore[dict-item]

    if not is_good_business_day(trade_date, usd_cs):
        raise InvalidTradeDateError(
            f"Trade date {trade_date.isoformat()} is not a good USD-RTGS day."
        )

    spot_result = apply_spot_offset(trade_date, pair, usd_cs)

    # Resolve target settlement either from tenor or from user-supplied target.
    if tenor is None and target_settlement is None:
        raise ValueError("Exactly one of tenor / target_settlement must be provided")
    if tenor is not None and target_settlement is not None:
        raise ValueError("Provide tenor OR target_settlement, not both")

    if tenor is not None:
        if tenor.kind in {"SPOT", "ON", "TN", "SN"}:
            raise InvalidTenorError("NDF requires a forward tenor (PERIOD / IMM / BROKEN).")
        if tenor.kind == "PERIOD":
            raw_settlement = add_period(spot_result.spot_date, tenor.period_unit, tenor.period_n)
            settlement, settle_trace = apply_eom_with_trace(
                spot_result.spot_date, raw_settlement, settle_cs
            )
        elif tenor.kind == "IMM":
            raw_settlement = next_imm_date(spot_result.spot_date, tenor.imm_index)
            settlement, settle_trace = roll_with_trace(
                raw_settlement, settle_cs, "modified_following"
            )
        else:  # BROKEN
            settlement, settle_trace = roll_with_trace(
                tenor.target_date, settle_cs, "modified_following"  # type: ignore[arg-type]
            )
    else:
        settlement, settle_trace = roll_with_trace(
            target_settlement,  # type: ignore[arg-type]
            settle_cs,
            "modified_following",
        )

    if settlement <= spot_result.spot_date:
        raise InvalidBrokenDateError(
            f"NDF settlement rolls to {settlement.isoformat()}, "
            f"which is not after spot {spot_result.spot_date.isoformat()}."
        )

    # Back-count fixing = settlement - 2 BD on the fixing calendar.
    fixing_trace: list[AdjustmentStep] = []
    fixing_candidate = settlement
    good_bd_count = 0
    while good_bd_count < 2:
        fixing_candidate = fixing_candidate - timedelta(days=1)
        if is_good_business_day(fixing_candidate, fixing_cs):
            good_bd_count += 1
    fixing_date, fix_roll_trace = roll_with_trace(fixing_candidate, fixing_cs, "preceding")
    fixing_trace.extend(fix_roll_trace)

    calendars_used = [f"USD ({usd.calendar_name})",
                      f"{fixing_calendar.currency} ({fixing_calendar.calendar_name})"]

    warnings: list[str] = []
    if (fixing_date - trade_date).days < 2:
        warnings.append(
            f"Short fixing horizon: fixing date {fixing_date.isoformat()} is within 2 "
            f"days of trade date {trade_date.isoformat()}. Confirm with counterparty."
        )

    return NdfResult(
        trade_date=trade_date,
        spot_date=spot_result.spot_date,
        fixing_date=fixing_date,
        settlement_date=settlement,
        spot_trace=spot_result.trace,
        settlement_trace=settle_trace,
        fixing_trace=fixing_trace,
        calendars_used=calendars_used,
        warnings=warnings,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_ndf.py -v
```

Expected: all green except any maturity-driven tests, which arrive in Task 2.3.

- [ ] **Step 5: Commit (user action)**

```bash
git add fx_holiday_calculator/ndf.py tests/test_ndf.py
git commit -m "feat(ndf): tenor-driven settlement and fixing-date math"
```

---

### Task 2.3: NDF maturity-driven path

**Files:**
- Modify: `tests/test_ndf.py`

The implementation in Task 2.2 already covers the maturity-driven branch via the `target_settlement` parameter; this task is purely test coverage.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ndf.py`:

```python
def test_maturity_driven_clean():
    cals = {"USD": _empty_rtgs("USD")}
    fix = _empty_fixing("CNY")
    r = calculate_ndf_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("USD/CNY"),
        target_settlement=date(2026, 8, 10),  # Mon — already a good day
        rtgs_calendars=cals,
        fixing_calendar=fix,
    )
    assert r.settlement_date == date(2026, 8, 10)
    assert r.fixing_date == date(2026, 8, 6)


def test_maturity_driven_rejects_pre_spot_target():
    cals = {"USD": _empty_rtgs("USD")}
    fix = _empty_fixing("CNY")
    with pytest.raises(InvalidBrokenDateError):
        calculate_ndf_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("USD/CNY"),
            target_settlement=date(2026, 5, 7),  # before spot 2026-05-08
            rtgs_calendars=cals,
            fixing_calendar=fix,
        )


def test_rejects_both_tenor_and_target():
    cals = {"USD": _empty_rtgs("USD")}
    fix = _empty_fixing("CNY")
    with pytest.raises(ValueError):
        calculate_ndf_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("USD/CNY"),
            tenor=parse_tenor("3M"),
            target_settlement=date(2026, 8, 10),
            rtgs_calendars=cals,
            fixing_calendar=fix,
        )


def test_rejects_neither_tenor_nor_target():
    cals = {"USD": _empty_rtgs("USD")}
    fix = _empty_fixing("CNY")
    with pytest.raises(ValueError):
        calculate_ndf_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("USD/CNY"),
            rtgs_calendars=cals,
            fixing_calendar=fix,
        )
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_ndf.py -v
```

Expected: all green.

- [ ] **Step 3: Commit (user action)**

```bash
git add tests/test_ndf.py
git commit -m "test(ndf): maturity-driven and exclusive-input validation"
```

---

### Task 2.4: NDF — tenor restrictions

**Files:**
- Modify: `tests/test_ndf.py`

The tenor restriction is already implemented (Task 2.2 rejects SPOT/ON/TN/SN). Confirm via tests.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ndf.py`:

```python
@pytest.mark.parametrize("bad", ["SPOT", "ON", "TN", "SN"])
def test_ndf_rejects_non_forward_tenor(bad):
    cals = {"USD": _empty_rtgs("USD")}
    fix = _empty_fixing("CNY")
    with pytest.raises(InvalidTenorError):
        calculate_ndf_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("USD/CNY"),
            tenor=parse_tenor(bad),
            rtgs_calendars=cals,
            fixing_calendar=fix,
        )
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_ndf.py -v
```

Expected: all four parametrised cases green.

- [ ] **Step 3: Commit (user action)**

```bash
git add tests/test_ndf.py
git commit -m "test(ndf): reject SPOT/ON/TN/SN tenors"
```

---

### Task 2.5: Public API exposure + `docs/conventions.md` §9

**Files:**
- Modify: `fx_holiday_calculator/__init__.py`
- Modify: `docs/conventions.md`

- [ ] **Step 1: Re-export the NDF public API**

In `fx_holiday_calculator/__init__.py`, add:

```python
from fx_holiday_calculator.ndf import (
    InvalidNdfPairError,
    NdfResult,
    calculate_ndf_dates,
)
```

Append the names to `__all__` if the file defines one.

- [ ] **Step 2: Append `docs/conventions.md` §9**

Append the following section after §8:

```markdown
## 9. NDF (Non-Deliverable Forward) — fixing & settlement

Non-deliverable forwards settle in USD only. The non-deliverable side
(CNY / KRW / TWD in v1.1) fixes against a primary-source rate published by
the local market organisation:

- **CNY** — CFETS / PBoC USD/CNY central parity (中间价)
- **KRW** — KFTC USD/KRW Market Average Rate
- **TWD** — Taipei Forex Inc. USD/TWD reference rate (TAIFX1)

### 9.1 Date relations

- **Spot** = `T + pair.spot_offset_days` on **USD RTGS only** (Fedwire). The
  non-deliverable side has no settlement leg, so its RTGS does not constrain
  spot.
- **Settlement** (tenor-driven) = `spot + tenor`, rolled `modified_following`
  on the union `{USD RTGS, fixing_calendar}`. EOM rule applies keyed on spot.
- **Settlement** (maturity-driven) = user-supplied target date, rolled
  `modified_following` on the same union. Rejected if rolled settlement ≤ spot.
- **Fixing date** = `settlement − 2 business days` on the fixing calendar.
  The fixing-day calendar must allow a fix to be published; the 2-day lag
  matches EMTA / ISDA EM template terms for these currencies.

### 9.2 Validations

- `InvalidNdfPairError` — pair is not configured as NDF (`pair.ndf is False`).
- `InvalidTradeDateError` — trade date is not a good USD-RTGS business day.
- `InvalidTenorError` — tenor is SPOT / ON / TN / SN (NDF requires a forward
  tenor; v1.1 accepts PERIOD / IMM / BROKEN).
- `InvalidBrokenDateError` — rolled settlement ≤ spot.

### 9.3 Warnings

- *Short fixing horizon* — `(fixing_date - trade_date).days < 2`. Surfaces a
  warning that fixing falls within 2 days of trade and may not be achievable
  with the counterparty.

### 9.4 References

- EMTA template terms for CNY / KRW / TWD non-deliverable forwards.
- ISDA 1998 FX and Currency Options Definitions, §1.18 (Business Day) and
  §3.7 (Settlement Date).
- CFETS market notices (chinamoney.com.cn).
- KFTC FX market trading calendar (kftc.or.kr).
- Taipei Forex Inc. (taifex.com.tw).
```

- [ ] **Step 3: Verify import works**

```bash
python -c "from fx_holiday_calculator import calculate_ndf_dates, NdfResult, InvalidNdfPairError; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit (user action)**

```bash
git add fx_holiday_calculator/__init__.py docs/conventions.md
git commit -m "docs(conventions): document NDF date math (§9); export public API"
```

---

## Phase 3 — Option engine

### Task 3.1: `option.py` skeleton — `OptionResult` and errors

**Files:**
- Create: `fx_holiday_calculator/option.py`
- Create: `tests/test_option.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_option.py`:

```python
from datetime import date, datetime, timezone

import pytest

from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import HolidayEntry, SourceRef
from fx_holiday_calculator.option import (
    InvalidOptionStyleError,
    ListedOptionVenueRequiredError,
    OptionResult,
    calculate_option_dates,
)
from fx_holiday_calculator.pairs import parse_pair
from fx_holiday_calculator.tenor import InvalidTenorError, parse_tenor

WINDOW = dict(valid_from=date(2020, 1, 1), valid_until=date(2030, 12, 31))


def _src() -> SourceRef:
    return SourceRef(
        url="https://x",
        doc_title="x",
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        fetcher="t",
    )


def _empty_rtgs(c: str) -> RtgsCalendar:
    return RtgsCalendar(currency=c, calendar_name=c, operator="x", entries_by_date={}, **WINDOW)


def _empty_exchange(v: str) -> ExchangeCalendar:
    return ExchangeCalendar(
        venue=v, products=(), entries_by_date={}, library_sourced=False, **WINDOW
    )


def test_rejects_unknown_style():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    with pytest.raises(InvalidOptionStyleError):
        calculate_option_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("EUR/USD"),
            tenor=parse_tenor("1M"),
            style="HYBRID",  # type: ignore[arg-type]
            rtgs_calendars=cals,
        )


def test_listed_requires_venue_and_exchange_cal():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    with pytest.raises(ListedOptionVenueRequiredError):
        calculate_option_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("EUR/USD"),
            tenor=parse_tenor("1M"),
            style="LISTED",
            rtgs_calendars=cals,
        )


def test_result_dataclass_shape():
    r = OptionResult(
        trade_date=date(2026, 5, 6),
        spot_date=date(2026, 5, 8),
        expiry_date=date(2026, 6, 8),
        delivery_date=date(2026, 6, 10),
        style="OTC",
        expiry_trace=[],
        delivery_trace=[],
        calendars_used=[],
        warnings=[],
    )
    assert r.expiry_date < r.delivery_date
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_option.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `fx_holiday_calculator/option.py` skeleton**

```python
"""FX option date math: expiry and delivery.

OTC: expiry rolls on RTGS (base + quote + ref). Delivery rolls on base + quote
(no reference-currency constraint on the delivery leg).

Listed: expiry rolls on the venue's exchange calendar. Delivery rolls on
base + quote RTGS (cash legs still settle bilaterally).

Conventions: see docs/conventions.md §10.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal, Optional

from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.conventions.business_day import (
    AdjustmentStep,
    CalendarSet,
    apply_eom_with_trace,
    roll_with_trace,
)
from fx_holiday_calculator.conventions.cross import RefCurrency, rtgs_calendar_set
from fx_holiday_calculator.conventions.dates import add_period, next_imm_date
from fx_holiday_calculator.conventions.spot_offset import apply_spot_offset
from fx_holiday_calculator.pairs import Pair
from fx_holiday_calculator.tenor import InvalidTenorError, Tenor

OptionStyle = Literal["OTC", "LISTED"]


class InvalidOptionStyleError(ValueError):
    pass


class ListedOptionVenueRequiredError(ValueError):
    pass


@dataclass
class OptionResult:
    trade_date: date
    spot_date: date
    expiry_date: date
    delivery_date: date
    style: OptionStyle
    expiry_trace: list[AdjustmentStep]
    delivery_trace: list[AdjustmentStep]
    calendars_used: list[str]
    warnings: list[str] = field(default_factory=list)


def calculate_option_dates(
    *,
    trade_date: date,
    pair: Pair,
    tenor: Tenor,
    style: OptionStyle,
    ref_currency: RefCurrency = "USD",
    rtgs_calendars: dict[str, RtgsCalendar],
    exchange_calendar: Optional[ExchangeCalendar] = None,
    venue: Optional[str] = None,
) -> OptionResult:
    if style not in ("OTC", "LISTED"):
        raise InvalidOptionStyleError(f"Unknown option style: {style!r}")

    if style == "LISTED":
        if exchange_calendar is None or venue is None or venue not in pair.listed_on:
            raise ListedOptionVenueRequiredError(
                f"LISTED option requires a venue from pair.listed_on={pair.listed_on} "
                f"and a matching exchange_calendar."
            )

    if tenor.kind in {"SPOT", "ON", "TN", "SN"}:
        raise InvalidTenorError("Option requires a forward tenor (PERIOD / IMM / BROKEN).")

    # Spot uses the full RTGS set (base + quote + ref).
    rtgs_cs = rtgs_calendar_set(pair, ref=ref_currency, calendars=rtgs_calendars)
    spot_result = apply_spot_offset(trade_date, pair, rtgs_cs)

    # Build expiry calendar set.
    if style == "OTC":
        expiry_cs = rtgs_cs
    else:
        expiry_cs = CalendarSet(members={venue: exchange_calendar})  # type: ignore[dict-item]

    # Raw expiry from spot + tenor.
    if tenor.kind == "PERIOD":
        raw_expiry = add_period(spot_result.spot_date, tenor.period_unit, tenor.period_n)
        expiry_date, expiry_trace = apply_eom_with_trace(
            spot_result.spot_date, raw_expiry, expiry_cs
        )
    elif tenor.kind == "IMM":
        raw_expiry = next_imm_date(spot_result.spot_date, tenor.imm_index)
        expiry_date, expiry_trace = roll_with_trace(raw_expiry, expiry_cs, "modified_following")
    else:  # BROKEN
        expiry_date, expiry_trace = roll_with_trace(
            tenor.target_date, expiry_cs, "modified_following"  # type: ignore[arg-type]
        )

    # Delivery on base + quote RTGS only (no ref).
    delivery_cs = CalendarSet(
        members={pair.base: rtgs_calendars[pair.base], pair.quote: rtgs_calendars[pair.quote]}
    )
    raw_delivery = expiry_date + timedelta(days=pair.spot_offset_days)
    # Use 'following' rather than mod-following for delivery — the option's
    # delivery is an extension off expiry, not a forward leg with month-boundary
    # logic.
    delivery_date, delivery_trace = roll_with_trace(raw_delivery, delivery_cs, "following")

    calendars_used = []
    for label, cal in expiry_cs.members.items():
        if isinstance(cal, RtgsCalendar):
            calendars_used.append(f"{label} ({cal.calendar_name})")
        else:
            calendars_used.append(label)
    for label, cal in delivery_cs.members.items():
        calendars_used.append(f"{label} ({cal.calendar_name})")

    warnings: list[str] = []
    if expiry_date == spot_result.spot_date:
        warnings.append(
            f"Option expires on spot date {expiry_date.isoformat()} — unusual, verify intent."
        )

    return OptionResult(
        trade_date=trade_date,
        spot_date=spot_result.spot_date,
        expiry_date=expiry_date,
        delivery_date=delivery_date,
        style=style,
        expiry_trace=expiry_trace,
        delivery_trace=delivery_trace,
        calendars_used=calendars_used,
        warnings=warnings,
    )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_option.py -v
```

Expected: the three skeleton-level tests pass.

- [ ] **Step 5: Commit (user action)**

```bash
git add fx_holiday_calculator/option.py tests/test_option.py
git commit -m "feat(option): scaffold OptionResult, errors, and OTC/Listed dispatch"
```

---

### Task 3.2: Option OTC path — clean & holiday-driven cases

**Files:**
- Modify: `tests/test_option.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_option.py`:

```python
def test_otc_option_clean_eurusd_1m():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    r = calculate_option_dates(
        trade_date=date(2026, 5, 6),  # Wed
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("1M"),
        style="OTC",
        ref_currency="none",
        rtgs_calendars=cals,
    )
    # Spot = T+2 on EUR+USD -> 2026-05-08 (Fri)
    assert r.spot_date == date(2026, 5, 8)
    # Expiry = spot + 1M -> 2026-06-08 (Mon — good day)
    assert r.expiry_date == date(2026, 6, 8)
    # Delivery = expiry + 2 BD -> 2026-06-10 (Wed)
    assert r.delivery_date == date(2026, 6, 10)


def test_otc_option_expiry_skips_holiday():
    # EUR has a holiday on 2026-06-08 -> expiry rolls forward.
    eur_hol = HolidayEntry(
        date=date(2026, 6, 8),
        name="Mock",
        note=None,
        source=_src(),
        source_origin="bundled",
        is_closure=True,
    )
    eur = RtgsCalendar(
        currency="EUR", calendar_name="EUR", operator="x",
        entries_by_date={date(2026, 6, 8): eur_hol}, **WINDOW,
    )
    cals = {"EUR": eur, "USD": _empty_rtgs("USD")}
    r = calculate_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("1M"),
        style="OTC",
        ref_currency="none",
        rtgs_calendars=cals,
    )
    assert r.expiry_date == date(2026, 6, 9)  # rolled past EUR holiday
    assert r.delivery_date == date(2026, 6, 11)  # spot lag from new expiry


def test_otc_option_delivery_ignores_ref_currency_holiday():
    # ref=JPY has a holiday on the delivery candidate. Delivery should not
    # be constrained by the reference currency — only by base + quote.
    jpy_hol = HolidayEntry(
        date=date(2026, 6, 10),
        name="Mock",
        note=None,
        source=_src(),
        source_origin="bundled",
        is_closure=True,
    )
    jpy = RtgsCalendar(
        currency="JPY", calendar_name="JPY", operator="x",
        entries_by_date={date(2026, 6, 10): jpy_hol}, **WINDOW,
    )
    cals = {
        "EUR": _empty_rtgs("EUR"),
        "USD": _empty_rtgs("USD"),
        "JPY": jpy,
    }
    r = calculate_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("1M"),
        style="OTC",
        ref_currency="JPY",  # type: ignore[arg-type]
        rtgs_calendars=cals,
    )
    # Delivery still falls on 2026-06-10 because JPY does not constrain delivery.
    assert r.delivery_date == date(2026, 6, 10)
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_option.py -v
```

Expected: all green (Task 3.1 implementation already covers these paths).

- [ ] **Step 3: Commit (user action)**

```bash
git add tests/test_option.py
git commit -m "test(option): OTC expiry rolls on RTGS, delivery ignores ref currency"
```

---

### Task 3.3: Option Listed path

**Files:**
- Modify: `tests/test_option.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_option.py`:

```python
def test_listed_option_expiry_rolls_on_exchange_only():
    # CME has a holiday on 2026-06-08; EUR/USD RTGS do not.
    cme_hol = HolidayEntry(
        date=date(2026, 6, 8),
        name="CME closed",
        note=None,
        source=_src(),
        source_origin="bundled",
        is_closure=True,
    )
    cme = ExchangeCalendar(
        venue="CME", products=("EURUSD",),
        entries_by_date={date(2026, 6, 8): cme_hol},
        library_sourced=False, **WINDOW,
    )
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    r = calculate_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("1M"),
        style="LISTED",
        ref_currency="none",
        rtgs_calendars=cals,
        exchange_calendar=cme,
        venue="CME",
    )
    # Expiry rolls past CME holiday -> 2026-06-09
    assert r.expiry_date == date(2026, 6, 9)
    # Delivery on RTGS-only (no CME) -> 2026-06-11
    assert r.delivery_date == date(2026, 6, 11)


def test_listed_option_rtgs_holiday_does_not_shift_expiry():
    # EUR has a holiday on 2026-06-08 but CME does not. Expiry stays on
    # 2026-06-08 because LISTED option expiry rolls only on exchange.
    eur_hol = HolidayEntry(
        date=date(2026, 6, 8),
        name="EUR holiday",
        note=None,
        source=_src(),
        source_origin="bundled",
        is_closure=True,
    )
    eur = RtgsCalendar(
        currency="EUR", calendar_name="EUR", operator="x",
        entries_by_date={date(2026, 6, 8): eur_hol}, **WINDOW,
    )
    cme = _empty_exchange("CME")
    cals = {"EUR": eur, "USD": _empty_rtgs("USD")}
    r = calculate_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("1M"),
        style="LISTED",
        ref_currency="none",
        rtgs_calendars=cals,
        exchange_calendar=cme,
        venue="CME",
    )
    assert r.expiry_date == date(2026, 6, 8)
    # But delivery, which uses RTGS, rolls past EUR holiday at expiry+2 BD
    assert r.delivery_date >= date(2026, 6, 10)
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_option.py -v
```

Expected: all green.

- [ ] **Step 3: Commit (user action)**

```bash
git add tests/test_option.py
git commit -m "test(option): Listed expiry rolls only on exchange; delivery on RTGS"
```

---

### Task 3.4: Option tenor restrictions & same-day-expiry warning

**Files:**
- Modify: `tests/test_option.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_option.py`:

```python
@pytest.mark.parametrize("bad", ["SPOT", "ON", "TN", "SN"])
def test_option_rejects_non_forward_tenor(bad):
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    with pytest.raises(InvalidTenorError):
        calculate_option_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("EUR/USD"),
            tenor=parse_tenor(bad),
            style="OTC",
            ref_currency="none",
            rtgs_calendars=cals,
        )


def test_option_same_day_expiry_warning():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    # BROKEN tenor with target == spot date triggers same-day-expiry.
    r = calculate_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("2026-05-08"),  # spot
        style="OTC",
        ref_currency="none",
        rtgs_calendars=cals,
    )
    assert r.expiry_date == r.spot_date
    assert any("expires on spot" in w for w in r.warnings)
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_option.py -v
```

Expected: all green.

- [ ] **Step 3: Commit (user action)**

```bash
git add tests/test_option.py
git commit -m "test(option): reject non-forward tenors; warn on same-day expiry"
```

---

### Task 3.5: Public API + `docs/conventions.md` §10

**Files:**
- Modify: `fx_holiday_calculator/__init__.py`
- Modify: `docs/conventions.md`

- [ ] **Step 1: Re-export option API**

In `fx_holiday_calculator/__init__.py`, add:

```python
from fx_holiday_calculator.option import (
    InvalidOptionStyleError,
    ListedOptionVenueRequiredError,
    OptionResult,
    calculate_option_dates,
)
```

- [ ] **Step 2: Append `docs/conventions.md` §10**

```markdown
## 10. FX Option — expiry & delivery

FX options have two characteristic dates:

- **Expiry date** — the day the option contract expires.
- **Delivery date** — the day the cash legs settle if the option is exercised.

The relationship is `delivery = expiry + pair.spot_offset_days` (a vanilla
forward outright off the expiry). Where the dates roll on different
calendars depending on style:

| Style  | Expiry calendar set            | Delivery calendar set      |
|--------|--------------------------------|----------------------------|
| OTC    | RTGS{base, quote, ref}         | RTGS{base, quote} only     |
| LISTED | Exchange{venue}                | RTGS{base, quote} only     |

The delivery leg deliberately omits the reference currency: the option's
delivery is the physical exchange of two currencies, not a cross-currency
constrained spot. Reference: ISDA 1998 FX and Currency Options Definitions
§3.2 (Expiration Date and Settlement Date).

### 10.1 Validations

- `InvalidOptionStyleError` — `style ∉ {OTC, LISTED}`.
- `ListedOptionVenueRequiredError` — `style == LISTED` with no venue
  provided, or venue not in `pair.listed_on`, or no exchange calendar
  provided.
- `InvalidTenorError` — tenor is SPOT / ON / TN / SN (option requires
  a forward tenor).

### 10.2 Warnings

- *Same-day expiry* — `expiry_date == spot_date` (rare; usually a
  user-error verifying a zero-day broken-date option). Surfaced via
  `result.warnings`.
- *Listed library-sourced caveat* — when `exchange_calendar.library_sourced
  is True`, the UI surfaces the existing exchange-calendar caveat that the
  data is equity-session-based, not FX-product-specific.

### 10.3 Where this lives

- Engine: `fx_holiday_calculator/option.py`
- Tests: `tests/test_option.py`
```

- [ ] **Step 3: Verify import**

```bash
python -c "from fx_holiday_calculator import calculate_option_dates, OptionResult; print('ok')"
```

- [ ] **Step 4: Commit (user action)**

```bash
git add fx_holiday_calculator/__init__.py docs/conventions.md
git commit -m "docs(conventions): document FX option date math (§10)"
```

---

## Phase 4 — Futures engine

### Task 4.1: `imm_last_trade_date` helper in `conventions/business_day.py`

**Files:**
- Modify: `fx_holiday_calculator/conventions/business_day.py`
- Modify: `tests/test_business_day.py`

- [ ] **Step 1: Write the failing tests**

The existing `tests/test_business_day.py` already imports `_cal()` helper (creates an `RtgsCalendar` with a list of holiday dates) and `CalendarSet`. Use those. Append:

```python
# At top of file, extend the existing import line:
from fx_holiday_calculator.conventions.business_day import (
    CalendarSet,
    apply_eom,
    apply_eom_with_trace,
    imm_last_trade_date,   # NEW
    is_good_business_day,
    last_business_day_of_month,
    roll,
    roll_with_trace,
)


def test_imm_last_trade_date_clean_month():
    cs = CalendarSet({"X": _cal("X", [])})
    # June 2026 — 3rd Wed = 2026-06-17. LTD = 2 BD back = 2026-06-15 (Mon).
    ltd = imm_last_trade_date((2026, 6), cs)
    assert ltd == date(2026, 6, 15)


def test_imm_last_trade_date_with_friday_and_monday_holidays():
    cs = CalendarSet({"X": _cal("X", [date(2026, 6, 12), date(2026, 6, 15)])})
    # Counting back from 2026-06-17 (3rd Wed, good):
    #   06-16 (Tue, good) -> count 1
    #   06-15 (Mon, holiday) -> skip
    #   06-12 (Fri, holiday) -> skip
    #   06-11 (Thu, good) -> count 2
    ltd = imm_last_trade_date((2026, 6), cs)
    assert ltd == date(2026, 6, 11)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_business_day.py -k imm_last_trade -v
```

Expected: `ImportError: cannot import name 'imm_last_trade_date'`.

- [ ] **Step 3: Add `imm_last_trade_date` to `business_day.py`**

Append to `fx_holiday_calculator/conventions/business_day.py`:

```python
def imm_last_trade_date(contract_month: tuple[int, int], cs: CalendarSet) -> date:
    """Compute the FX-futures last trade date: 2 good business days before the
    unrolled 3rd Wednesday of `contract_month`, on the supplied calendar set.

    Used by all three venues in v1.1 (CME, HKEX, SGX) — see CME Rule 25102.E
    for the EUR/USD canonical example. The unrolled 3rd Wed is the anchor,
    not the rolled delivery date: LTD does not chain off delivery.
    """
    from fx_holiday_calculator.conventions.dates import imm_third_wednesday

    year, month = contract_month
    anchor = imm_third_wednesday(year, month)
    cur = anchor
    good_count = 0
    while good_count < 2:
        cur = cur - timedelta(days=1)
        if is_good_business_day(cur, cs):
            good_count += 1
    return cur
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_business_day.py -v
```

Expected: all green.

- [ ] **Step 5: Commit (user action)**

```bash
git add fx_holiday_calculator/conventions/business_day.py tests/test_business_day.py
git commit -m "feat(conventions): add imm_last_trade_date helper for FX futures"
```

---

### Task 4.2: `future.py` skeleton — `FutureResult` and errors

**Files:**
- Create: `fx_holiday_calculator/future.py`
- Create: `tests/test_future.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_future.py`:

```python
from datetime import date, datetime, timezone

import pytest

from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import HolidayEntry, SourceRef
from fx_holiday_calculator.future import (
    FutureResult,
    InvalidContractMonthError,
    VenueNotListedError,
    calculate_future_dates,
)
from fx_holiday_calculator.pairs import parse_pair
from fx_holiday_calculator.tenor import parse_tenor

WINDOW = dict(valid_from=date(2020, 1, 1), valid_until=date(2030, 12, 31))


def _src() -> SourceRef:
    return SourceRef(
        url="x", doc_title="x",
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc), fetcher="t",
    )


def _empty_rtgs(c: str) -> RtgsCalendar:
    return RtgsCalendar(currency=c, calendar_name=c, operator="x", entries_by_date={}, **WINDOW)


def _empty_exchange(v: str) -> ExchangeCalendar:
    return ExchangeCalendar(venue=v, products=(), entries_by_date={}, library_sourced=False, **WINDOW)


def test_rejects_venue_not_on_pair():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    sgx = _empty_exchange("SGX")
    with pytest.raises(VenueNotListedError):
        calculate_future_dates(
            pair=parse_pair("EUR/USD"),  # not SGX-listed
            venue="SGX",
            contract_month=(2026, 6),
            rtgs_calendars=cals,
            exchange_calendar=sgx,
        )


def test_rejects_neither_contract_month_nor_imm_tenor():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    cme = _empty_exchange("CME")
    with pytest.raises(ValueError):
        calculate_future_dates(
            pair=parse_pair("EUR/USD"),
            venue="CME",
            rtgs_calendars=cals,
            exchange_calendar=cme,
        )


def test_result_dataclass_shape():
    r = FutureResult(
        contract_month=(2026, 6),
        venue="CME",
        last_trade_date=date(2026, 6, 15),
        delivery_date=date(2026, 6, 17),
        last_trade_trace=[],
        delivery_trace=[],
        calendars_used=[],
        warnings=[],
    )
    assert r.last_trade_date < r.delivery_date
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_future.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `fx_holiday_calculator/future.py` skeleton**

```python
"""FX futures date math: last trade date and delivery date.

Delivery date is the 3rd Wednesday of the contract month, rolled
modified-following on the combined exchange + base/quote RTGS set.
Last trade date is anchored to the unrolled 3rd Wednesday and is
2 good business days before it (CME Rule 25102.E and analogous rules
on HKEX / SGX).

Conventions: see docs/conventions.md §11.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.conventions.business_day import (
    AdjustmentStep,
    CalendarSet,
    imm_last_trade_date,
    roll_with_trace,
)
from fx_holiday_calculator.conventions.dates import imm_third_wednesday, next_imm_date
from fx_holiday_calculator.pairs import Pair
from fx_holiday_calculator.tenor import InvalidTenorError, Tenor


class VenueNotListedError(ValueError):
    pass


class InvalidContractMonthError(ValueError):
    pass


@dataclass
class FutureResult:
    contract_month: tuple[int, int]
    venue: str
    last_trade_date: date
    delivery_date: date
    last_trade_trace: list[AdjustmentStep]
    delivery_trace: list[AdjustmentStep]
    calendars_used: list[str]
    warnings: list[str] = field(default_factory=list)


def calculate_future_dates(
    *,
    pair: Pair,
    venue: str,
    contract_month: Optional[tuple[int, int]] = None,
    imm_tenor: Optional[Tenor] = None,
    from_date: Optional[date] = None,
    rtgs_calendars: dict[str, RtgsCalendar],
    exchange_calendar: ExchangeCalendar,
) -> FutureResult:
    if venue not in pair.listed_on:
        raise VenueNotListedError(
            f"{pair.base}/{pair.quote} is not listed on {venue}. "
            f"Listed venues: {pair.listed_on}"
        )
    if contract_month is None and imm_tenor is None:
        raise ValueError("Exactly one of contract_month / imm_tenor must be provided")
    if contract_month is not None and imm_tenor is not None:
        raise ValueError("Provide contract_month OR imm_tenor, not both")

    if imm_tenor is not None:
        if imm_tenor.kind != "IMM":
            raise InvalidTenorError("Futures input only accepts IMM1..IMM4 tenor")
        anchor_date = from_date or date.today()
        imm_date = next_imm_date(anchor_date, imm_tenor.imm_index)
        contract_month = (imm_date.year, imm_date.month)
    assert contract_month is not None  # for type-checker

    today = date.today()
    if (contract_month[0], contract_month[1]) < (today.year, today.month) and from_date is None:
        raise InvalidContractMonthError(
            f"Contract month {contract_month} is in the past."
        )

    # Combined calendar set: venue exchange + base + quote RTGS.
    combined_cs = CalendarSet(
        members={
            venue: exchange_calendar,
            pair.base: rtgs_calendars[pair.base],
            pair.quote: rtgs_calendars[pair.quote],
        }  # type: ignore[dict-item]
    )

    # Delivery: 3rd Wed rolled modified-following on combined set.
    anchor = imm_third_wednesday(*contract_month)
    delivery_date, delivery_trace = roll_with_trace(anchor, combined_cs, "modified_following")

    # Last trade date: 2 good BDs back from unrolled 3rd Wed.
    last_trade_date = imm_last_trade_date(contract_month, combined_cs)
    # LTD is by construction a good BD on combined_cs, so roll_with_trace
    # returns a single accepted step — no need to reach for a private helper.
    _, last_trade_trace = roll_with_trace(last_trade_date, combined_cs, "following")

    calendars_used = [venue]
    calendars_used += [f"{pair.base} ({rtgs_calendars[pair.base].calendar_name})",
                       f"{pair.quote} ({rtgs_calendars[pair.quote].calendar_name})"]

    warnings: list[str] = []
    if last_trade_date < today and from_date is None:
        warnings.append(
            f"Contract {contract_month[0]}-{contract_month[1]:02d} expired on "
            f"{last_trade_date.isoformat()} — this is a historical query."
        )

    return FutureResult(
        contract_month=contract_month,
        venue=venue,
        last_trade_date=last_trade_date,
        delivery_date=delivery_date,
        last_trade_trace=last_trade_trace,
        delivery_trace=delivery_trace,
        calendars_used=calendars_used,
        warnings=warnings,
    )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_future.py -v
```

Expected: the three skeleton tests pass.

- [ ] **Step 5: Commit (user action)**

```bash
git add fx_holiday_calculator/future.py tests/test_future.py
git commit -m "feat(future): scaffold FutureResult and venue/input validation"
```

---

### Task 4.3: Futures contract-month input — clean and holiday cases

**Files:**
- Modify: `tests/test_future.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_future.py`:

```python
def test_future_contract_month_clean_eurusd_cme():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    cme = _empty_exchange("CME")
    r = calculate_future_dates(
        pair=parse_pair("EUR/USD"),
        venue="CME",
        contract_month=(2026, 6),
        rtgs_calendars=cals,
        exchange_calendar=cme,
        from_date=date(2026, 5, 6),  # avoid stale-contract warning
    )
    # 3rd Wed of June 2026 = 2026-06-17. Clean -> delivery same.
    assert r.delivery_date == date(2026, 6, 17)
    # LTD = 2 BD back = 2026-06-15 (Mon).
    assert r.last_trade_date == date(2026, 6, 15)


def test_future_ltd_anchored_to_unrolled_3rd_wed():
    # Make the 3rd Wed itself a CME holiday. Delivery rolls; LTD anchors to
    # unrolled 3rd Wed -> they drift apart by one day.
    cme_hol = HolidayEntry(
        date=date(2026, 6, 17),
        name="CME closed",
        note=None,
        source=_src(),
        source_origin="bundled",
        is_closure=True,
    )
    cme = ExchangeCalendar(
        venue="CME", products=("EURUSD",),
        entries_by_date={date(2026, 6, 17): cme_hol},
        library_sourced=False, **WINDOW,
    )
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    r = calculate_future_dates(
        pair=parse_pair("EUR/USD"),
        venue="CME",
        contract_month=(2026, 6),
        rtgs_calendars=cals,
        exchange_calendar=cme,
        from_date=date(2026, 5, 6),
    )
    # Delivery rolls past 2026-06-17 -> 2026-06-18 (Thu)
    assert r.delivery_date == date(2026, 6, 18)
    # LTD anchored to UNROLLED 2026-06-17. Count back 2 good BDs:
    # 06-16 (Tue, good) -> first; 06-15 (Mon, good) -> second. So LTD = 2026-06-15.
    assert r.last_trade_date == date(2026, 6, 15)
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_future.py -v
```

Expected: all green.

- [ ] **Step 3: Commit (user action)**

```bash
git add tests/test_future.py
git commit -m "test(future): contract-month input; LTD anchored to unrolled 3rd Wed"
```

---

### Task 4.4: Futures IMM-tenor input

**Files:**
- Modify: `tests/test_future.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_future.py`:

```python
def test_future_imm_tenor_maps_to_correct_contract_month():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    cme = _empty_exchange("CME")
    r = calculate_future_dates(
        pair=parse_pair("EUR/USD"),
        venue="CME",
        imm_tenor=parse_tenor("IMM1"),
        from_date=date(2026, 5, 6),  # IMM1 from May 2026 = June 2026
        rtgs_calendars=cals,
        exchange_calendar=cme,
    )
    assert r.contract_month == (2026, 6)
    assert r.delivery_date == date(2026, 6, 17)


def test_future_imm_tenor_rejects_non_imm_tenor():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    cme = _empty_exchange("CME")
    with pytest.raises(InvalidTenorError):
        calculate_future_dates(
            pair=parse_pair("EUR/USD"),
            venue="CME",
            imm_tenor=parse_tenor("3M"),
            from_date=date(2026, 5, 6),
            rtgs_calendars=cals,
            exchange_calendar=cme,
        )
```

Add the missing import at the top of `tests/test_future.py`:

```python
from fx_holiday_calculator.tenor import InvalidTenorError
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_future.py -v
```

Expected: all green.

- [ ] **Step 3: Commit (user action)**

```bash
git add tests/test_future.py
git commit -m "test(future): IMM tenor input maps to correct contract month"
```

---

### Task 4.5: Futures — venues converge & stale-contract warning

**Files:**
- Modify: `tests/test_future.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_future.py`:

```python
@pytest.mark.parametrize("venue", ["CME", "HKEX", "SGX"])
def test_future_all_three_venues_produce_same_dates_when_calendars_match(venue):
    # USD/CNH is listed on all three venues. With identical (empty) calendars,
    # all three produce the same dates.
    cals = {"USD": _empty_rtgs("USD"), "CNH": _empty_rtgs("CNH")}
    ex = _empty_exchange(venue)
    r = calculate_future_dates(
        pair=parse_pair("USD/CNH"),
        venue=venue,
        contract_month=(2026, 6),
        rtgs_calendars=cals,
        exchange_calendar=ex,
        from_date=date(2026, 5, 6),
    )
    assert r.delivery_date == date(2026, 6, 17)
    assert r.last_trade_date == date(2026, 6, 15)


def test_future_stale_contract_warning():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    cme = _empty_exchange("CME")
    # No from_date supplied -> uses today(). Past contract triggers either the
    # warning or InvalidContractMonthError depending on how far in the past
    # the contract month is. Use a contract month from far enough back that
    # InvalidContractMonthError fires.
    with pytest.raises(InvalidContractMonthError):
        calculate_future_dates(
            pair=parse_pair("EUR/USD"),
            venue="CME",
            contract_month=(2020, 6),
            rtgs_calendars=cals,
            exchange_calendar=cme,
        )
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_future.py -v
```

Expected: all green.

- [ ] **Step 3: Commit (user action)**

```bash
git add tests/test_future.py
git commit -m "test(future): venues converge for shared pairs; stale-contract rejection"
```

---

### Task 4.6: Public API + `docs/conventions.md` §11

**Files:**
- Modify: `fx_holiday_calculator/__init__.py`
- Modify: `docs/conventions.md`

- [ ] **Step 1: Re-export futures API**

In `fx_holiday_calculator/__init__.py`, add:

```python
from fx_holiday_calculator.future import (
    FutureResult,
    InvalidContractMonthError,
    VenueNotListedError,
    calculate_future_dates,
)
```

- [ ] **Step 2: Append `docs/conventions.md` §11**

```markdown
## 11. FX Futures — last trade date & delivery date

FX futures are exchange-listed contracts with two characteristic dates:

- **Delivery date** — the 3rd Wednesday of the contract month, rolled
  `modified_following` on the combined exchange + base RTGS + quote RTGS
  calendar set.
- **Last trade date** — 2 good business days before the **unrolled** 3rd
  Wednesday, on the same combined set.

The LTD anchor is the unrolled 3rd Wednesday — not the rolled delivery
date. When 3rd Wed is a holiday and delivery rolls forward, LTD remains
anchored to the original IMM date and does not chain off delivery. This
matches CME Rule 25102.E for EUR/USD futures and analogous HKEX / SGX
rules; the 9:16 a.m. CT time-of-day cut is out of v1.1 scope.

### 11.1 Input modes

- **Contract month** — user supplies `(year, month)` directly.
- **IMM tenor** — user supplies `IMM1..IMM4` plus an optional `from_date`
  (defaults to today). The contract month is resolved via
  `next_imm_date(from_date, imm_index)`.

### 11.2 Validations

- `VenueNotListedError` — pair is not listed on the chosen venue.
- `InvalidContractMonthError` — contract month is in the past relative
  to `from_date` (or today if no `from_date`).
- `InvalidTenorError` — `imm_tenor` is supplied but not an IMM kind.

### 11.3 Warnings

- *Stale contract* — `last_trade_date < today` with `from_date is None`.
  Historical queries are allowed via explicit `from_date`.

### 11.4 Where this lives

- Engine: `fx_holiday_calculator/future.py`
- LTD helper: `fx_holiday_calculator/conventions/business_day.py`
  (`imm_last_trade_date`)
- Tests: `tests/test_future.py`
```

- [ ] **Step 3: Verify import**

```bash
python -c "from fx_holiday_calculator import calculate_future_dates, FutureResult; print('ok')"
```

- [ ] **Step 4: Commit (user action)**

```bash
git add fx_holiday_calculator/__init__.py docs/conventions.md
git commit -m "docs(conventions): document FX futures date math (§11)"
```

---

## Phase 5 — UI restructure

The engine library is now fully wired. Phase 5 re-shells the UI around the new product modules.

### Task 5.1: Rename `tab_swap.py` → `product_spot_swap.py`

**Files:**
- Rename: `fx_holiday_calculator/ui/tab_swap.py` → `fx_holiday_calculator/ui/product_spot_swap.py`
- Modify: `fx_holiday_calculator/ui/app.py` (import path update; superseded in Task 5.6)

- [ ] **Step 1: Rename the file**

```bash
git mv fx_holiday_calculator/ui/tab_swap.py fx_holiday_calculator/ui/product_spot_swap.py
```

- [ ] **Step 2: Update the in-tab subheader**

In `product_spot_swap.py`, replace the `render()` function's first line:

```python
def render() -> None:
    st.subheader("Spot & Swap Date Calculator")
    st.caption(
        "Covers spot, cross-spot, ON/TN/SN, forward outright, standard swap, "
        "and forward-forward swap. All rolling on RTGS calendars; exchange "
        "calendar mode optional for forward legs."
    )
```

- [ ] **Step 3: Update the docstring at the top of the file**

Add at the top, replacing or augmenting any existing module docstring:

```python
"""Spot / Swap product sub-tab.

Renders the existing engine surface (calculate_swap_dates) under a
product-aware label. Covers spot, cross-spot, ON/TN/SN, forward outright,
standard swap, and forward-forward swap — all sharing identical RTGS-only
calendar logic, with optional exchange/both mode for forward legs.
"""
```

- [ ] **Step 4: Update `app.py` import**

In `fx_holiday_calculator/ui/app.py`, replace:

```python
from fx_holiday_calculator.ui import sidebar, tab_about, tab_holidays, tab_swap
```

with:

```python
from fx_holiday_calculator.ui import (
    product_spot_swap,
    sidebar,
    tab_about,
    tab_holidays,
)
```

And inside `main()`:

```python
with t1:
    product_spot_swap.render()
```

This is a transitional state; Task 5.6 wraps it in the parent Calculator tab.

- [ ] **Step 5: Verify the app still imports cleanly**

```bash
python -c "from fx_holiday_calculator.ui import app; print('ok')"
```

Expected: `ok`.

- [ ] **Step 6: Commit (user action)**

```bash
git add fx_holiday_calculator/ui/
git commit -m "refactor(ui): rename tab_swap to product_spot_swap and re-title"
```

---

### Task 5.2: New `tab_calculator.py` parent — hosts 4 product sub-tabs

**Files:**
- Create: `fx_holiday_calculator/ui/tab_calculator.py`

- [ ] **Step 1: Write the parent tab**

Create `fx_holiday_calculator/ui/tab_calculator.py`:

```python
"""Calculator parent tab — hosts the four product sub-tabs.

Sub-tabs are loaded lazily so an exception in one product doesn't kill
the others.
"""

import streamlit as st


def render() -> None:
    st.write("")  # spacing under the top-level tab bar

    # Lazy imports so any one sub-tab's import failure doesn't break the others.
    from fx_holiday_calculator.ui import (
        product_futures,
        product_ndf,
        product_option,
        product_spot_swap,
    )

    sub = st.tabs(["Spot / Swap", "NDF", "Option", "Futures"])
    with sub[0]:
        product_spot_swap.render()
    with sub[1]:
        product_ndf.render()
    with sub[2]:
        product_option.render()
    with sub[3]:
        product_futures.render()
```

- [ ] **Step 2: Verify imports clean**

```bash
python -c "from fx_holiday_calculator.ui import tab_calculator; print('ok')"
```

Expected: `ImportError: No module named ...product_ndf` — that's fine, fixed by 5.3–5.5. For now, defer the assertion until those modules exist.

- [ ] **Step 3: Commit (user action)**

```bash
git add fx_holiday_calculator/ui/tab_calculator.py
git commit -m "feat(ui): add Calculator parent tab hosting four product sub-tabs"
```

---

### Task 5.3: NDF product sub-tab — `product_ndf.py`

**Files:**
- Create: `fx_holiday_calculator/ui/product_ndf.py`

- [ ] **Step 1: Write the NDF UI**

Create `fx_holiday_calculator/ui/product_ndf.py`:

```python
"""NDF product sub-tab — inputs for USD/CNY, USD/KRW, USD/TWD with fixing dates."""

from datetime import date
from pathlib import Path

import streamlit as st

from fx_holiday_calculator.calendars.fixing import FixingCalendar
from fx_holiday_calculator.calendars.loader import (
    load_fixing_calendar,
    load_rtgs_calendar,
)
from fx_holiday_calculator.calendars.types import CalendarRangeError
from fx_holiday_calculator.ndf import (
    InvalidBrokenDateError,
    InvalidNdfPairError,
    InvalidTradeDateError,
    NdfResult,
    calculate_ndf_dates,
)
from fx_holiday_calculator.pairs import list_supported_pairs, parse_pair
from fx_holiday_calculator.tenor import InvalidTenorError, parse_tenor

BUNDLED = Path(__file__).resolve().parents[2] / "data"
CACHE = Path.home() / ".fx_holiday_calculator" / "cache"


def _ndf_pair_codes() -> list[str]:
    return [
        f"{p.base}/{p.quote}"
        for p in list_supported_pairs()
        if p.ndf
    ]


def _load_fixing(currency: str) -> FixingCalendar:
    return load_fixing_calendar(
        currency,
        root=BUNDLED / "fx_fixing",
        cache_root=CACHE / "fx_fixing",
    )


def _render_trace(steps, label: str) -> None:
    if not steps:
        st.write(f"_{label}: no adjustment steps_")
        return
    with st.expander(f"{label} — {len(steps)} candidate(s)", expanded=True):
        for s in steps:
            cols = st.columns([1.4, 0.5, 4, 1])
            cols[0].write(s.candidate_date.isoformat())
            cols[1].write(s.weekday)
            cells = []
            for cal_label, status in s.statuses.items():
                if status.is_good:
                    cells.append(f"{cal_label}: ✓")
                else:
                    cells.append(f"{cal_label}: ✘ {status.holiday_name}")
            cols[2].write("  ·  ".join(cells))
            cols[3].write(s.decision)
            for cal_label, status in s.statuses.items():
                if status.source is not None:
                    st.caption(
                        f"{cal_label}: [{status.source.doc_title}]({status.source.url}) · "
                        f"fetched {status.source.fetched_at.isoformat()} · "
                        f"{status.source_origin}"
                    )


def render() -> None:
    st.subheader("NDF Date Calculator")
    st.caption(
        "Non-deliverable forwards: USD settlement, fixing on primary-source "
        "calendar of the non-deliverable currency (CFETS / KFTC / Taipei Forex)."
    )

    pair_codes = _ndf_pair_codes()
    if not pair_codes:
        st.warning("No NDF pairs available — check pair-table configuration.")
        return

    col1, col2 = st.columns(2)
    pair_code = col1.selectbox("Currency pair", pair_codes, key="ndf_pair")
    trade_date = col2.date_input("Trade date", value=date.today(), key="ndf_trade_date")
    pair = parse_pair(pair_code)

    input_mode = st.radio(
        "Input mode",
        ["Tenor", "Maturity date"],
        horizontal=True,
        key="ndf_input_mode",
    )

    tenor_str: str | None = None
    target_date: date | None = None
    if input_mode == "Tenor":
        tenor_str = st.text_input(
            "Tenor (forward only — PERIOD / IMM / BROKEN, e.g. 3M, IMM1, 2026-08-15)",
            value="3M",
            key="ndf_tenor",
        )
    else:
        target_date = st.date_input(
            "Target settlement date",
            value=date(date.today().year, date.today().month, 15),
            key="ndf_target",
        )

    # Load USD RTGS + fixing calendar.
    try:
        usd = load_rtgs_calendar(
            "USD",
            root=BUNDLED / "fx_rtgs",
            cache_root=CACHE / "fx_rtgs",
        )
    except FileNotFoundError as exc:
        st.error(f"USD RTGS calendar missing: {exc}")
        return

    try:
        fixing = _load_fixing(pair.fixing_currency)  # type: ignore[arg-type]
    except FileNotFoundError as exc:
        st.error(
            f"Fixing calendar for {pair.fixing_currency} missing: {exc}. "
            f"Refresh via the sidebar."
        )
        return

    st.caption(
        f"Calendars to be used: RTGS: USD ({usd.calendar_name}) | "
        f"Fixing: {fixing.currency} ({fixing.calendar_name})"
    )

    if st.button("Calculate", key="ndf_calc"):
        try:
            if input_mode == "Tenor":
                tenor = parse_tenor(tenor_str)  # type: ignore[arg-type]
                result = calculate_ndf_dates(
                    trade_date=trade_date,
                    pair=pair,
                    tenor=tenor,
                    rtgs_calendars={"USD": usd},
                    fixing_calendar=fixing,
                )
            else:
                result = calculate_ndf_dates(
                    trade_date=trade_date,
                    pair=pair,
                    target_settlement=target_date,
                    rtgs_calendars={"USD": usd},
                    fixing_calendar=fixing,
                )
        except (
            InvalidNdfPairError,
            InvalidTenorError,
            InvalidTradeDateError,
            InvalidBrokenDateError,
        ) as exc:
            st.error(f"Invalid input: {exc}")
            return
        except CalendarRangeError as exc:
            st.error(
                f"Calculation lands outside bundled calendar window: {exc} "
                "Refresh the calendar data or pick an earlier trade date."
            )
            return

        if result.warnings:
            st.warning("\n\n".join(f"• {w}" for w in result.warnings))

        st.markdown("### Result")
        st.write(f"**Trade date:**       {result.trade_date} ({result.trade_date.strftime('%a')})")
        st.write(f"**Spot date:**        {result.spot_date} ({result.spot_date.strftime('%a')})")
        st.write(f"**Fixing date:**      {result.fixing_date} ({result.fixing_date.strftime('%a')})")
        st.write(f"**Settlement date:**  {result.settlement_date} ({result.settlement_date.strftime('%a')})")

        st.markdown("### Adjustment trace")
        _render_trace(result.spot_trace, "Spot offset")
        _render_trace(result.settlement_trace, "Settlement")
        _render_trace(result.fixing_trace, "Fixing")
```

- [ ] **Step 2: Verify import (will fail until other product modules exist; we'll defer verification to Task 5.6)**

For now, just `python -c "from fx_holiday_calculator.ui import product_ndf; print('ok')"`. If only product_ndf is the target, this should succeed in isolation.

- [ ] **Step 3: Commit (user action)**

```bash
git add fx_holiday_calculator/ui/product_ndf.py
git commit -m "feat(ui): NDF product sub-tab"
```

---

### Task 5.4: Option product sub-tab — `product_option.py`

**Files:**
- Create: `fx_holiday_calculator/ui/product_option.py`

- [ ] **Step 1: Write the Option UI**

Create `fx_holiday_calculator/ui/product_option.py`:

```python
"""Option product sub-tab — OTC and Listed FX options."""

from datetime import date
from pathlib import Path

import streamlit as st

from fx_holiday_calculator.calendars.loader import (
    load_exchange_calendar,
    load_rtgs_calendar,
)
from fx_holiday_calculator.calendars.types import CalendarRangeError
from fx_holiday_calculator.option import (
    InvalidOptionStyleError,
    ListedOptionVenueRequiredError,
    calculate_option_dates,
)
from fx_holiday_calculator.pairs import list_supported_pairs, parse_pair
from fx_holiday_calculator.tenor import InvalidTenorError, parse_tenor

BUNDLED = Path(__file__).resolve().parents[2] / "data"
CACHE = Path.home() / ".fx_holiday_calculator" / "cache"

AVAILABLE_RTGS = {"EUR", "USD", "GBP", "JPY"}


def _available_pairs() -> list[str]:
    return [
        f"{p.base}/{p.quote}"
        for p in list_supported_pairs()
        if not p.ndf and p.base in AVAILABLE_RTGS and p.quote in AVAILABLE_RTGS
    ]


def _available_exchange_venues() -> set[str]:
    bundled = BUNDLED / "fx_exchange"
    if not bundled.exists():
        return set()
    return {p.stem for p in bundled.glob("*.json") if not p.name.startswith("_")}


def _render_trace(steps, label: str) -> None:
    # Identical helper as in product_ndf — duplicated for module independence.
    if not steps:
        st.write(f"_{label}: no adjustment steps_")
        return
    with st.expander(f"{label} — {len(steps)} candidate(s)", expanded=True):
        for s in steps:
            cols = st.columns([1.4, 0.5, 4, 1])
            cols[0].write(s.candidate_date.isoformat())
            cols[1].write(s.weekday)
            cells = []
            for cal_label, status in s.statuses.items():
                if status.is_good:
                    cells.append(f"{cal_label}: ✓")
                else:
                    cells.append(f"{cal_label}: ✘ {status.holiday_name}")
            cols[2].write("  ·  ".join(cells))
            cols[3].write(s.decision)
            for cal_label, status in s.statuses.items():
                if status.source is not None:
                    st.caption(
                        f"{cal_label}: [{status.source.doc_title}]({status.source.url}) · "
                        f"fetched {status.source.fetched_at.isoformat()} · "
                        f"{status.source_origin}"
                    )


def render() -> None:
    st.subheader("FX Option Date Calculator")
    st.caption(
        "Expiry + delivery dates for vanilla FX options. "
        "OTC = expiry rolls on RTGS; Listed = expiry rolls on the venue's exchange calendar."
    )

    pairs = _available_pairs()
    if not pairs:
        st.warning("No supported pairs available.")
        return

    col1, col2, col3 = st.columns(3)
    pair_code = col1.selectbox("Currency pair", pairs, key="opt_pair")
    trade_date = col2.date_input("Trade date", value=date.today(), key="opt_trade_date")
    tenor_str = col3.text_input(
        "Tenor (forward only — e.g. 1M, 3M, IMM1, 2026-08-15)",
        value="1M",
        key="opt_tenor",
    )

    pair = parse_pair(pair_code)
    style = st.radio("Style", ["OTC", "Listed"], horizontal=True, key="opt_style")
    style_key = "OTC" if style == "OTC" else "LISTED"

    has_usd = "USD" in {pair.base, pair.quote}
    ref_options = ["none", "USD", "EUR"]
    default_ref = "none" if has_usd else "USD"
    ref = st.radio(
        "Reference currency (OTC only — ignored for Listed)",
        ref_options,
        index=ref_options.index(default_ref),
        horizontal=True,
        key="opt_ref",
    )

    venue: str | None = None
    if style_key == "LISTED":
        available = _available_exchange_venues()
        valid_for_pair = [v for v in pair.listed_on if v in available]
        if not valid_for_pair:
            st.error(
                f"{pair_code} is not listed on any venue with bundled exchange data. "
                f"Switch to OTC."
            )
            return
        venue = st.selectbox("Venue", valid_for_pair, key="opt_venue")

    # Load RTGS calendars.
    needed = {pair.base, pair.quote}
    if ref != "none":
        needed.add(ref)
    try:
        cals = {
            c: load_rtgs_calendar(c, root=BUNDLED / "fx_rtgs", cache_root=CACHE / "fx_rtgs")
            for c in sorted(needed)
        }
    except FileNotFoundError as exc:
        st.error(f"RTGS calendar missing: {exc}")
        return

    exch_cal = None
    if style_key == "LISTED":
        try:
            exch_cal = load_exchange_calendar(
                venue,  # type: ignore[arg-type]
                root=BUNDLED / "fx_exchange",
                cache_root=CACHE / "fx_exchange",
            )
        except FileNotFoundError as exc:
            st.error(f"Exchange calendar missing: {exc}")
            return
        if exch_cal.library_sourced:
            st.warning(
                f"Exchange calendar caveat — {venue} is library-sourced (equity session). "
                "FX-options holidays may differ. See docs/data-sources.md."
            )

    cal_caption = "RTGS: " + " · ".join(f"{c} ({cals[c].calendar_name})" for c in sorted(needed))
    if exch_cal:
        cal_caption += f" | Exchange: {venue}"
    st.caption("Calendars to be used: " + cal_caption)

    if st.button("Calculate", key="opt_calc"):
        try:
            tenor = parse_tenor(tenor_str)
            result = calculate_option_dates(
                trade_date=trade_date,
                pair=pair,
                tenor=tenor,
                style=style_key,
                ref_currency=ref,  # type: ignore[arg-type]
                rtgs_calendars=cals,
                exchange_calendar=exch_cal,
                venue=venue,
            )
        except (
            InvalidTenorError,
            InvalidOptionStyleError,
            ListedOptionVenueRequiredError,
        ) as exc:
            st.error(f"Invalid input: {exc}")
            return
        except CalendarRangeError as exc:
            st.error(f"Calculation lands outside bundled window: {exc}")
            return

        if result.warnings:
            st.warning("\n\n".join(f"• {w}" for w in result.warnings))

        st.markdown("### Result")
        st.write(f"**Trade date:**     {result.trade_date} ({result.trade_date.strftime('%a')})")
        st.write(f"**Spot date:**      {result.spot_date} ({result.spot_date.strftime('%a')})")
        st.write(f"**Expiry date:**    {result.expiry_date} ({result.expiry_date.strftime('%a')})")
        st.write(f"**Delivery date:**  {result.delivery_date} ({result.delivery_date.strftime('%a')})")

        st.markdown("### Adjustment trace")
        _render_trace(result.expiry_trace, "Expiry")
        _render_trace(result.delivery_trace, "Delivery")
```

- [ ] **Step 2: Commit (user action)**

```bash
git add fx_holiday_calculator/ui/product_option.py
git commit -m "feat(ui): Option product sub-tab"
```

---

### Task 5.5: Futures product sub-tab — `product_futures.py`

**Files:**
- Create: `fx_holiday_calculator/ui/product_futures.py`

- [ ] **Step 1: Write the Futures UI**

Create `fx_holiday_calculator/ui/product_futures.py`:

```python
"""Futures product sub-tab — CME / HKEX / SGX FX futures."""

from datetime import date
from pathlib import Path

import streamlit as st

from fx_holiday_calculator.calendars.loader import (
    load_exchange_calendar,
    load_rtgs_calendar,
)
from fx_holiday_calculator.calendars.types import CalendarRangeError
from fx_holiday_calculator.future import (
    InvalidContractMonthError,
    VenueNotListedError,
    calculate_future_dates,
)
from fx_holiday_calculator.pairs import list_supported_pairs, parse_pair
from fx_holiday_calculator.tenor import InvalidTenorError, parse_tenor

BUNDLED = Path(__file__).resolve().parents[2] / "data"
CACHE = Path.home() / ".fx_holiday_calculator" / "cache"


def _listed_pairs() -> list[str]:
    return [
        f"{p.base}/{p.quote}"
        for p in list_supported_pairs()
        if p.listed_on
    ]


def _available_exchange_venues() -> set[str]:
    bundled = BUNDLED / "fx_exchange"
    if not bundled.exists():
        return set()
    return {p.stem for p in bundled.glob("*.json") if not p.name.startswith("_")}


def _render_trace(steps, label: str) -> None:
    if not steps:
        st.write(f"_{label}: no adjustment steps_")
        return
    with st.expander(f"{label} — {len(steps)} candidate(s)", expanded=True):
        for s in steps:
            cols = st.columns([1.4, 0.5, 4, 1])
            cols[0].write(s.candidate_date.isoformat())
            cols[1].write(s.weekday)
            cells = []
            for cal_label, status in s.statuses.items():
                if status.is_good:
                    cells.append(f"{cal_label}: ✓")
                else:
                    cells.append(f"{cal_label}: ✘ {status.holiday_name}")
            cols[2].write("  ·  ".join(cells))
            cols[3].write(s.decision)
            for cal_label, status in s.statuses.items():
                if status.source is not None:
                    st.caption(
                        f"{cal_label}: [{status.source.doc_title}]({status.source.url}) · "
                        f"fetched {status.source.fetched_at.isoformat()} · "
                        f"{status.source_origin}"
                    )


def render() -> None:
    st.subheader("FX Futures Date Calculator")
    st.caption(
        "Last trade date + delivery date for CME / HKEX / SGX FX futures. "
        "LTD is anchored to the unrolled 3rd Wednesday of the contract month."
    )

    listed = _listed_pairs()
    if not listed:
        st.warning("No listed pairs available.")
        return

    col1, col2 = st.columns(2)
    pair_code = col1.selectbox("Currency pair", listed, key="fut_pair")
    pair = parse_pair(pair_code)
    available_venues = _available_exchange_venues()
    valid_venues = [v for v in pair.listed_on if v in available_venues]
    if not valid_venues:
        st.error(
            f"{pair_code} has no bundled exchange calendar. "
            f"Listed on {pair.listed_on}, but none bundled."
        )
        return
    venue = col2.selectbox("Venue", valid_venues, key="fut_venue")

    input_mode = st.radio(
        "Input mode",
        ["Contract month", "IMM tenor"],
        horizontal=True,
        key="fut_input_mode",
    )

    contract_month: tuple[int, int] | None = None
    imm_tenor_str: str | None = None
    from_date: date | None = None
    if input_mode == "Contract month":
        today = date.today()
        c1, c2 = st.columns(2)
        year = c1.number_input(
            "Year", min_value=today.year, max_value=today.year + 5,
            value=today.year, step=1, key="fut_year",
        )
        month_name = c2.selectbox(
            "Month",
            ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
            index=today.month - 1,
            key="fut_month",
        )
        month_idx = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"].index(month_name) + 1
        contract_month = (int(year), int(month_idx))
    else:
        c1, c2 = st.columns(2)
        imm_tenor_str = c1.selectbox(
            "IMM tenor",
            ["IMM1", "IMM2", "IMM3", "IMM4"],
            key="fut_imm_tenor",
        )
        from_date = c2.date_input(
            "Reference date", value=date.today(), key="fut_from_date"
        )

    # Load RTGS + exchange calendars.
    needed = {pair.base, pair.quote}
    try:
        cals = {
            c: load_rtgs_calendar(c, root=BUNDLED / "fx_rtgs", cache_root=CACHE / "fx_rtgs")
            for c in sorted(needed)
        }
    except FileNotFoundError as exc:
        st.error(f"RTGS calendar missing: {exc}")
        return
    try:
        exch_cal = load_exchange_calendar(
            venue, root=BUNDLED / "fx_exchange", cache_root=CACHE / "fx_exchange"
        )
    except FileNotFoundError as exc:
        st.error(f"Exchange calendar missing: {exc}")
        return
    if exch_cal.library_sourced:
        st.warning(
            f"Exchange calendar caveat — {venue} is library-sourced (equity session). "
            "FX-futures holidays may differ. See docs/data-sources.md."
        )

    cal_caption = (
        f"Exchange: {venue} | RTGS: "
        + " · ".join(f"{c} ({cals[c].calendar_name})" for c in sorted(needed))
    )
    st.caption("Calendars to be used: " + cal_caption)

    if st.button("Calculate", key="fut_calc"):
        try:
            if input_mode == "Contract month":
                result = calculate_future_dates(
                    pair=pair,
                    venue=venue,
                    contract_month=contract_month,
                    rtgs_calendars=cals,
                    exchange_calendar=exch_cal,
                )
            else:
                result = calculate_future_dates(
                    pair=pair,
                    venue=venue,
                    imm_tenor=parse_tenor(imm_tenor_str),  # type: ignore[arg-type]
                    from_date=from_date,
                    rtgs_calendars=cals,
                    exchange_calendar=exch_cal,
                )
        except (
            VenueNotListedError,
            InvalidContractMonthError,
            InvalidTenorError,
        ) as exc:
            st.error(f"Invalid input: {exc}")
            return
        except CalendarRangeError as exc:
            st.error(f"Calculation lands outside bundled window: {exc}")
            return

        if result.warnings:
            st.warning("\n\n".join(f"• {w}" for w in result.warnings))

        st.markdown("### Result")
        cm = result.contract_month
        st.write(f"**Contract:**         {cm[0]}-{cm[1]:02d} ({venue})")
        st.write(f"**Last trade date:**  {result.last_trade_date} ({result.last_trade_date.strftime('%a')})")
        st.write(f"**Delivery date:**    {result.delivery_date} ({result.delivery_date.strftime('%a')})")

        st.markdown("### Adjustment trace")
        _render_trace(result.last_trade_trace, "Last trade date")
        _render_trace(result.delivery_trace, "Delivery date")
```

- [ ] **Step 2: Commit (user action)**

```bash
git add fx_holiday_calculator/ui/product_futures.py
git commit -m "feat(ui): Futures product sub-tab"
```

---

### Task 5.6: Update `app.py` to use nested Calculator parent

**Files:**
- Modify: `fx_holiday_calculator/ui/app.py`

- [ ] **Step 1: Rewrite `app.py`**

Replace the entire contents of `fx_holiday_calculator/ui/app.py`:

```python
import streamlit as st


def main() -> None:
    st.set_page_config(page_title="FX Holiday Calculator", layout="wide")
    st.title("FX Holiday Calculator")
    st.caption("Sources cited per holiday")

    # Lazy imports so any one tab's import failure doesn't kill the others.
    from fx_holiday_calculator.ui import sidebar, tab_about, tab_calculator, tab_holidays

    sidebar.render()
    t1, t2, t3 = st.tabs(
        [
            "Calculator",
            "Holiday Calendar",
            "About / Sources",
        ]
    )
    with t1:
        tab_calculator.render()
    with t2:
        tab_holidays.render()
    with t3:
        tab_about.render()
```

- [ ] **Step 2: Verify the full app imports cleanly**

```bash
python -c "from fx_holiday_calculator.ui import app; app  # touch attr"
python -c "from fx_holiday_calculator.ui import tab_calculator, product_spot_swap, product_ndf, product_option, product_futures; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Smoke-test the UI**

```bash
streamlit run run_ui.py --server.headless true --server.port 0 &
sleep 5
pkill -f streamlit
```

Expected: no traceback from the Streamlit process during the 5-second startup window. (For a proper UI test, the user should open the app in a browser and walk through the four sub-tabs; the headless smoke test only catches import-time errors.)

- [ ] **Step 4: Commit (user action)**

```bash
git add fx_holiday_calculator/ui/app.py
git commit -m "feat(ui): top-level tabs become Calculator | Holidays | About"
```

---

### Task 5.7: Update `tab_about.py` with new products and sources

**Files:**
- Modify: `fx_holiday_calculator/ui/tab_about.py`

- [ ] **Step 1: Read the current content of `tab_about.py`**

Open the file and identify its product list and sources list sections.

- [ ] **Step 2: Update the product-list copy**

Find the section that lists supported products (likely near the top of `render()`) and replace with:

```python
st.markdown(
    "**Products supported (v1.1):**\n"
    "- Spot / Swap (covers spot, cross-spot, ON/TN/SN, forward outright, "
    "standard swap, forward-forward swap)\n"
    "- NDF (USD/CNY, USD/KRW, USD/TWD — primary-source fixing)\n"
    "- FX Option (OTC and Listed)\n"
    "- FX Futures (CME / HKEX / SGX)"
)
```

- [ ] **Step 3: Append the new fixing sources to the sources table**

Add a section after the existing RTGS / Exchange listings:

```python
st.markdown(
    "**Fixing calendars (NDF):**\n"
    "- **CNY** — CFETS / PBoC ([chinamoney.com.cn](https://www.chinamoney.com.cn/english/svcrmm/))\n"
    "- **KRW** — KFTC ([kftc.or.kr](https://www.kftc.or.kr/en/))\n"
    "- **TWD** — Taipei Forex Inc. ([taifex.com.tw](https://www.taifex.com.tw/))"
)
```

(Exact URLs may need adjustment; cross-reference `docs/data-sources.md` after the engineer has confirmed live URLs in Task 1.6.)

- [ ] **Step 4: Commit (user action)**

```bash
git add fx_holiday_calculator/ui/tab_about.py
git commit -m "docs(ui): About tab lists v1.1 products and fixing sources"
```

---

## Verification — end-to-end sanity sweep

After all six phases complete, run a single end-to-end verification.

- [ ] **Step 1: Full test suite green**

```bash
pytest -v
```

Expected: zero failures. If the data-integrity test parametrises by glob, confirm the three new fixing files are present and pass.

- [ ] **Step 2: Linting clean**

```bash
flake8 fx_holiday_calculator/ tests/ scripts/
black --check fx_holiday_calculator/ tests/ scripts/
isort --check-only fx_holiday_calculator/ tests/ scripts/
```

Expected: no diffs.

- [ ] **Step 3: Manual UI smoke test**

```bash
streamlit run run_ui.py
```

Open the browser at the URL shown. Walk through each sub-tab:

- **Spot / Swap**: pick EUR/USD, trade date today, tenor 3M, calc → spot + far date with trace.
- **NDF**: pick USD/CNY, trade date today, tenor 3M, calc → spot + settlement + fixing dates with trace.
- **Option (OTC)**: pick EUR/USD, tenor 1M, OTC, calc → expiry + delivery.
- **Option (Listed)**: pick EUR/USD, tenor 1M, Listed → CME, calc → expiry + delivery.
- **Futures (Contract month)**: pick EUR/USD, CME, June 2026, calc → LTD + delivery.
- **Futures (IMM tenor)**: pick EUR/USD, CME, IMM1 from today, calc → LTD + delivery.

For each, confirm the source captions render under the trace expander with clickable URLs.

- [ ] **Step 4: User reviews everything**

Per `CLAUDE.md`, all commits are user-driven. The user reviews each committed change and the final running UI before declaring v1.1 complete.

---

## Spec coverage map

| Spec section | Covered by tasks |
|---|---|
| §3.1 — Tab structure | 5.6, 5.2 |
| §3.2 — Per-product UI surface | 5.1, 5.3, 5.4, 5.5 |
| §3.3 — UI file layout | 5.1, 5.2, 5.3, 5.4, 5.5 |
| §4 — Engine modules | 2.1, 3.1, 4.2 |
| §4.1 — `ndf.py` API | 2.1, 2.2, 2.3, 2.4 |
| §4.2 — `option.py` API | 3.1, 3.2, 3.3, 3.4 |
| §4.3 — `future.py` API | 4.2, 4.3, 4.4, 4.5 |
| §5.1 — Fixing-calendar file layout | 1.6 |
| §5.2 — Fixing JSON schema | 1.3, 1.4, 1.5 |
| §5.3 — Fixing loader | 1.2 |
| §5.4 — Fixing fetchers | 1.3, 1.4, 1.5 |
| §5.5 — Pair table additions | 0.1, 0.2 |
| §5.6 — Refresh integration | 1.7, 1.9 |
| §6.1–§6.4 — Conventions | 2.5, 3.5, 4.6 |
| §7.1 — Provenance contract extension | 1.8 |
| §7.2 — Trace rendering | 5.3, 5.4, 5.5 |
| §7.3 — Calendars-used caption | 5.3, 5.4, 5.5 |
| §7.4 — Missing-calendar UX | 5.3, 5.4, 5.5 |
| §8 — Errors & warnings | 2.1, 2.4, 3.1, 3.4, 4.2, 4.5 |
| §9 — Library tripwire extension | 1.10 |
| §10 — Tests | every TDD task |
| §11 — Phasing | matches plan structure |
