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
  - Settles on FX-RTGS calendars only; listed-venue calendars never enter swap math.
- **FX futures key dates** — given an exchange and a listed contract, look up the contract's Last Trading Day (LTD) and final settlement / delivery date, and report the business days remaining until each from an as-of date. Futures are a **lookup**, not a tenor-driven calculation: the venue publishes the contract calendar, the tool surfaces it with provenance.
- **Holiday calendar** — given a currency pair, reference currency, calendar mode, and date range, list every relevant holiday with its source URL.

Used as a verification tool against in-house systems, so the **provenance of every holiday must be inspectable**. There are no unsourced dates: every holiday returned by the engine is paired with the URL of the official document it was sourced from and the timestamp it was fetched at.

National (public) holidays are surfaced **for reference only** and are visually distinguished. They never drive any calculation.

## 2. Goals

1. Compute FX swap near/far dates for OTC FX spot, forward outright, **standard swap**, **forward-forward swap**, and NDF, using authoritative FX-RTGS settlement calendars.
2. Surface FX-listed-venue (futures) contract calendars — LTD, final settlement date, and business days remaining — as a lookup over the contracts the venue publishes, with every contract row pointing to the document that backs it.
3. Display per-pair holidays in a date range, with the user choosing FX-only, Exchange-only, or both.
4. Make every holiday **and every contract date** traceable to a primary-source document URL plus a fetch timestamp, in the UI.
5. Allow on-demand manual refresh from upstream sources, in addition to a scheduled refresh.
6. Stay maintainable: one fetcher per source, deterministic where possible, with a tripwire against `python-holidays` to catch drift, and a clear derived-vs-scraped marker on every contract row.

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

**Tenor inputs (T-Flex):** `ON`, `TN`, `SN`, `SPOT`, `nD`, `nW`, `nM`, `nY`, `IMM1..IMM4`, plus a broken-date target (raw `YYYY-MM-DD`). Tenors apply to the **swap** flow only. The **futures** flow does not accept a tenor — the user picks an exchange and then a contract code.

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
│   ├── futures.py                   # listed-contract lookup (LTD, settlement, BD-until)
│   ├── holidays_view.py
│   ├── refresh.py                   # `python -m fx_holiday_calculator.refresh`
│   ├── calendars/
│   │   ├── loader.py
│   │   ├── rtgs.py
│   │   ├── exchange.py              # venue *holidays*
│   │   ├── contracts.py             # venue *contract listings*
│   │   ├── national.py              # python-holidays-backed
│   │   └── types.py                 # HolidayEntry, ContractEntry, CalendarStatus, …
│   ├── conventions/
│   │   ├── spot_offset.py
│   │   ├── business_day.py          # good-BD + roll modes + EOM
│   │   └── cross.py                 # RTGS calendar-set union
│   └── ui/
│       ├── app.py
│       ├── sidebar.py
│       ├── tab_swap.py
│       ├── tab_futures.py
│       ├── tab_holidays.py
│       └── tab_about.py
├── data/                            # bundled JSON — source of truth
│   ├── fx_rtgs/
│   │   ├── USD.json  EUR.json  GBP.json  JPY.json  HKD.json
│   │   ├── CNH.json  CHF.json  CAD.json  AUD.json  SGD.json
│   │   └── _raw/                    # sidecar upstream documents
│   └── fx_exchange/
│       ├── CME.json   HKEX.json   SGX.json     # venue holiday calendars
│       ├── CME_contracts.json   HKEX_contracts.json   SGX_contracts.json   # listed-contract calendars
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
│       ├── cme_fx.py                # venue holidays
│       ├── hkex_fx.py
│       ├── sgx_fx.py
│       ├── cme_contracts.py         # listed-contract calendars (scrape-first, derive-fallback)
│       ├── hkex_contracts.py
│       └── sgx_contracts.py
└── tests/
    ├── test_tenor.py
    ├── test_conventions.py
    ├── test_swap.py
    ├── test_futures.py
    ├── test_holidays_view.py
    ├── test_calendars.py
    ├── test_data_integrity.py
    ├── test_fetchers.py
    └── fixtures/
        └── sources/                 # recorded upstream documents per fetcher
```

## 7. Data architecture

### 7.1 JSON schema

Three flavours of bundled JSON live under `data/`:

1. **RTGS currency files** — one per currency at `data/fx_rtgs/<CCY>.json`.
2. **Venue holiday files** — one per FX-listed venue at `data/fx_exchange/<VENUE>.json`. The full-venue closure calendar used by the Holiday tab.
3. **Venue contract-listing files** — one per FX-listed venue at `data/fx_exchange/<VENUE>_contracts.json`. The list of currently listed FX-futures contracts with LTD and final settlement / delivery date per contract. Powers the Futures tab.

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

Exchange holiday files have the same shape with `calendar_kind: "EXCHANGE"`, `venue`, and a `products` list of FX contracts the file applies to.

**Contract-listing files (`<VENUE>_contracts.json`)** have a parallel shape with `calendar_kind: "EXCHANGE_CONTRACTS"`:

```json
{
  "schema_version": 1,
  "venue": "CME",
  "calendar_kind": "EXCHANGE_CONTRACTS",
  "default_source": {
    "url": "https://www.cmegroup.com/markets/fx/...",
    "doc_title": "CME FX Futures Contract Specifications",
    "fetched_at": "2026-05-13T03:00:00Z",
    "fetcher": "scripts/sources/cme_contracts.py@v1",
    "default_derivation_mode": "scrape"
  },
  "contracts": [
    {
      "code": "6EM6",
      "pair": "EUR/USD",
      "product_name": "Euro FX Futures",
      "contract_month": "2026-06",
      "last_trading_day": "2026-06-15",
      "settlement_date": "2026-06-17",
      "first_notice_day": null,
      "derivation_mode": null,
      "source": null,
      "note": null
    }
  ]
}
```

`derivation_mode` is the **load-bearing provenance flag** for contract data, parallel to the source-URL contract for holidays. Allowed values:

| Value | Meaning |
|---|---|
| `"scrape"` | Row was parsed from the venue's published contract page. Default / preferred. |
| `"derived"` | Row was generated from a documented venue rule (e.g. "LTD = 3rd Wednesday − 2 BDs") because the scrape failed or covered fewer months than required. **UI surfaces a warning banner for these rows.** |
| `"manual"` | Row was hand-edited into the JSON by a maintainer because neither scrape nor derivation produced an authoritative value. Carries its own per-entry `source` override pointing to the document the maintainer relied on. Treated as authoritative; no warning banner. |

`null` at the entry level inherits from the file's `default_source.default_derivation_mode`.

**Rules:**
- Every holiday must resolve to a non-null `source` — either its own override or the file's `default_source`. The integrity test fails CI otherwise.
- Every contract must resolve to a non-null `source`, a non-null `derivation_mode`, and non-null `last_trading_day` + `settlement_date`. The integrity test fails CI otherwise.
- Per-entry `source` overrides exist for one-off events (typhoon T8 closures, ad-hoc closures) where one date came from a different document than the rest. For contract-listing files, per-entry overrides are mandatory whenever `derivation_mode = "manual"`.
- **Precedence on refresh:** when a fetcher rewrites a contract-listing file, it must preserve any pre-existing rows with `derivation_mode = "manual"`. Manual rows are never overwritten by scrape or derive outputs. The refresh test verifies this.
- Sidecar raw documents (`data/fx_rtgs/_raw/USD.html`, `data/fx_exchange/_raw/CME_contracts.html`, etc.) are committed alongside, so `git diff` can show exactly what each upstream said at fetch time.

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
| EXCHANGE | CME | CME Group FX futures (venue holidays) | HTML |
| EXCHANGE | HKEX | HKEX FX futures (venue holidays) | HTML |
| EXCHANGE | SGX | SGX FX futures (venue holidays) | HTML |
| EXCHANGE_CONTRACTS | CME | CME Group FX-futures contract listings | HTML scrape → rule-derive fallback |
| EXCHANGE_CONTRACTS | HKEX | HKEX FX-futures contract listings | HTML scrape → rule-derive fallback |
| EXCHANGE_CONTRACTS | SGX | SGX FX-futures contract listings | HTML/PDF scrape → rule-derive fallback |

National (public) holidays are sourced from `python-holidays` at runtime — no JSON files. Cited as `python-holidays v<exact-version>, calendar=<code>` with `source_origin = "library"`, tagged `is_reference_only = True`.

### 7.3 Fetcher contract

Each `scripts/sources/<name>.py` exposes:

```python
def fetch(year_range: tuple[int, int]) -> dict:
    """Return a dict matching the JSON schema for this source."""
```

Side effects: writes the parsed JSON to `data/<kind>/<file>.json` and the raw upstream document to `data/<kind>/_raw/<file>.<ext>`. `fetched_at` is auto-stamped to UTC now. The fetcher is the audit trail.

**Contract-listing fetchers (`<venue>_contracts.py`) additionally follow a scrape → derive fallback:**

1. **Attempt scrape.** HTTP GET the venue's contract-specs / listed-contracts page; parse out contract code, pair, contract month, LTD, settlement date. Rows produced this way get `derivation_mode = "scrape"`.
2. **On scrape failure or partial coverage, derive from venue rules.** Generate the standard quarterly months (Mar/Jun/Sep/Dec) plus serials per the venue's rule (e.g. CME: 3rd Wednesday = settlement, LTD = settlement − 2 BDs against USD calendar + base-currency calendar). Rows produced this way get `derivation_mode = "derived"`. The fetcher logs a warning and the JSON file's top-level `default_source.default_derivation_mode` is set to `"derived"` so the UI banner fires.
3. **Preserve manual rows.** Before writing, the fetcher reads the existing JSON file (if any) and re-inserts any row with `derivation_mode = "manual"`. These take precedence over both scrape and derive outputs even when keys collide.
4. **Never silently substitute.** If both scrape and derive fail (e.g. unknown venue rule), the fetcher exits with a non-zero status and does not overwrite the existing file. CI surfaces the failure.

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
get_rtgs_calendar("USD")          -> RtgsCalendar
get_exchange_calendar("HKEX")     -> ExchangeCalendar      # venue holidays
get_contract_calendar("HKEX")     -> ContractCalendar      # listed contracts
get_national_calendar("US")       -> NationalCalendar      # python-holidays-backed
```

Each holiday `Calendar` exposes `is_holiday(date) -> bool` and `get_holiday(date) -> HolidayEntry | None`. `HolidayEntry` carries the resolved `source_url`, `source_doc_title`, `source_fetched_at`, and `source_origin ∈ {"bundled","cache","live"}`.

`ContractCalendar` exposes `list_contracts(pair=None, asof=None) -> list[ContractEntry]` and `get_contract(code) -> ContractEntry | None`. `ContractEntry` carries `code`, `pair`, `product_name`, `contract_month`, `last_trading_day`, `settlement_date`, `first_notice_day`, `derivation_mode ∈ {"scrape","derived","manual"}`, plus the same source-provenance fields as `HolidayEntry`. The `derivation_mode` is what `tab_futures.py` reads to decide whether to render a per-row warning chip.

Cache layering: `user_cache > bundled`. Future BYOD overrides plug in here via `FX_HOLIDAY_OVERRIDES_PATH` env var.

## 8. Engine

### 8.1 Module dependency map

```
tenor.py ─┐
          │
pairs.py ─┤
          ├──► swap.py ─────────┐
calendars/┤                     │
   rtgs   │                     │
   exchange ──────► futures.py ─┤
   contracts ──────────────────►├──► ui/
   national                     │
conventions/                    │
   spot_offset.py               │
   business_day.py              │
   cross.py ──► holidays_view.py ┘
```

UI never reaches into `calendars/` or `conventions/` directly — only through `swap.py`, `futures.py`, and `holidays_view.py`. `swap.py` is FX-RTGS-only; `futures.py` is the only module that consults `calendars/contracts.py` and `calendars/exchange.py` for date math.

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
- `cross.py::relevant_venues(pair, ref) -> list[str]` — returns venues that list the pair directly or any leg through the reference currency. Used by the **Holiday** tab to populate venue checkboxes. Not used by `swap.py`. The **Futures** tab does not call this — it uses `futures.list_venues()` (all venues with a bundled contract-listings file) and applies pair filtering inside `futures.list_contracts(venue, pair=…)` instead.

### 8.5 `swap.py`

```python
def calculate_swap_dates(
    trade_date: date,
    pair: Pair,
    far_tenor: Tenor,
    near_tenor: Tenor | None = None,                    # set for FFS
    ref_currency: Literal["none","USD","EUR","HKD","CNH"] = "USD",
) -> SwapResult: ...
```

`swap.py` settles on FX-RTGS calendars only. Listed-venue calendars are surfaced separately by `futures.py` (§8.6) and do not enter swap math — an earlier draft accepted a `calendar_mode = "EXCHANGE"|"BOTH"` switch here; that has been removed because OTC FX swap settlement is governed by RTGS, not by venue trading sessions.

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

**Standard mode — far_tenor → date translation** (every BD calculation uses the calendar set resolved by `cross.rtgs_calendar_set`; modified-following + EOM where shown):

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

### 8.6 `futures.py`

Listed-FX-futures lookup. The user does not pass a tenor; they pick a venue, then a contract.

```python
def list_venues() -> list[str]:
    """Venues with a bundled contract-listings file. v1: ["CME","HKEX","SGX"]."""

def list_contracts(
    venue: str,
    pair: str | None = None,                 # optional filter, e.g. "EUR/USD"
    asof: date | None = None,                # default today; hides expired contracts
    include_expired: bool = False,
) -> list[ContractEntry]: ...

def get_contract(venue: str, code: str) -> ContractEntry: ...

def days_until(contract: ContractEntry, asof: date) -> ContractCountdown: ...
```

```python
@dataclass(frozen=True)
class ContractEntry:
    venue: str
    code: str                      # e.g. "6EM6"
    pair: str                      # e.g. "EUR/USD"
    product_name: str              # e.g. "Euro FX Futures"
    contract_month: str            # "YYYY-MM"
    last_trading_day: date
    settlement_date: date
    first_notice_day: date | None
    derivation_mode: Literal["scrape","derived","manual"]
    source_url: str
    source_doc_title: str
    source_fetched_at: datetime
    source_origin: Literal["bundled","cache","live"]
    note: str | None

@dataclass
class ContractCountdown:
    asof: date
    business_days_to_ltd: int      # negative if LTD has passed
    business_days_to_settlement: int
    calendar_days_to_ltd: int
    calendar_days_to_settlement: int
    bd_calendar_used: str          # e.g. "USD (Fedwire) ∪ EUR (TARGET2)" for 6E
```

`business_days_to_*` count good business days between `asof` (exclusive) and the target date (inclusive) against the RTGS calendar set implied by the contract's pair (base ∪ quote). The function does **not** consult the venue's exchange-holiday calendar for the countdown, because the question being asked is "how many settlement days do I have left," not "how many trading sessions." When `asof` itself is not a good business day, it is still treated as the anchor (the count is from "now").

**Provenance and warning surface:** every `ContractEntry` carries `derivation_mode`. The Futures tab renders a yellow inline chip whenever `derivation_mode == "derived"` and a neutral chip when `"manual"`. The chip's tooltip explains what the value means and links to the venue's contract-specs page so the user can verify.

**Pair filter semantics:** `pair` matches both `base/quote` and `quote/base` forms (e.g. `"EUR/USD"` matches a CME row stored as `"EUR/USD"` and a SGX row stored as `"USD/EUR"` — pair direction is a venue-specific convention and is not load-bearing for the lookup).

### 8.7 `holidays_view.py`

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

Single `streamlit run run_ui.py`. Sidebar always visible; main pane has four tabs: **Swap**, **Futures**, **Holidays**, **About / Sources**.

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

The Swap tab settles strictly on FX-RTGS calendars. There is **no calendar-mode toggle** here — venue / exchange calendars belong to the **Futures** tab (key dates) and the **Holidays** tab (display filter). A footer note links to those tabs for users arriving here looking for futures dates.

**Pre-calc surface:** the resolved RTGS calendar set is shown as chips before the user clicks Calculate, so they see exactly what calendars will drive the math.

**Result:** trade/spot/near/far dates with day counts (spot→near, spot→far, near→far); full adjustment trace per leg with each `AdjustmentStep` rendered as one line per candidate date, the per-calendar `✓/✘` statuses, and inline source citations for any rejection. In FFS mode, the result card labels both legs explicitly as "Near (forward)" and "Far (forward)" to avoid confusion with standard-swap "spot vs forward" framing.

### 9.3 Tab — Futures (listed-contract key dates)

A market-maker workflow: pick a venue, pick a contract, see its key dates and how many days remain.

**Step 1 — Exchange selector** (radio): `CME` / `HKEX` / `SGX`. Populated from `futures.list_venues()`.

**Step 2 — Contract selector:**
- Optional pair filter (dropdown auto-populated from the contracts on that venue; e.g. `Any` / `EUR/USD` / `USD/CNH` / …).
- Contract dropdown listing one row per `ContractEntry` returned by `futures.list_contracts(venue, pair, asof=today)`. Display label: `<code> · <product_name> · <contract_month>` (e.g. `6EM6 · Euro FX Futures · 2026-06`).
- `Include expired contracts` toggle (default off).

**Step 3 — As-of date** (default `today`). Used to compute business-days-remaining.

**Result card:**
- Contract code, product name, pair, contract month.
- **Last Trading Day** with weekday and `business_days_to_ltd` from the as-of date.
- **Final settlement / delivery date** with weekday and `business_days_to_settlement`.
- **First notice day** if non-null (relevant for physically-delivered or deliverable contracts).
- RTGS calendar used for the business-day count, shown as chips.
- **Provenance row:** source URL link, `source_doc_title`, `source_fetched_at`, and a **derivation badge**:
  - `derivation_mode = "scrape"` → small grey "scraped" badge.
  - `derivation_mode = "derived"` → **yellow warning chip** "⚠ derived from venue rule — verify against the venue's official contract page before trading. If this contract is unusual, add a manual override to the JSON."
  - `derivation_mode = "manual"` → blue "manual override" chip with the maintainer's note in the tooltip.

When the chosen venue's contract file has `default_derivation_mode = "derived"` (i.e. the last scrape failed and the whole file is rule-generated), a top-of-tab banner repeats the warning so it can't be missed.

### 9.4 Tab — Holiday Calendar

Inputs: currency pair, reference currency, calendar mode (default `Both`), date range, "Include national (reference only)" toggle (default off), per-venue checkboxes (auto from `cross.relevant_venues`), per-RTGS-currency checkboxes.

Output: a table of `HolidayRow`s. Default view is **grouped by date** with expandable per-calendar details; an "ungrouped" toggle gives one row per (date × calendar). Source URLs are clickable. CSV and JSON export buttons.

### 9.5 Tab — About / Sources

Static page covering:
1. Methodology paragraph for FX-RTGS, Exchange, and National.
2. Sources table (one row per calendar — name, operator, URL, fetcher script, last-fetched bundled+cache).
3. Provenance contract statement: *"Every holiday returned by this tool is paired with the URL of the official document it came from and the timestamp it was fetched at. There are no unsourced dates."*
4. Refresh policy.
5. License + sponsor links.

### 9.6 Streamlit 1.30 quirks (codified in CLAUDE.md)

- `use_container_width=True`, never `width="stretch"`.
- `st.column_config.*Column` without `width=`.
- No experimental APIs. Pinned 1.30 in CI.

## 10. Testing

| File | Asserts |
|---|---|
| `test_tenor.py` | T-Flex parser exhaustively; case/whitespace; rejection of garbage. |
| `test_conventions.py` | Spot offset T+1 / T+2; mod-following with month-end roll-back; EOM; calendar-set union deduplication. |
| `test_swap.py` | Fixture-based end-to-end across USD-pair, non-USD cross with each ref option, weekend-only adjustment, holiday adjustment, EOM, ON/TN/SN/IMM/broken-date, **FFS with PERIOD+PERIOD, PERIOD+IMM, IMM+IMM, BROKEN+BROKEN combinations**, FFS rejection of ON/TN/SN/SPOT, FFS rejection when far ≤ near — every `AdjustmentStep` field populated. Verifies that `calculate_swap_dates` does not accept a venue / exchange-mode parameter. |
| `test_futures.py` | Fixture-based end-to-end: `list_venues`, `list_contracts` (with/without pair filter, with/without expired), `get_contract`, `days_until` (negative when LTD has passed, zero when as-of == LTD, positive otherwise). Verifies that `ContractEntry.derivation_mode` round-trips from the bundled JSON, including `"scrape"` / `"derived"` / `"manual"` rows, and that `pair` filter matches both `BASE/QUOTE` and `QUOTE/BASE` orderings. |
| `test_holidays_view.py` | Row counts per mode, group-by-date collapse, national rows only when toggled and carry `is_reference_only=True`. |
| `test_calendars.py` | Loader assembles RTGS + Exchange (holidays) + Contracts from JSON; cache overlays bundled; `HolidayEntry.source_*` and `ContractEntry.source_*` populated from `default_source` and per-entry override; manual rows preserved when a fresh fetcher output is merged in. |
| `test_data_integrity.py` | **Every JSON entry resolves to a non-null source URL/title/fetched_at.** Every contract row additionally has a non-null `derivation_mode` ∈ `{"scrape","derived","manual"}` and non-null `last_trading_day` + `settlement_date`. CI fails otherwise. This enforces the "no unsourced dates" contract. |
| `test_fetchers.py` | Each fetcher has a recorded-fixture test using `tests/fixtures/sources/`. Given fixture in → expected JSON out. Contract-listing fetchers additionally have a "scrape-fails → derive-fallback" test that pipes an empty/malformed HTML fixture and asserts the produced JSON has `derivation_mode = "derived"` plus the venue-rule-derived dates, AND a "manual rows preserved" test that seeds a pre-existing JSON file with a `derivation_mode = "manual"` row and asserts the refresh does not overwrite it. **Fully offline; no network in `pytest`.** |

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
