# 2026-05-11 — Phase A correctness fixes + Phase B.1 hybrid exchange calendars

**Scope:** Two pieces of work in one session.

1. **Phase A** — close the nine correctness/UX/CI issues surfaced by two
   rounds of code review against the v1 implementation.
2. **Phase B.1** — start the exchange-calendar (CME/HKEX/SGX) buildout
   that was deferred in v1. Hit a primary-source blocker; pivoted to a
   library-floored hybrid strategy with primary-source overrides as a
   future drop-in path.

**Baseline before this session:**
- `pytest -q` — 125 passed
- `flake8` — 15 errors
- `black --check` — 29 files dirty
- `isort --check` — 4 files dirty
- All four bundled RTGS calendars at `schema_version` 1 (USD at 2)
- No exchange-calendar data bundled

**State at end of session:**
- `pytest -q` — 168 passed (+43 across new and updated tests)
- `flake8` — clean
- `black --check` / `isort --check` — clean
- All bundled calendars at `schema_version` 3 with `valid_from`/`valid_until`
- Library-sourced exchange calendars bundled for SGX/HKEX/CME

Not committed. The user reviews and commits manually per the standing
`CLAUDE.md` rule.

---

## Phase A — nine correctness/UX/CI fixes

### Issues fixed

| # | Severity | Area | One-line |
|---|---|---|---|
| 3 | High | Correctness | Calendars had no validity window — out-of-range queries silently returned "not a holiday". |
| 4 | High | Correctness | `calculate_swap_dates(calendar_mode=...)` was a no-op; FX/EXCHANGE/BOTH all returned identical results. |
| 5 | High | Correctness | `list_holidays(selected_rtgs=None)` listed every RTGS calendar passed in, not pair+ref-derived. |
| 6 | Medium | Correctness | Standard broken-date forward could return a far leg before spot. |
| 7 | Medium | Correctness | ON tenor set `near_date = trade_date` raw — non-business trade dates slipped through. |
| 8 | Medium | UX | Holiday tab help text said "EXCHANGE shows FX rows" but engine returned 0 rows. |
| 9 | Medium | CI/hygiene | Lint gate in `.github/workflows/tests.yml` failing across flake8/black/isort. |

Issues 1 and 2 (packaging — `scripts.sources.*` excluded from wheel,
`data/` not declared as package-data) were deferred per user decision
("v1 only for source-checkout").

### Key design decisions

#### Calendar validity window (issue 3)

Introduced `valid_from`/`valid_until` as **required** schema fields,
bumped `schema_version` to 3. Both `RtgsCalendar` and `ExchangeCalendar`
dataclasses now require these fields; out-of-range queries raise
`CalendarRangeError` with the window in the message.

The alternative — making them optional with permissive defaults — was
explicitly rejected. The whole point is to surface the silent-fallthrough
case that caused issue 3 in the first place; an optional field with a
wide default would let the bug back in.

Cost: every test helper constructing `RtgsCalendar`/`ExchangeCalendar`
directly had to be updated (9 sites across 5 test files). Mechanical
change, but unavoidable.

#### Spot offset always uses RTGS, regardless of `calendar_mode` (issue 4)

`calculate_swap_dates` builds two calendar sets now: `rtgs_cs` for spot
offset and `leg_cs` for near/far rolls. Spot is fundamentally an
FX-market settlement concept (T+1/T+2 against the FX-RTGS calendars).
Exchange holidays don't affect when a CLS-settled FX trade actually
clears. Only the swap legs are subject to the calendar-mode choice.

This matches the spec's note on CME: "FX delivery happens via the
Continuous Linked Settlement (CLS) mechanism for most pairs; CME-specific
delivery dates fall on the third Wednesday of contract months and are
subject to mod-following adjustment using the union of FX-RTGS
calendars."

#### EXCHANGE/BOTH must raise, not silently degrade (issue 4)

When the user picks EXCHANGE or BOTH but no exchange calendars are
provided, the engine raises `MissingExchangeCalendarError` rather than
falling back to FX-only. The UI catches this and shows a clear error.
"Silently lying" was identified as worse than "failing loud" — that's
the core promise of a double-check tool.

#### `list_holidays(selected_rtgs=None)` auto-derives from pair+ref (issue 5)

Previously: `None` meant "use everything in `rtgs_calendars`". This was
the documented API but acted as a footgun — callers passing the full
dict got all calendars regardless of pair. Now: `None` mirrors the
existing exchange branch's `relevant_venues()` behaviour and derives
from `pair` and `ref_currency`. Explicit `selected_rtgs={...}` still
wins.

#### Validation is rejection, not auto-correction (issue 7)

For ON tenor with a non-business trade date: reject input (raise
`InvalidTradeDateError`). Auto-adjusting the trade date silently was
rejected — a double-check tool that mutates its inputs is worse than
one that refuses them.

### Test coverage added

- `test_calendar_loader.py`: validity-window enforcement (5 tests)
- `test_swap.py`: ON trade-date validation, broken-date < spot validation,
  EXCHANGE/BOTH calendar-mode plumbing, spot-always-RTGS invariant (8 tests)
- `test_holidays_view.py`: auto-scope correctness, explicit-scope-wins (3 tests)
- `test_data_integrity.py`: validity-window declared on every bundled JSON,
  entries within window (parametrized over all files)

---

## Phase B.1 — Library-sourced exchange calendars (hybrid)

### Original plan vs reality

Original plan (per user priority): build `scripts/sources/sgx_fx.py` to
HTML-scrape SGX's holiday page, then HKEX, then CME.

What actually happened:

- **SGX**: The trading-and-clearing-hours page is now a JavaScript SPA.
  Static HTML is an empty shell. `urllib`/`requests` (the only HTTP path
  available under BOCHK constraints — no Playwright) cannot reach the
  holiday data.
- **HKEX**: Same SPA pattern.
- **CME**: Master holiday calendar widget is XHR-loaded.
- **SGX PDF (provided by user)**: A 4.2 MB per-product calendar. Each
  day lists product codes closed (`GIN, GINB, AJ, UC, UCO, …`) with
  full-venue closures as named caps headers (`NEW YEAR'S DAY`,
  `CHINESE NEW YEAR`). There is no single "venue is closed" signal —
  the question is product-specific. Parsing this PDF reliably requires a
  product-code → FX-product mapping that doesn't exist as a single
  authoritative artifact.

The `docs/data-sources.md` spec assumed "HTML with per-year derivatives
holiday table" for all three venues. That assumption is stale for all
three.

### Decision: hybrid strategy

After surveying open-source alternatives (`exchange_calendars`,
`pandas_market_calendars`, `python-holidays`) and reading the
`exchange_calendars` source for `XSES`/`XHKG`/`CMES`, the user chose a
hybrid strategy:

> Library is the v1 floor. Primary-source fetchers override per venue
> when they become viable. UI clearly surfaces which is in use, with
> caveats about library limitations.

This trades the spec's "primary-source for every date" purity for
ship-ability. The provenance contract is preserved because the library
still cites authoritative URLs — it just shifts the meaning of "primary
source" from "official venue document" to "community-maintained library
that tracks official documents". This matches how `python-holidays` is
already used for the national-calendar reference layer.

### Implementation

- `scripts/sources/library_exchange.py` — generator that reads
  `exchange_calendars` and emits `data/fx_exchange/{SGX,HKEX,CME}.json`.
  Each entry tagged with `note: "library-sourced … see docs/data-sources.md"`.
- Generator has an **overwrite guard**: if an existing JSON's `fetcher`
  field doesn't mention `library_exchange`, it's assumed to be
  primary-sourced and left alone. This makes the library-to-primary
  migration a no-op when a primary fetcher ships.
- `ExchangeCalendar.library_sourced: bool` field, computed by the loader
  from the `fetcher` string. Threaded through to the UI.
- UI banners in `tab_swap.py` and `tab_holidays.py` warn users when
  library-sourced data is in use, with the three caveats spelled out.
- `refresh.py` knows about exchange venues; `python -m
  fx_holiday_calculator.refresh` now refreshes all 7 sources (4 RTGS +
  3 exchange). `--source SGX` works.

### Coverage delivered

| Venue | Library calendar | Coverage | 2026 closed weekdays |
|---|---|---|---|
| SGX | `XSES` | 2026-01-01 → 2026-12-31 | 10 |
| HKEX | `XHKG` | 2026-01-01 → 2027-05-11 | 14 |
| CME | `CMES` | 2026-01-01 → 2027-05-11 | **3** |

The CME number is dramatic and *is* the load-bearing caveat: NYD, Good
Friday, Christmas only. Globex FX futures observe US bank holidays
(MLK, Memorial, Independence, Labor, Thanksgiving) that the library
does not encode. A trader relying on this for a real CME-cleared trade
would be misled. The UI banner is non-negotiable here.

### Caveats documented (UI + README + data-sources.md)

The three caveats users must understand:

1. **Equity ≠ FX-futures.** Library encodes equity sessions. CME is the
   extreme example — only 3 closed weekdays/year. Globex FX futures
   close additional US bank holidays.
2. **Per-product nature.** Exchange holidays are observed per-product,
   not per-venue. SGX's published 2026 calendar lists ~50 dates where
   *some* product is closed, vs ~10 that close the entire venue. The
   library returns one calendar per venue (≈ the full-venue-closure
   subset).
3. **Coverage-horizon lag.** Lunar/Islamic dates are hand-typed into the
   library by community contributors. Year-ahead extensions arrive
   months after the venue publishes. `CalendarRangeError` fires past the
   coverage window — no silent fallthrough.

---

## Latent issue caught along the way

The four existing RTGS fetchers (`ecb_target2`, `federal_reserve`,
`boe_chaps`, `boj`) were emitting `schema_version: 1` JSON without
`valid_from`/`valid_until`. Once Phase A bumped the loader to require
schema 3, running `python -m fx_holiday_calculator.refresh` would have
written JSON that the loader rejected on next load — silent breakage
waiting to happen. Updated all four `build_payload` functions to emit
schema 3.

---

## What's still on the table

### Deferred from this session

- **Issues 1 + 2 (packaging)** — `scripts.sources.*` excluded from
  wheel, `data/` not declared as package-data. Deferred per "v1 only for
  source-checkout".
- **Primary-source PDF parser for SGX** — the user-provided PDF URL is
  `https://api2.sgx.com/sites/default/files/2026-01/SGX%20Calendar%202026_2.pdf`,
  reachable via plain HTTP with a browser User-Agent. Parse strategy:
  `pdfplumber` on the named caps headers (`NEW YEAR'S DAY`, etc.) to
  extract full-venue closures. Estimated 1 session. When this lands,
  drop the library-sourced SGX JSON; loader will pick up the
  primary-sourced replacement automatically.
- **HKEX primary-source parser** — similar pattern; HKEX publishes
  annual derivatives calendar PDFs.
- **CME primary-source parser** — CME publishes a downloadable
  calendar export from their website widget. Worth investigating
  whether that's reachable without JS.

### Phase B.2 / B.3 (originally CME + HKEX fetcher sessions)

These are now "primary-source overrides per venue" — independent units
of work, each replacing the library data for one venue.

### Spec drift to address eventually

`docs/data-sources.md` was written assuming each venue had an HTML
table to scrape. SGX/HKEX/CME all rearchitected to SPAs. The hybrid
section in `data-sources.md` now reflects this reality, but the
per-venue subsections still carry the old "parser strategy" prose
under a "Future primary source (planned)" header. When primary-source
fetchers ship, those sections need rewrites — not a deletion of the
library record but a record of what the primary source provides.
