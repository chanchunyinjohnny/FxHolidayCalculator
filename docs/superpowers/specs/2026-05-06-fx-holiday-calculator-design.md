# FX Holiday Calculator — Design

**Date:** 2026-05-06
**Author:** Chan Chun Yin Johnny
**Status:** Approved (brainstorming complete; pending implementation plan)
**License (project):** MIT

---

## 1. Purpose

An open-source tool to **double-check** holiday-driven date math used by an FX desk:

- **FX swap dates** — given a trade date, currency pair, tenor(s), and reference currency, compute near and far-leg dates with a fully cited adjustment trace. Supports:
  - Standard swap (one tenor; near leg defaults from tenor kind — e.g. ON/TN/SN, or near = spot for forwards).
  - **Forward-forward swap (FFS)**: both legs are forwards; user supplies two tenors (e.g. 1M near, 3M far) or two broken dates.
  - Single-leg trades: SPOT, FX forward outright (use far_tenor only), NDF.
- **Holiday calendar** — given a currency pair, reference currency, calendar mode, and date range, list every relevant holiday with its source URL.

Used as a verification tool against in-house systems, so the **provenance of every holiday must be inspectable**. There are no unsourced dates: every holiday returned by the engine is paired with the URL of the official document it was sourced from and the timestamp it was fetched at.

National (public) holidays are surfaced **for reference only** and are visually distinguished. They never drive any calculation.

## 2. Goals

1. Compute FX swap near/far dates for OTC FX spot, forward outright, **standard swap**, **forward-forward swap**, and NDF, plus FX-listed-venue (futures) delivery dates, using only authoritative settlement/exchange calendars.
2. Display per-pair holidays in a date range, with the user choosing FX-only, Exchange-only, or both.
3. Make every holiday traceable to a primary-source document URL plus a fetch timestamp, in the UI.
4. Allow on-demand manual refresh from upstream sources, in addition to a scheduled refresh.
5. Stay maintainable: one fetcher per source, deterministic where possible, with a tripwire against `python-holidays` to catch drift.

## 3. Non-goals (explicit)

- **Pricing or P&L.** This tool only produces dates and holiday rows.
- **National (public) holidays as authoritative input.** They are reference-only.
- **CLI in v1.** Streamlit UI is the only entrypoint; the package remains importable as a library.
- **BYOD (user-supplied holiday overrides) in v1.** The loader is designed to support it; no surface in v1.
- **Currencies beyond R-Mid in v1.** Designed to expand cheaply later.
- **Half-day or session-time data in v1.** Holidays are full-day. Time-of-day fields are not in the v1 schema.

## 4. Scope (v1)

**RTGS currencies (R-Mid, 10):** USD, EUR, GBP, JPY, HKD, CNH, CHF, CAD, AUD, SGD.

**FX-listed venues (V-Min, 3):** CME (FX futures), HKEX (USD/CNH, HKD/CNY, EUR/CNH, JPY/CNH, USD/HKD, etc.), SGX (USD/CNH, USD/INR, KRW/USD, etc.).

**Reference currency choices:** `none`, `USD`, `EUR`, `HKD`, `CNH`.

**Tenor inputs (T-Flex):** `ON`, `TN`, `SN`, `SPOT`, `nD`, `nW`, `nM`, `nY`, `IMM1..IMM4`, plus a broken-date target (raw `YYYY-MM-DD`).

## 5. Key conventions

- **Spot offset (C1):** `T+1` for USD/CAD; `T+2` for all other in-scope pairs.
- **Cross rule (C2):** the spot date must be a good business day in **both leg currencies plus the reference currency** (when reference ≠ `none`). When reference equals one of the legs it is deduped.
- **USD-as-implicit-cross (C3):** when reference = `none` for a non-USD pair, the engine does **not** silently apply USD as a third constraint. The UI's default reference for non-USD pairs is `USD`, with a note explaining why; the user can override to `none`.
- **End-of-month (C4):** if the spot date is the last business day of its month, the far leg rolls to the last business day of the target month.
- **Modified following (C5):** default business-day adjustment. Roll forward; if forward crosses a month boundary, roll back instead.

## 6. Project layout

Mirrors `OpenFigiClient` and `FxFixParser` (Python 3.10/3.11, constrained-corporate env restrictions).

```
FxHolidayCalculator/
├── pyproject.toml
├── README.md
├── CLAUDE.md
├── LICENSE                          # MIT, Chan Chun Yin Johnny
├── pack.sh
├── run_ui.py                        # `streamlit run run_ui.py`
├── .github/
│   ├── FUNDING.yml
│   └── workflows/
│       ├── tests.yml
│       └── refresh-holidays.yml
├── .gitignore                       # excludes proprietary/, dist/, caches
├── proprietary/                     # gitignored, dev-only reference
├── fx_holiday_calculator/
│   ├── __init__.py                  # public API
│   ├── tenor.py
│   ├── pairs.py
│   ├── swap.py
│   ├── holidays_view.py
│   ├── refresh.py                   # `python -m fx_holiday_calculator.refresh`
│   ├── calendars/
│   │   ├── loader.py
│   │   ├── rtgs.py
│   │   ├── exchange.py
│   │   ├── national.py              # python-holidays-backed
│   │   └── types.py                 # HolidayEntry, CalendarStatus, …
│   ├── conventions/
│   │   ├── spot_offset.py
│   │   ├── business_day.py          # good-BD + roll modes + EOM
│   │   └── cross.py                 # calendar-set union, venue resolution
│   └── ui/
│       ├── app.py
│       ├── sidebar.py
│       ├── tab_swap.py
│       ├── tab_holidays.py
│       └── tab_about.py
├── data/                            # bundled holiday JSON — source of truth
│   ├── fx_rtgs/
│   │   ├── USD.json  EUR.json  GBP.json  JPY.json  HKD.json
│   │   ├── CNH.json  CHF.json  CAD.json  AUD.json  SGD.json
│   │   └── _raw/                    # sidecar upstream documents
│   └── fx_exchange/
│       ├── CME.json  HKEX.json  SGX.json
│       └── _raw/
├── scripts/
│   └── sources/                     # one fetcher per source
│       ├── ecb_target2.py           # deterministic rule, no scrape
│       ├── federal_reserve.py
│       ├── boe_chaps.py             # gov.uk JSON API
│       ├── boj.py
│       ├── hkma_chats_hkd.py
│       ├── hkma_chats_cnh.py
│       ├── snb_sic.py
│       ├── payments_canada_lynx.py
│       ├── rba_rits.py
│       ├── mas_meps.py
│       ├── cme_fx.py
│       ├── hkex_fx.py
│       └── sgx_fx.py
└── tests/
    ├── test_tenor.py
    ├── test_conventions.py
    ├── test_swap.py
    ├── test_holidays_view.py
    ├── test_calendars.py
    ├── test_data_integrity.py
    ├── test_fetchers.py
    └── fixtures/
        └── sources/                 # recorded upstream documents per fetcher
```

## 7. Data architecture

### 7.1 JSON schema

One file per RTGS currency (`data/fx_rtgs/<CCY>.json`) and one per FX-listed venue (`data/fx_exchange/<VENUE>.json`).

```json
{
  "schema_version": 1,
  "currency": "USD",
  "calendar_kind": "RTGS",
  "calendar_name": "Fedwire",
  "operator": "Federal Reserve System",
  "default_source": {
    "url": "https://www.federalreserve.gov/aboutthefed/k8.htm",
    "doc_title": "Federal Reserve Bank Holiday Schedule",
    "fetched_at": "2026-04-15T03:00:00Z",
    "fetcher": "scripts/sources/federal_reserve.py@v1"
  },
  "holidays": [
    {
      "date": "2026-01-01",
      "name": "New Year's Day",
      "source": null,
      "note": null
    },
    {
      "date": "2026-07-03",
      "name": "Independence Day (observed)",
      "source": null,
      "note": "Jul 4 falls on Saturday; preceding Friday observed"
    }
  ]
}
```

Exchange files have the same shape with `calendar_kind: "EXCHANGE"`, `venue`, and a `products` list of FX contracts the file applies to.

**Rules:**
- Every holiday must resolve to a non-null `source` — either its own override or the file's `default_source`. The integrity test fails CI otherwise.
- Per-entry `source` overrides exist for one-off events (typhoon T8 closures, ad-hoc closures) where one date came from a different document than the rest.
- Sidecar raw documents (`data/fx_rtgs/_raw/USD.html`, etc.) are committed alongside, so `git diff` can show exactly what each upstream said at fetch time.

### 7.2 Sources table (summary)

The full per-source registry — including upstream URLs, parser strategies, schema mappings, known quirks, and cross-check tripwire rules — lives in **`docs/data-sources.md`**, which is the project's authoritative source-of-truth document for "where does our data come from." That document is maintained alongside this spec; treat it as load-bearing.

Summary of in-scope sources for v1:

| Kind | Code | Operator / Calendar | Format |
|---|---|---|---|
| RTGS | USD | Federal Reserve (Fedwire) | HTML |
| RTGS | EUR | Eurosystem (TARGET2) | Deterministic rule |
| RTGS | GBP | Bank of England (CHAPS) | gov.uk JSON API |
| RTGS | JPY | Bank of Japan (BoJ-NET) | HTML |
| RTGS | HKD | HKMA (CHATS) | PDF |
| RTGS | CNH | HKMA (CNY clearing in HK) | PDF |
| RTGS | CHF | SNB / SIX SIC | HTML |
| RTGS | CAD | Payments Canada (Lynx) | HTML/PDF |
| RTGS | AUD | RBA (RITS) | HTML |
| RTGS | SGD | MAS (MEPS+) | PDF/HTML |
| EXCHANGE | CME | CME Group FX futures | HTML |
| EXCHANGE | HKEX | HKEX FX futures | HTML |
| EXCHANGE | SGX | SGX FX futures | HTML |

National (public) holidays are sourced from `python-holidays` at runtime — no JSON files. Cited as `python-holidays v<exact-version>, calendar=<code>` with `source_origin = "library"`, tagged `is_reference_only = True`.

### 7.3 Fetcher contract

Each `scripts/sources/<name>.py` exposes:

```python
def fetch(year_range: tuple[int, int]) -> dict:
    """Return a dict matching the JSON schema for this source."""
```

Side effects: writes the parsed JSON to `data/<kind>/<file>.json` and the raw upstream document to `data/<kind>/_raw/<file>.<ext>`. `fetched_at` is auto-stamped to UTC now. The fetcher is the audit trail.

### 7.4 Refresh — three entry points

| Entry point | Used by | Writes where | Effect |
|---|---|---|---|
| Streamlit "Refresh holiday data" button (sidebar + per-source `↻`) | Desk users | User cache `~/.fx_holiday_calculator/cache/` | Local overlay; `cache > bundled`. Bundled package files untouched. |
| GitHub Actions `workflow_dispatch` on `refresh-holidays.yml` | Maintainers | Repo `data/` via PR | Same flow as monthly cron, on demand. |
| `python -m fx_holiday_calculator.refresh` | Maintainers / CI | `--cache` (default) or `--write-bundled` | Mirrors the UI button or the GH workflow respectively. |

The monthly cron in `refresh-holidays.yml` runs all fetchers for `[current_year, current_year + 2]`, runs the **library tripwire** (`python-holidays` cross-check on TARGET2/Fedwire/CHAPS, fails CI on drift), commits diffs, and opens a PR titled *"Holiday refresh YYYY-MM"* via `peter-evans/create-pull-request`. If a fetcher errors, CI fails and a tracking issue is updated.

`python-holidays` is **pinned** in `pyproject.toml`. Bumps are deliberate PRs.

### 7.5 Loader

`fx_holiday_calculator/calendars/loader.py` reads JSON at import time and exposes:

```python
get_rtgs_calendar("USD")     -> RtgsCalendar
get_exchange_calendar("HKEX") -> ExchangeCalendar
get_national_calendar("US")  -> NationalCalendar     # python-holidays-backed
```

Each `Calendar` exposes `is_holiday(date) -> bool` and `get_holiday(date) -> HolidayEntry | None`. `HolidayEntry` carries the resolved `source_url`, `source_doc_title`, `source_fetched_at`, and `source_origin ∈ {"bundled","cache","live"}`.

Cache layering: `user_cache > bundled`. Future BYOD overrides plug in here via `FX_HOLIDAY_OVERRIDES_PATH` env var.

## 8. Engine

### 8.1 Module dependency map

```
tenor.py ─┐
          │
pairs.py ─┤
          ├──► swap.py ─────────┐
calendars/┤                     │
          │                     ├──► ui/
conventions/                    │
   spot_offset.py               │
   business_day.py              │
   cross.py ──► holidays_view.py ┘
```

UI never reaches into `calendars/` or `conventions/` directly — only through `swap.py` and `holidays_view.py`.

### 8.2 `tenor.py`

Pure function from string → typed `Tenor`:

```python
@dataclass
class Tenor:
    kind: Literal["ON","TN","SN","SPOT","PERIOD","IMM","BROKEN"]
    period_unit: Literal["D","W","M","Y"] | None
    period_n: int | None
    imm_index: int | None              # 1..4
    target_date: date | None           # for BROKEN
```

Accepts: `ON`, `TN`, `SN`, `SPOT`, `1W`, `2W`, `3W`, `1M..24M`, `1Y`, `2Y`, `5D`, `45D`, `IMM1..IMM4`, `YYYY-MM-DD`. Whitespace + case insensitive. Bad input raises `InvalidTenorError`.

### 8.3 `pairs.py`

```python
@dataclass(frozen=True)
class Pair:
    base: str
    quote: str
    spot_offset_days: int           # 1 for USD/CAD, 2 otherwise (in v1 scope)
    listed_on: tuple[str, ...]      # venues that list this pair directly
```

Hard-coded table covers majors and crosses across the R-Mid set, plus the FX futures pairs traded on V-Min venues.

### 8.4 `conventions/`

- `spot_offset.py::apply_spot_offset(trade_date, pair, calendars) -> SpotResult` — walks forward `pair.spot_offset_days` good business days, returning the result and a per-day trace.
- `business_day.py` — `is_good_business_day`, `roll(date, calendars, mode)` with modes `following`, `preceding`, `modified_following` (default), `modified_preceding`, plus `apply_eom`.
- `cross.py::rtgs_calendar_set(pair, ref) -> CalendarSet` — assembles `{base, quote, ref if ref != "none"}` (deduped). A date is good iff good in **all** calendars in the set.
- `cross.py::relevant_venues(pair, ref) -> list[str]` — returns venues that list the pair directly **or** any leg through the reference currency. Surfaced as toggleable checkboxes in the UI.

### 8.5 `swap.py`

```python
def calculate_swap_dates(
    trade_date: date,
    pair: Pair,
    far_tenor: Tenor,
    near_tenor: Tenor | None = None,                    # set for FFS
    ref_currency: Literal["none","USD","EUR","HKD","CNH"] = "USD",
    calendar_mode: Literal["FX","EXCHANGE","BOTH"] = "FX",
) -> SwapResult: ...
```

**Two modes, distinguished by whether `near_tenor` is provided:**

- `near_tenor is None` → **Standard mode.** Near leg is implied by `far_tenor.kind` (see translation table below). Covers SPOT, ON/TN/SN, forward outright, standard swap.
- `near_tenor is not None` → **Forward-forward mode (FFS).** Both legs are forwards, computed independently from spot. Both `near_tenor` and `far_tenor` must be `PERIOD`, `IMM`, or `BROKEN` (forward kinds); ON/TN/SN/SPOT are rejected with `InvalidFFSCombinationError`. The engine also checks `far_date > near_date` post-adjustment and errors if not.

```python
@dataclass
class SwapResult:
    trade_date: date
    spot_date: date              # always populated (the unadjusted market spot for the pair)
    near_date: date | None       # leg-1 settlement; None for SPOT (single-leg trade)
    far_date: date | None        # leg-2 settlement; None for SPOT
    spot_trace: list[AdjustmentStep]
    near_trace: list[AdjustmentStep]   # may be empty when near_date == spot_date
    far_trace: list[AdjustmentStep]
    calendars_used: list[str]    # e.g. ["EUR (TARGET2)", "JPY (BoJ-NET)", "USD (Fedwire)"]
    calendar_mode: Literal["FX","EXCHANGE","BOTH"]

@dataclass
class AdjustmentStep:
    candidate_date: date
    weekday: str
    statuses: dict[str, CalendarStatus]   # calendar_label -> status
    decision: Literal["accepted","reject_holiday","reject_weekend","rolled_eom"]

@dataclass
class CalendarStatus:
    is_good: bool
    holiday_name: str | None
    source_url: str | None
    source_doc_title: str | None
    source_fetched_at: datetime | None
    source_origin: Literal["bundled","cache","live"] | None
```

The trace is the verification surface: every step lists every calendar's status with the source URL inlined for any holiday rejection.

**Standard mode — far_tenor → date translation** (every BD calculation uses the calendar set resolved by `cross.rtgs_calendar_set` or `cross.relevant_venues` per `calendar_mode`; modified-following + EOM where shown):

| `far_tenor` | `near_date` | `far_date` |
|---|---|---|
| ON | trade_date | trade_date + 1 BD |
| TN | trade_date + 1 BD | spot_date |
| SN | spot_date | spot_date + 1 BD |
| SPOT | `None` | `None` (only `spot_date` populated; single-leg trade) |
| `nD/nW/nM/nY` | spot_date | spot + period → mod-following → EOM |
| IMM1..IMM4 | spot_date | 3rd Wednesday of next Mar/Jun/Sep/Dec → mod-following |
| BROKEN | spot_date | user-supplied target → mod-following |

**Forward-forward mode — both tenors are translated independently:**

| `near_tenor` / `far_tenor` (each, must be PERIOD/IMM/BROKEN) | resulting leg date |
|---|---|
| `nD/nW/nM/nY` | spot + period → mod-following → EOM |
| IMM1..IMM4 | 3rd Wednesday of corresponding Mar/Jun/Sep/Dec → mod-following |
| BROKEN | user-supplied target → mod-following |

Both legs share the same `spot_date` anchor and same calendar set. Each leg gets its own `AdjustmentStep` trace in the result (`near_trace`, `far_trace`).

`spot_date` is always populated, even when no leg uses it directly (e.g. ON), so the UI can display "the market spot for this pair on this trade date" as context.

### 8.6 `holidays_view.py`

```python
def list_holidays(
    pair: Pair,
    ref_currency: str,
    start: date,
    end: date,
    calendar_mode: Literal["FX","EXCHANGE","BOTH"] = "BOTH",
    include_national: bool = False,
    selected_venues: set[str] | None = None,    # None → all from cross.relevant_venues()
    selected_rtgs: set[str] | None = None,      # None → all from cross.rtgs_calendar_set()
) -> list[HolidayRow]: ...

@dataclass
class HolidayRow:
    date: date
    weekday: str
    type: Literal["FX_RTGS","EXCHANGE","NATIONAL"]
    calendar: str               # e.g. "USD (Fedwire)" / "HKEX" / "HK (national, ref)"
    holiday_name: str
    source_url: str             # for NATIONAL: "https://pypi.org/project/holidays/"
    source_doc_title: str       # for NATIONAL: "python-holidays vX.Y.Z, calendar=<code>"
    source_fetched_at: datetime # for NATIONAL: library load time
    source_origin: Literal["bundled","cache","live","library"]
    is_reference_only: bool     # True iff type == "NATIONAL"
```

One row per `(date × calendar)`. The UI groups them by date by default. National rows appear only when `include_national=True` and are visually distinguished.

## 9. UI (Streamlit 1.30)

Single `streamlit run run_ui.py`. Sidebar always visible; main pane has three tabs.

### 9.1 Sidebar — data origin and refresh

- Active origin badge: one of `bundled` / `cache (live)` / `cache (live, stale)`.
- Bundled fetched date and cache-last-refreshed date.
- Global refresh button → writes user cache, runs all fetchers, shows per-source result panel.
- Per-source rows with individual `↻` icons, source URL link, last-fetched-at.
- Last refresh log: per-source diff summary or `⚠ error — retry` line.
- Clear-cache button reverts to bundled-only.

### 9.2 Tab — Swap Date Calculator

**Inputs:**
- Currency pair, trade date.
- **Swap kind** (radio): `Standard (single tenor)` [default] / `Forward-forward (two tenors)`.
- **Tenor input(s):** Standard mode shows one tenor field (or broken-date picker). FFS mode shows two — `Near tenor` and `Far tenor` (or two broken-date pickers); ON/TN/SN/SPOT are disabled in FFS mode with an inline note.
- Reference currency (radio: none / USD / EUR / HKD / CNH).
- Calendar mode (radio: FX-RTGS only [default] / Exchange only / Both).

**Pre-calc surface:** the resolved calendar set is shown as chips before the user clicks Calculate, so they see exactly what calendars will drive the math.

**Result:** trade/spot/near/far dates with day counts (spot→near, spot→far, near→far); full adjustment trace per leg with each `AdjustmentStep` rendered as one line per candidate date, the per-calendar `✓/✘` statuses, and inline source citations for any rejection. When `calendar_mode = EXCHANGE`, a yellow note states settlement is exchange-cleared, not RTGS. In FFS mode, the result card labels both legs explicitly as "Near (forward)" and "Far (forward)" to avoid confusion with standard-swap "spot vs forward" framing.

### 9.3 Tab — Holiday Calendar

Inputs: currency pair, reference currency, calendar mode (default `Both`), date range, "Include national (reference only)" toggle (default off), per-venue checkboxes (auto from `relevant_venues`), per-RTGS-currency checkboxes.

Output: a table of `HolidayRow`s. Default view is **grouped by date** with expandable per-calendar details; an "ungrouped" toggle gives one row per (date × calendar). Source URLs are clickable. CSV and JSON export buttons.

### 9.4 Tab — About / Sources

Static page covering:
1. Methodology paragraph for FX-RTGS, Exchange, and National.
2. Sources table (one row per calendar — name, operator, URL, fetcher script, last-fetched bundled+cache).
3. Provenance contract statement: *"Every holiday returned by this tool is paired with the URL of the official document it came from and the timestamp it was fetched at. There are no unsourced dates."*
4. Refresh policy.
5. License + sponsor links.

### 9.5 Streamlit 1.30 quirks (codified in CLAUDE.md)

- `use_container_width=True`, never `width="stretch"`.
- `st.column_config.*Column` without `width=`.
- No experimental APIs. Pinned 1.30 in CI.

## 10. Testing

| File | Asserts |
|---|---|
| `test_tenor.py` | T-Flex parser exhaustively; case/whitespace; rejection of garbage. |
| `test_conventions.py` | Spot offset T+1 / T+2; mod-following with month-end roll-back; EOM; calendar-set union deduplication. |
| `test_swap.py` | Fixture-based end-to-end across USD-pair, non-USD cross with each ref option, weekend-only adjustment, holiday adjustment, EOM, Exchange-only mode, ON/TN/SN/IMM/broken-date, **FFS with PERIOD+PERIOD, PERIOD+IMM, IMM+IMM, BROKEN+BROKEN combinations**, FFS rejection of ON/TN/SN/SPOT, FFS rejection when far ≤ near — every `AdjustmentStep` field populated. |
| `test_holidays_view.py` | Row counts per mode, group-by-date collapse, national rows only when toggled and carry `is_reference_only=True`. |
| `test_calendars.py` | Loader assembles RTGS + Exchange from JSON; cache overlays bundled; `HolidayEntry.source_*` populated from `default_source` and per-entry override. |
| `test_data_integrity.py` | **Every JSON entry resolves to a non-null source URL/title/fetched_at.** CI fails otherwise. This enforces the "no unsourced dates" contract. |
| `test_fetchers.py` | Each fetcher has a recorded-fixture test using `tests/fixtures/sources/`. Given fixture in → expected JSON out. **Fully offline; no network in `pytest`.** |

All tests offline. Run with `pytest`. No `pytest-cov`. Lint: `flake8`, `black --check`, `isort --check`.

## 11. CI

**`.github/workflows/tests.yml`** (push and PR):
- Matrix Python 3.10 + 3.11.
- `pip install -e ".[test]"`, `flake8`, `black --check`, `isort --check`, `pytest`.
- `streamlit run --server.headless true run_ui.py` smoke test for import-time errors against pinned 1.30.

**`.github/workflows/refresh-holidays.yml`** (monthly cron + `workflow_dispatch`):
- Run `python -m fx_holiday_calculator.refresh --write-bundled`.
- Run library-as-tripwire cross-check.
- Stage JSON + sidecar raw-document diffs.
- If anything changed → open PR via `peter-evans/create-pull-request`.
- If a fetcher errors → comment on (or open) tracking issue.

## 12. Packaging

- `pyproject.toml` with `setuptools`, name `fx-holiday-calculator`, `requires-python >= "3.10"`. Dependencies allowed under the constrained corporate profile: `streamlit==1.30.*`, `python-holidays` (pinned), `requests`, `pdfplumber` (or `pypdf`). Optional `[test]` extra: `pytest`, `flake8`, `black`, `isort`. Optional `[extras]` extra (NOT available under the constrained profile): `exchange_calendars` — required for live-refresh of `data/fx_exchange/{SGX,HKEX,CME}.json`.
- `pack.sh` mirrors OpenFigiClient/FxFixParser; produces sdist + wheel into `dist/`.
- `proprietary/`, `dist/`, `__pycache__`, `.pytest_cache` gitignored.
- `run_ui.py` at repo root.
- No CLI entrypoint in v1.

## 13. Operations after first ship

| Action | Trigger | Who |
|---|---|---|
| Skim auto-PR diff | Monthly when one appears (typically Sep–Nov for next-year calendars) | Maintainer |
| Approve auto-PR | Diff matches upstream | Maintainer |
| Click Refresh in UI | Anytime user wants live data | Any user |
| Add JSON override | One-off events (typhoon, ad-hoc) | Maintainer / contributor PR |
| Repair fetcher | CI fails after upstream redesign | Maintainer |
| Add new currency / venue | v1.1+ | Maintainer (new fetcher + new JSON + `pairs.py` row) |

## 14. Open items / future work

- **BYOD overrides** (`FX_HOLIDAY_OVERRIDES_PATH`) — loader supports it, no UI surface in v1.
- **Half-day / partial closures** — schema currently full-day only; if surfaced, add a `time_of_day` field to entries.
- **Wider currency / venue scope** — KRW, INR, TWD, MXN, BRL on the RTGS side; ICE, B3, TFX on the venue side.
- **Confidence flag** — optional `confidence: official|inferred` on entries when an upstream document is ambiguous.
- **ISDA / FpML holiday code mapping** — useful for cross-referencing with ISDA-driven systems.

## 15. Provenance contract

> Every holiday returned by this tool is paired with the URL of the official document it was sourced from and the timestamp at which it was fetched. There are no unsourced dates. National (public) holidays are surfaced for reference only and never drive any calculation.

This is the project's reason to exist. CI enforces it via `test_data_integrity.py`.
