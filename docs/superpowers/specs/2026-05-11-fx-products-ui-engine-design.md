# FX Products — UI Restructure & Engine Extension Design

**Date:** 2026-05-11
**Author:** Chan Chun Yin Johnny
**Status:** Approved (brainstorming complete; pending implementation plan)
**Builds on:** `docs/superpowers/specs/2026-05-06-fx-holiday-calculator-design.md`
**License:** MIT

---

## 1. Purpose

Extend the FX Holiday Calculator from a single "Swap Date Calculator" tab into a product-aware tool that covers the FX products an interbank desk actually verifies dates for:

1. **Spot / Swap** — the existing engine, exposed as one sub-tab covering spot, cross-spot, ON/TN/SN, forward outright, standard swap, and forward-forward swap.
2. **NDF (Non-Deliverable Forward)** — new. Fixing date + USD settlement date. Top 3 East-Asian fixing currencies: CNY, KRW, TWD.
3. **FX Option** — new. Expiry + delivery, with an OTC/Listed switch.
4. **FX Futures** — new. Last trade date + delivery date for CME / HKEX / SGX listings.

The provenance contract from the v1 design is unchanged: every holiday returned by the tool is paired with a non-null `source_url`, `source_doc_title`, and `source_fetched_at`. New fixing calendars must satisfy it on day one.

## 2. Non-goals

- Cut times on options (NY 10am, Tokyo 3pm, London 4pm). Time-of-day is not in the v1 schema.
- NDF pairs beyond CNY / KRW / TWD. INR is explicitly excluded.
- Listed-option *contract picker* (CME's specific monthly/weekly expiry codes). Listed options in this iteration use tenor-driven expiry rolled on the venue calendar — an approximation, documented as such.
- Per-product CSV / JSON export from the calculator. Only the Holiday Calendar tab exports.
- Pricing or P&L of any kind. Date math only.

## 3. UI shell

### 3.1 Tab structure

```
[ Calculator ]   [ Holiday Calendar ]   [ About / Sources ]
```

Inside Calculator, four sub-tabs:

```
[ Spot / Swap ]   [ NDF ]   [ Option ]   [ Futures ]
```

### 3.2 Per-product UI surface

| Sub-tab | Inputs | Outputs |
|---|---|---|
| **Spot / Swap** | Pair (full list) · Trade date · Swap kind (Standard / FFS) · Tenor(s) · Reference currency · Calendar mode (FX/Exchange/Both) | Spot · Near · Far · Per-leg adjustment trace |
| **NDF** | Pair (USD/CNY, USD/KRW, USD/TWD) · Trade date · Input mode radio (Tenor / Maturity) · Tenor (forward-only: PERIOD / IMM / BROKEN — SPOT/ON/TN/SN omitted from the picker per §8.3) or target settlement date | Spot · Settlement · Fixing · Per-leg adjustment trace |
| **Option** | Pair (full list) · Trade date · Tenor · Reference currency · Style radio (OTC / Listed) · Venue (when Listed) | Spot · Expiry · Delivery · Per-leg adjustment trace |
| **Futures** | Pair (listed pairs only) · Venue (CME/HKEX/SGX, filtered) · Input mode radio (Contract month / IMM tenor) · Contract month picker or IMM tenor + reference date | Last trade date · Delivery date · Per-leg adjustment trace |

The Holiday Calendar tab is unchanged. It already supports the FX / Exchange / Both calendar mode that is general across products.

### 3.3 UI file layout

```
fx_holiday_calculator/ui/
├── app.py                  # top-level tabs (Calculator / Holidays / About)
├── sidebar.py              # unchanged
├── tab_calculator.py       # NEW — hosts the 4 product sub-tabs
├── product_spot_swap.py    # renamed from tab_swap.py
├── product_ndf.py          # NEW
├── product_option.py       # NEW
├── product_futures.py      # NEW
├── tab_holidays.py         # unchanged
└── tab_about.py            # updated to list new sources + products
```

The renaming from `tab_swap.py` to `product_spot_swap.py` is deliberate: the existing engine covers Spot, Cross-Spot, ON/TN/SN, Forward outright, Standard Swap, and FFS — all in one place, because their underlying calendar logic is identical (pure RTGS). The new filename makes that explicit.

## 4. Engine modules

Per-product modules sit alongside `swap.py` (existing). UI never reaches into `calendars/` or `conventions/` directly — only through product modules.

```
fx_holiday_calculator/
├── swap.py            # existing — Spot, Swap, Forward, FFS
├── ndf.py             # NEW
├── option.py          # NEW
├── future.py          # NEW
├── holidays_view.py   # existing
├── conventions/
│   ├── spot_offset.py # existing
│   ├── business_day.py# existing — extended with IMM last-trade helper
│   ├── cross.py       # existing
│   └── dates.py       # existing — `next_imm_date`, `add_period` reused
└── calendars/
    ├── rtgs.py        # existing
    ├── exchange.py    # existing
    ├── fixing.py      # NEW
    └── national.py    # existing
```

Shared helpers stay in `conventions/`. No duplication of spot-offset, business-day, or IMM math.

### 4.1 `ndf.py`

```python
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
    warnings: list[str]

def calculate_ndf_dates(
    *,
    trade_date: date,
    pair: Pair,
    tenor: Tenor | None = None,
    target_settlement: date | None = None,
    rtgs_calendars: dict[str, RtgsCalendar],   # must contain "USD"; other keys ignored
    fixing_calendar: FixingCalendar,           # must match pair.fixing_currency
) -> NdfResult: ...
```

Exactly one of `tenor` / `target_settlement` must be provided. For v1.1 the only RTGS calendar consulted is USD — the non-deliverable side has no settlement leg, only fixing. The dict signature is kept (rather than a single `usd_calendar: RtgsCalendar` parameter) to mirror the swap engine's loader-friendly shape; UI passes `{"USD": load_rtgs_calendar("USD", ...)}`.

### 4.2 `option.py`

```python
@dataclass
class OptionResult:
    trade_date: date
    spot_date: date
    expiry_date: date
    delivery_date: date
    style: Literal["OTC", "LISTED"]
    expiry_trace: list[AdjustmentStep]
    delivery_trace: list[AdjustmentStep]
    calendars_used: list[str]
    warnings: list[str]

def calculate_option_dates(
    *,
    trade_date: date,
    pair: Pair,
    tenor: Tenor,
    style: Literal["OTC", "LISTED"],
    ref_currency: RefCurrency = "USD",
    rtgs_calendars: dict[str, RtgsCalendar],
    exchange_calendar: ExchangeCalendar | None = None,   # required when style="LISTED"
    venue: str | None = None,                            # required when style="LISTED"
) -> OptionResult: ...
```

### 4.3 `future.py`

```python
@dataclass
class FutureResult:
    contract_month: tuple[int, int]    # (year, month)
    venue: str
    last_trade_date: date
    delivery_date: date
    last_trade_trace: list[AdjustmentStep]
    delivery_trace: list[AdjustmentStep]
    calendars_used: list[str]
    warnings: list[str]

def calculate_future_dates(
    *,
    pair: Pair,
    venue: str,
    contract_month: tuple[int, int] | None = None,
    imm_tenor: Tenor | None = None,
    from_date: date | None = None,                       # required when imm_tenor used; defaults to today
    rtgs_calendars: dict[str, RtgsCalendar],
    exchange_calendar: ExchangeCalendar,
) -> FutureResult: ...
```

Exactly one of `contract_month` / `imm_tenor` must be provided.

## 5. New data layer — fixing calendars

NDF fixing dates use a brand-new calendar family. The provenance contract applies in full.

### 5.1 File layout

```
data/
├── fx_rtgs/         # existing
├── fx_exchange/     # existing
└── fx_fixing/       # NEW
    ├── CNY.json
    ├── KRW.json
    ├── TWD.json
    └── _raw/        # sidecar upstream documents (PDF/HTML)
```

### 5.2 JSON schema

Same shape as `fx_rtgs/<CCY>.json`, with `calendar_kind: "FIXING"`. The schema below is illustrative — exact upstream URLs are populated by each fetcher at implementation time and recorded in `docs/data-sources.md`:

```json
{
  "schema_version": 1,
  "currency": "CNY",
  "calendar_kind": "FIXING",
  "calendar_name": "CFETS USD/CNY Central Parity",
  "operator": "China Foreign Exchange Trade System (PBoC)",
  "default_source": {
    "url": "https://www.chinamoney.com.cn/english/...",
    "doc_title": "CFETS Trading Calendar YYYY",
    "fetched_at": "2026-04-15T03:00:00Z",
    "fetcher": "scripts/sources/cfets_cny.py@v1"
  },
  "holidays": [
    { "date": "2026-01-01", "name": "New Year's Day", "source": null, "note": null },
    ...
  ]
}
```

Rules carry over from RTGS files: every holiday entry must resolve to a non-null source (own override or `default_source`). The data-integrity test fails CI otherwise.

### 5.3 Loader

```python
# calendars/fixing.py
@dataclass
class FixingCalendar:
    currency: str            # "CNY" | "KRW" | "TWD"
    calendar_name: str
    operator: str
    default_source: SourceCitation
    holidays: dict[date, HolidayEntry]

    def is_holiday(self, d: date) -> bool: ...
    def get_holiday(self, d: date) -> HolidayEntry | None: ...

# calendars/loader.py — extended
def load_fixing_calendar(
    currency: str, *, root: Path, cache_root: Path,
) -> FixingCalendar: ...
```

Cache layering (`user_cache > bundled`) and `FX_HOLIDAY_OVERRIDES_PATH` BYOD hook are inherited from the existing loader infrastructure.

### 5.4 Fetchers

Three new fetchers, each mirroring the existing `scripts/sources/<name>.py` contract:

| Fetcher | Source | Format |
|---|---|---|
| `scripts/sources/cfets_cny.py` | CFETS / China Foreign Exchange Trade System (PBoC) | HTML / PDF |
| `scripts/sources/kftc_krw.py`  | KFTC (Korea Financial Telecommunications & Clearings Institute) / Seoul Money Brokerage | HTML / PDF |
| `scripts/sources/taifx_twd.py` | Taipei Forex Inc. | HTML |

Side effects unchanged: writes parsed JSON to `data/fx_fixing/<CCY>.json` and raw upstream document to `data/fx_fixing/_raw/<CCY>.<ext>`. `fetched_at` is auto-stamped to UTC now.

### 5.5 Pair table additions

`pairs.py` gains three NDF entries plus two new fields on `Pair`:

```python
@dataclass(frozen=True)
class Pair:
    base: str
    quote: str
    spot_offset_days: int
    listed_on: tuple[str, ...]
    ndf: bool = False                       # NEW
    fixing_currency: str | None = None      # NEW — set iff ndf=True

# Additions
_add("USD", "CNY", t=2, listed_on=(), ndf=True, fixing_currency="CNY")
_add("USD", "KRW", t=2, listed_on=(), ndf=True, fixing_currency="KRW")
_add("USD", "TWD", t=2, listed_on=(), ndf=True, fixing_currency="TWD")
```

The existing `KRW/USD` SGX-listed deliverable entry remains. `USD/KRW` is a distinct NDF pair (different convention, different settlement currency). No collision: pair keys are `(base, quote)` tuples.

### 5.6 Refresh integration

Existing entry points (sidebar manual refresh, `python -m fx_holiday_calculator.refresh`, GitHub Actions monthly cron) extend to cover the three new fetchers. Sidebar's per-source list grows by three rows. Bundled-fetched-timestamp scan logic walks subdirs; it already accepts a list of subdirectories — `fx_fixing` is appended.

## 6. Per-product conventions

All conventions cited from primary references. New sections to be added to `docs/conventions.md`.

### 6.1 Spot / Swap (existing, §1–§8 of conventions.md)

Unchanged. Spot rolls T+1 (USD/CAD) or T+2 (others) on RTGS. Forward legs roll modified-following with EOM rule keyed on spot. FFS legs anchor on original spot per OpenGamma Strata `FxSwapConvention`.

### 6.2 NDF (new — conventions.md §9)

EMTA / ISDA EM template convention. The fixing currency is the non-deliverable side (CNY, KRW, TWD).

**Tenor-driven path:**

1. `spot = apply_spot_offset(trade_date, pair, USD_RTGS_only)` — pure USD-RTGS T+2.
2. `raw_settlement = add_period(spot, tenor)` (PERIOD adds calendar months; IMM uses `next_imm_date`; BROKEN uses target).
3. `settlement = roll(raw_settlement, {USD_RTGS, fixing_calendar}, "modified_following")`, with EOM rule keyed on spot. Settlement must be good in **both** USD RTGS and the local fixing calendar — the local market needs to compute the fix, and USD needs to wire.
4. `fixing = back_roll(settlement − 2 BD, fixing_calendar, "preceding")` — counts 2 good fixing-calendar days back from settlement.

**Maturity-driven path:** same, but `raw_settlement = user_target`. Reject if rolled settlement ≤ spot (`InvalidBrokenDateError`).

**Validations:**

- `InvalidNdfPairError` if `pair.ndf is False`.
- `InvalidTradeDateError` if trade date is not a good USD-RTGS day.
- `InvalidTenorError` if tenor is `SPOT` / `ON` / `TN` / `SN` (NDF requires a forward tenor).
- Warning `NdfFixingHorizonWarning` (surfaced via `result.warnings`) if `fixing_date < trade_date + 2 calendar days`.

### 6.3 FX Option (new — conventions.md §10)

Two sub-conventions selected by the OTC/Listed radio. Reference: ISDA 1998 FX and Currency Options Definitions §3.2.

**OTC option:**

1. `spot = apply_spot_offset(trade_date, pair, rtgs_set{base, quote, ref})` — standard FX spot (with reference-currency cross rule).
2. `raw_expiry = add_period(spot, tenor)` (PERIOD / IMM / BROKEN as in swap).
3. `expiry = roll(raw_expiry, rtgs_set{base, quote, ref}, "modified_following")` with EOM rule keyed on spot.
4. `delivery = roll(expiry + pair.spot_offset_days, rtgs_set{base, quote}, "following")` — note the delivery roll uses only the two leg currencies, not the reference. The option's delivery is a vanilla forward outright off the expiry.

**Listed option:**

1. `spot` and `raw_expiry` as in OTC.
2. `expiry = roll(raw_expiry, exchange_calendar(venue), "modified_following")` — expiry rolls only on the venue calendar.
3. `delivery = roll(expiry + pair.spot_offset_days, rtgs_set{base, quote}, "following")` — same as OTC, since cash legs still settle bilaterally.

**Validations:**

- `InvalidOptionStyleError` if `style not in {"OTC", "LISTED"}`.
- `ListedOptionVenueRequiredError` if `style == "LISTED"` and pair has no listed venues.
- `InvalidTenorError` if tenor is `SPOT` / `ON` / `TN` / `SN`.
- Warning `OptionSameDayExpiryWarning` if `expiry_date == spot_date` (unusual; verify intent).
- Listed-option library-sourced caveat is surfaced verbatim from the existing exchange-calendar caveat in `tab_swap.py`.

### 6.4 FX Futures (new — conventions.md §11)

Last trade date and delivery date are anchored independently to the **unrolled 3rd Wednesday** of the contract month — not chained off each other. The two dates can drift apart when 3rd Wed is a holiday on one calendar set but not the other.

| Venue | Last trade date rule | Delivery date rule |
|---|---|---|
| CME (Rule 25102.E for EUR/USD futures; analogous for other FX) | 2 business days before the unrolled 3rd Wed of contract month, on combined CME + base RTGS + quote RTGS. If 9:16 a.m. CT cut day is itself a holiday, roll `preceding`. Time-of-day cut out of scope. | 3rd Wed of contract month, rolled `modified_following` on combined CME + base RTGS + quote RTGS |
| HKEX FX futures | 2 business days before the unrolled 3rd Wed of contract month, on combined HKEX + base RTGS + quote RTGS | Same shape as CME |
| SGX FX futures | 2 business days before the unrolled 3rd Wed of contract month, on combined SGX + base RTGS + quote RTGS | Same shape as CME |

Codified as a single helper `imm_last_trade_date(contract_month, venue_calendar, rtgs_set) -> date` in `conventions/business_day.py`, computed as: take the 3rd Wednesday of `contract_month` (unrolled), step back 2 good business days on the combined calendar set, return the result.

**Contract-month input path:** user picks `(year, month)`. Engine computes unrolled 3rd Wed → independently produces LTD (2 BD back, combined calendars) and delivery (modified-following roll, combined calendars).

**IMM tenor input path:** `from_date` (defaults to today) → `next_imm_date(from_date, imm_index)` → contract month → same as above.

**Validations:**

- `VenueNotListedError` if `venue not in pair.listed_on`.
- `InvalidContractMonthError` if contract month is in the past relative to `from_date` or today.
- Warning `FutureStaleContractWarning` if `last_trade_date < today` (historical query).

## 7. Provenance & result rendering

### 7.1 Contract extension

The existing rule (every holiday paired with `source_url` + `source_doc_title` + `source_fetched_at`) extends unchanged to fixing calendars. No new `source_origin` value — `bundled` / `cache` / `live` stay the only three. Library-sourced data is forbidden from driving calculations, fixing-calendar included.

`tests/test_data_integrity.py` scan list is extended from `{fx_rtgs, fx_exchange}` to `{fx_rtgs, fx_exchange, fx_fixing}`. Same assertions: every holiday resolves to a non-null source; `fetched_at` parses as ISO; the `_raw/` sidecar exists. CI fails if any new fixing calendar fails the contract.

### 7.2 Trace rendering

The existing `_render_trace` helper iterates `step.statuses.items()` and renders per-calendar status with source citations. It works as-is for fixing calendars because `CalendarStatus` already carries the source field regardless of calendar kind.

| Product | Traces rendered |
|---|---|
| Spot / Swap | Spot offset · Near leg · Far leg |
| NDF | Spot offset · Settlement · Fixing |
| Option | Spot offset · Expiry · Delivery |
| Futures | Last trade date · Delivery date |

### 7.3 Calendars-used caption

Every product sub-tab surfaces a `"Calendars to be used: <list>"` caption above the Calculate button.

| Product | Caption shape |
|---|---|
| Spot / Swap (unchanged) | `RTGS: USD (Fedwire) · EUR (TARGET2) [ \| Exchange: CME ]` |
| NDF | `RTGS: USD (Fedwire) \| Fixing: CNY (CFETS USD/CNY Central Parity)` |
| Option (OTC) | `RTGS: USD (Fedwire) · JPY (BoJ-NET)` |
| Option (Listed) | `RTGS: USD (Fedwire) · JPY (BoJ-NET) \| Exchange: CME` |
| Futures | `Exchange: CME \| RTGS: USD (Fedwire) · CNH (HKMA CHATS-CNH)` |

### 7.4 Missing-calendar UX

Same pattern as the existing Spot/Swap tab: when a required calendar is missing, the sub-tab renders a clear `st.error` and disables Calculate.

- NDF on USD/CNY but `fx_fixing/CNY.json` not bundled → error with refresh instructions.
- Option in Listed mode for a pair not listed on any venue → error directing user to OTC mode.
- Futures for a pair not listed on the chosen venue → `VenueNotListedError` surfaced as `st.error`.

## 8. Errors and warnings

Pattern stays uniform across products: narrow `ValueError` subclasses raised by the engine; UI catches them per sub-tab and renders `st.error`. Warnings accumulate into `result.warnings: list[str]` and render via `st.warning`.

### 8.1 New exception types

```python
# ndf.py
class InvalidNdfPairError(ValueError): ...

# option.py
class InvalidOptionStyleError(ValueError): ...
class ListedOptionVenueRequiredError(ValueError): ...

# future.py
class InvalidContractMonthError(ValueError): ...
class VenueNotListedError(ValueError): ...
```

### 8.2 Reused exceptions

- `InvalidTenorError` — bad tenor string.
- `InvalidTradeDateError` — trade date not good on the required calendar set (per product).
- `InvalidBrokenDateError` — broken / maturity target rolls to ≤ spot.
- `CalendarRangeError` — calculation falls outside bundled calendar window. Raised uniformly by RTGS / Exchange / Fixing calendars.

### 8.3 Tenor restrictions per product

| Product | Accepted tenor kinds | Rejected → error |
|---|---|---|
| Spot / Swap (existing) | All | (already correct) |
| NDF | PERIOD, IMM, BROKEN | SPOT / ON / TN / SN → `InvalidTenorError("NDF requires a forward tenor")` |
| Option | PERIOD, IMM, BROKEN | Same as NDF |
| Futures | n/a — input is contract month or `IMM1..IMM4` only | Anything else → `InvalidTenorError` |

### 8.4 Warnings

- **NDF — short fixing horizon.** `fixing_date < trade_date + 2 calendar days` → "Fixing date is within 2 days of trade — confirm with counterparty."
- **Option — same-day expiry.** `expiry_date == spot_date` → "Option expires on spot — unusual; verify intended."
- **Futures — stale contract.** `last_trade_date < today` → "Contract has already expired; this is a historical query."
- **Listed Option library caveat.** Same wording as the existing exchange-calendar library-sourced warning. Reuses `ExchangeCalendar.library_sourced`.
- **NDF library caveat** — not applicable in v1.1: all three fixing calendars are primary-sourced. Tripwire infra is ready for it.

## 9. Library tripwire extension

The existing tripwire (TARGET2 / Fedwire / CHAPS cross-checked against `python-holidays`) stays. A parallel block walks the three fixing calendars against `python-holidays` public holidays for `CN` / `KR` / `TW`. Mismatches emit warnings (not hard fails — fixing calendars legitimately differ from public holidays). Same mechanism, different threshold.

## 10. Testing

### 10.1 New test files

```
tests/
├── test_ndf.py                 # NEW
├── test_option.py              # NEW
├── test_future.py              # NEW
├── test_calendars_fixing.py    # NEW
└── fixtures/
    └── sources/
        ├── cfets_cny/          # NEW — recorded upstream documents
        ├── kftc_krw/           # NEW
        └── taifx_twd/          # NEW
```

### 10.2 Coverage per test file

| Test | What it covers |
|---|---|
| `test_ndf.py` | Tenor-driven & maturity-driven paths · settlement rolls on USD + fixing union · fixing = settlement − 2BD on fixing calendar · rejection of SPOT/ON/TN/SN tenor · rejection of deliverable pair (`InvalidNdfPairError`) · IMM-tenor NDF · short-horizon warning · adjustment-trace fields populated · `InvalidBrokenDateError` when target ≤ spot |
| `test_option.py` | OTC: expiry rolls on full RTGS set, delivery on base+quote only · Listed: expiry rolls on exchange, delivery on RTGS · venue required when style=LISTED · pair-not-listed rejection · EOM rule when spot is last BD of month · same-day-expiry warning · adjustment-trace fields populated |
| `test_future.py` | Contract-month input: delivery = roll(3rd Wed, exchange + RTGS) · last trade = delivery − 2 BD on exchange + RTGS · IMM-tenor input maps to correct contract month · CME / HKEX / SGX produce identical dates given identical pair · venue-not-listed rejection · stale-contract warning |
| `test_calendars_fixing.py` | Fixing JSON loads · `is_holiday(date)` correctness · cache > bundled layering · `CalendarRangeError` raised when query is outside coverage horizon |

### 10.3 Existing-test extensions

- `test_data_integrity.py` — scan list extended to include `fx_fixing/*.json`. Same assertions.
- `test_calendars.py` — fixture entries for the three new fixing calendars to confirm they load through the same loader contract.
- `test_fetchers.py` — recorded-fixture round-trip tests for `cfets_cny.py`, `kftc_krw.py`, `taifx_twd.py`, mirroring the existing `federal_reserve.py`-style test.

All tests fixture-based, deterministic, no network. The library tripwire in §9 is a new assertion block in the existing tripwire test; no separate test file.

## 11. Implementation phases

Six self-contained phases. Each phase ends with tests green so the build is never broken mid-stream.

| Phase | Ships | Touches |
|---|---|---|
| **0. Pair table** | USD/CNY, USD/KRW, USD/TWD added with `ndf=True`. `Pair` dataclass grows `ndf` + `fixing_currency` fields. Existing pairs untouched. | `pairs.py`, `test_pairs.py` |
| **1. Fixing calendar data layer** | New schema (`fx_fixing/<CCY>.json`), loader (`calendars/fixing.py`), three fetchers, data-integrity test extended, sidebar + about-tab wiring. | `calendars/`, `scripts/sources/`, `data/fx_fixing/`, `refresh.py`, tests |
| **2. NDF engine** | `ndf.py` (`NdfResult` + `calculate_ndf_dates`), tenor + maturity paths, validations, `docs/conventions.md` §9. | `ndf.py`, `test_ndf.py`, `docs/conventions.md` |
| **3. Option engine** | `option.py` (`OptionResult` + `calculate_option_dates`), OTC + listed paths, `docs/conventions.md` §10. | `option.py`, `test_option.py`, `docs/conventions.md` |
| **4. Futures engine** | `future.py` (`FutureResult` + `calculate_future_dates`), contract-month + IMM-tenor paths, `docs/conventions.md` §11. | `future.py`, `test_future.py`, `docs/conventions.md` |
| **5. UI restructure** | Top-level tabs collapse to `Calculator / Holidays / About`. Calculator hosts `tab_calculator.py` with four sub-tabs. `tab_swap.py` → `product_spot_swap.py` rename. New `product_ndf.py`, `product_option.py`, `product_futures.py`. About-tab updated. | `ui/`, `run_ui.py` |

Each phase is independently mergeable — engine modules (phases 2–4) work as a library before the UI restructure ships, so a partial release is always coherent.

## 12. References

- v1 design — `docs/superpowers/specs/2026-05-06-fx-holiday-calculator-design.md`
- Sources registry — `docs/data-sources.md`
- Existing conventions — `docs/conventions.md`
- ISDA 1998 FX and Currency Options Definitions §3.2 — option expiration and settlement
- EMTA template terms for CNY / KRW / TWD non-deliverable forwards
- CME Rule 261.01 — FX futures last-trade-day specification
- OpenGamma Strata `FxSwapConvention` (already referenced in `docs/conventions.md`)
