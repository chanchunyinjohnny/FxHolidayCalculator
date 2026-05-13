# FX Date Conventions — Holiday Practice

This document explains the holiday-handling and date conventions implemented in the
FX Holiday Calculator's swap engine (`fx_holiday_calculator/swap.py`). The conventions
follow standard interbank FX market practice; where practice is not universal, the
engine takes the more permissive path and surfaces a warning rather than blocking.

For the underlying primary-source holiday data, see [`data-sources.md`](data-sources.md).

## 1. OTC vs listed products

The engine accepts a `calendar_mode` parameter (`FX` | `EXCHANGE` | `BOTH`) that controls
which calendars roll the legs of a swap.

- **OTC products** (over-the-counter spot, ON, TN, SN, FX forwards, FX swaps,
  forward-forward swaps) settle bilaterally and only depend on **RTGS** (real-time
  gross settlement) calendars — TARGET2 for EUR, Fedwire for USD, CHAPS for GBP, etc.
- **Listed products** (CME / HKEX / SGX FX futures and options) trade on an exchange,
  and the exchange's trading calendar can shift fixings and expiries even when the
  underlying RTGS systems are open.

The pre-spot tenors **ON, TN, SN** (and **SPOT** itself) are inherently OTC instruments
— no listed contract represents an "overnight FX swap". For these tenors the engine
**ignores `calendar_mode` and always rolls on RTGS only**, even if the caller passes
`EXCHANGE` or `BOTH`. Exchange calendars only enter the calculation for forward-tenor
legs (PERIOD / IMM / BROKEN) where the user has explicitly requested EXCHANGE or BOTH
mode for listed-product workflows.

## 2. Spot offset

Spot is `T+1` for USD/CAD and `T+2` for all other in-scope pairs. The spot offset
always rolls on the **RTGS** calendar set, never on exchange calendars, because the
spot date is the universal anchor for forward calculations and must be a settleable
date in the relevant cash currencies regardless of which product is being priced.

If the spot candidate falls on a weekend or a holiday in any of the relevant
RTGS calendars (base, quote, and reference currency when not `none`), it is pushed
forward to the next common good business day.

> "If the spot date falls on a holiday of either currency of a pair, then the spot
> date is pushed out to become the next common business day for both currencies of
> the pair." — [Wikipedia, *Foreign exchange date conventions*][wiki-fx-date]

### 2.1 Known limitation — cross-pair intermediate hops vs. reference currency

For non-USD cross pairs (e.g. EUR/JPY) with `ref="USD"`, the engine requires
each **intermediate** day-hop in the T+N count to be a good business day in
all three currencies (base + quote + ref). The textbook market algorithm
(Cao 2008; Bloomberg/Reuters/EBS) is two-pass: count `pair.spot_offset_days`
good BDs on **base + quote only**, then push the candidate spot forward if
it lands on a ref-currency holiday. The two algorithms agree on most
calendars; they diverge when a ref-currency holiday falls strictly *between*
trade and spot (e.g. EUR/JPY trade on a Mon with US July 4 on the following
Tue): convention returns T+2, the engine returns T+3.

This is rare in practice — US holidays predominantly fall on Mondays, where
both algorithms agree — and the engine errs on the side of always producing
a date that is a good BD in every relevant currency. v1.x does not implement
the two-pass algorithm; users who care about the Tue-US-holiday edge case
should cross-check manually for non-USD crosses with `ref="USD"`.

## 3. Pre-spot tenors: ON, TN, SN

| Tenor | Near leg | Far leg | Holiday handling on trade date |
|---|---|---|---|
| **ON** (Overnight) | `T` | `T+1` rolled `following` on RTGS | **Blocked** — `InvalidTradeDateError` if `T` is a weekend or holiday in either RTGS calendar |
| **TN** (Tom-Next) | `T+1` rolled `following` on RTGS | `near+1` rolled `following` on RTGS | **Warns** if `T` is a weekend or holiday; computation proceeds |
| **SN** (Spot-Next) | spot | `spot+1` rolled `following` on RTGS | No warning (spot is always rolled to a good BD by construction) |

The "Next" in **Tom-Next** is the *next business day after tomorrow*, not the
spot date. For T+2 pairs this happens to equal spot (because spot = T+2 =
tomorrow+1 BD when no rolls intervene), which is what the textbook examples
show. The market quotes TN as a real product on every pair, including T+1
pairs — see `USDCAD TN FWD` on Investing.com and equivalent screens on
Bloomberg / Reuters.

### 3.1 TN ≡ SN on T+1 pairs

For T+1 pairs (USD/CAD, USD/MXN, USD/TRY, USD/RUB), `near = T+1 = spot` and
`far = T+2 = spot+1`, so TN and SN refer to the same swap. Interbank screens
quote them at the same rate (cf. `USDCAD TN FWD` and `USDCAD SN FWD` on
Investing.com, both bid -0.6470 ask -0.5270 at 03:08 UTC on a representative
session). The engine returns identical near/far dates for both tenors on
T+1 pairs by construction; it does not raise.

**Why block ON but only warn for TN?** The two cases sit on opposite sides of "universal
market practice":

- **ON** settles at `T+0` in both currencies. If `T` is not a good business day in
  one currency, that currency's cash leg cannot settle on `T` — the trade is
  structurally impossible. This is universal across interbank desks.
- **TN** settles `T+1` against `T+1+1BD`. The trade can be agreed today and
  settled tomorrow even if today is a holiday in one currency, **provided**
  the near and far rolls land on good business days in both currencies (the
  `following` roll guarantees this). Practice varies on whether to book TN
  on a holiday trade date: some venues allow it, others refuse and require
  the customer to wait. Because there is no universal rule, the engine
  permits the trade and surfaces a warning, leaving the decision to the
  user and their counterparty.

**SN** never raises a holiday issue: the near leg equals the spot date, which is
already adjusted to a good business day by the spot offset, and the far leg rolls
forward on RTGS.

## 4. Post-spot tenors: PERIOD, IMM, BROKEN

| Tenor | Far leg construction | Adjustment |
|---|---|---|
| **PERIOD** (`1M`, `3M`, …) | `spot + N units` | End-of-month rule then `modified_following` |
| **IMM** (`IMM1`, …) | 3rd Wednesday of the next IMM month after spot | `modified_following` |
| **BROKEN** (`YYYY-MM-DD`) | user-supplied target date | `modified_following`; rejects `far ≤ spot` |

### 4.1 End-of-month (EOM) rule

If the spot date falls on the last business day of its month, the far leg is rolled
to the last business day of the **target month** (the month `N` months after spot's
month). Otherwise the far leg uses standard `modified_following`.

> "If the spot date is at the last business day of the month, all of the following
> business day calculations are also for the last business day of the month."
> — [Wikipedia, *Foreign exchange date conventions*][wiki-fx-date]

### 4.2 Modified following

Standard FX adjustment: roll forward to the next good business day; if that crosses
into the next month, roll backward to the previous good business day instead.

## 5. Forward-forward swaps (FFS)

A forward-forward swap has two forward legs, both quoted relative to spot. For an
input like `near=1M, far=3M` the engine computes:

- `near_date = spot + 1M` adjusted (modified-following + EOM keyed on spot)
- `far_date = spot + 3M` adjusted (modified-following + EOM keyed on spot)

Both legs are anchored on the **original spot date**, not on the near leg. This
follows the OpenGamma Strata convention:

> "[`createTrade`] returns a trade based on the specified periods, **starting from
> the spot date**. For example, a '3M x 6M' FX swap has a period from spot to the
> start date of 3 months and a period from spot to the end date of 6 months."
> — [OpenGamma Strata, `FxSwapConvention`][strata-fxswap]

This contrasts with QuantLib's `FxSwapRateHelper` which takes a single tenor and
computes `far = near + tenor`, anchoring EOM on the near leg
([QuantLib `ratehelpers.cpp`][ql-ratehelpers]). The two libraries model FFS through
different APIs; the underlying market convention — "both periods quoted from spot"
— is the same one that interbank desks use when they show a `1M vs 3M` swap.

FFS validations:

- Both legs must be forward tenors (PERIOD / IMM / BROKEN). ON / TN / SN / SPOT
  are rejected as legs of an FFS (`InvalidFFSCombinationError`).
- `near_date` must be strictly after `spot_date` (catches BROKEN near legs that
  roll to ≤ spot).
- `far_date` must be strictly after `near_date`.

## 6. Cross rule

When a swap involves a non-USD pair and a reference currency is specified, the spot
date must be a good business day in **all three** RTGS calendars (base + quote +
reference). For example, `EUR/JPY` with `ref=USD` rolls against TARGET2, BOJ, and
Fedwire combined. With `ref=none` the third constraint is dropped.

## 7. Where these choices show up in code

- Spot offset and RTGS-only rolling: `fx_holiday_calculator/conventions/spot_offset.py`
- OTC tenor RTGS override: `fx_holiday_calculator/swap.py` (the `otc_only` branch)
- ON hard block: `fx_holiday_calculator/swap.py` (`InvalidTradeDateError` in the ON branch)
- TN warning: `fx_holiday_calculator/swap.py` (appends to `SwapResult.warnings` in the TN branch)
- EOM rule: `fx_holiday_calculator/conventions/business_day.py` (`apply_eom_with_trace`)
- FFS invariants: `fx_holiday_calculator/swap.py` (FFS branch — checks `near > spot` and `far > near`)

## 8. References

- [Wikipedia — Foreign exchange date conventions][wiki-fx-date]
- [Wikipedia — Foreign exchange swap][wiki-fx-swap]
- [Wikipedia — Spot date][wiki-spot-date]
- [OpenGamma Strata — `FxSwapConvention`][strata-fxswap]
- [QuantLib — `ratehelpers.cpp` (`FxSwapRateHelper`)][ql-ratehelpers]
- [QuantLib — Dates and Conventions documentation][ql-dates]

[wiki-fx-date]: https://en.wikipedia.org/wiki/Foreign_exchange_date_conventions
[wiki-fx-swap]: https://en.wikipedia.org/wiki/Foreign_exchange_swap
[wiki-spot-date]: https://en.wikipedia.org/wiki/Spot_date
[strata-fxswap]: https://strata.opengamma.io/apidocs/com/opengamma/strata/product/fx/type/FxSwapConvention.html
[ql-ratehelpers]: https://github.com/lballabio/QuantLib/blob/master/ql/termstructures/yield/ratehelpers.cpp
[ql-dates]: https://quantlib-python-docs.readthedocs.io/en/latest/dates.html

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
- CFETS market notices (chinamoney.com.cn) — primary source for CNY
  fixing-calendar data. v1.1 ships with a `python-holidays`-sourced
  stopgap (`scripts/sources/library_fixing.py`); the primary fetcher
  `scripts/sources/cfets_cny.py` awaits a successful first live run
  from an unrestricted network environment.
- KFTC FX market trading calendar (kftc.or.kr) — primary source for KRW
  fixing-calendar data. v1.1 ships with a `python-holidays`-sourced
  stopgap; the primary fetcher `scripts/sources/kftc_krw.py` awaits a
  successful first live run.
- Taipei Forex Inc. (tpefx.com.tw) — primary source for TWD
  fixing-calendar data. v1.1 ships with a `python-holidays`-sourced
  stopgap; the primary fetcher `scripts/sources/taifx_twd.py` awaits a
  successful first live run.

## 10. FX OTC Option — expiry & delivery

> Listed FX options are documented in §10A and use a separate contract-lookup engine (`fx_holiday_calculator.options`).

FX OTC options have two characteristic dates:

- **Expiry date** — the day the option contract expires.
- **Delivery date** — the day the cash legs settle if the option is exercised.

Delivery date = `apply_spot_offset(expiry, pair, RTGS{base,quote})` — the
same business-day offset as the swap engine's spot, applied off the expiry
instead of the trade date.

| Calendar set       | Expiry                         | Delivery                   |
|--------------------|--------------------------------|----------------------------|
| OTC                | RTGS{base, quote, ref}         | RTGS{base, quote} only     |

The delivery leg deliberately omits the reference currency: the option's
delivery is the physical exchange of two currencies, not a cross-currency
constrained spot.

### 10.1 Validations

- `InvalidTenorError` — tenor is SPOT / ON / TN / SN (option requires
  a forward tenor).

### 10.2 Warnings

- *Same-day expiry* — `expiry_date == spot_date` (rare; usually a
  user-error verifying a zero-day broken-date option). Surfaced via
  `result.warnings`.

### 10.3 Where this lives

- Engine: `fx_holiday_calculator/option_otc.py`
- Tests: `tests/test_option_otc.py`

## 10A. FX Listed Option — contract lookup

Listed FX options trade as fixed-month contracts. The user picks a venue and
a contract code; expiry and delivery dates are read from the venue's bundled
contract listings, not derived at lookup time.

### 10A.1 Data flow

- Refresh time: `scripts/sources/{venue}_options_contracts.py` calls
  `fx_holiday_calculator.option_listed.derive_contract(...)` to compute
  `(expiry_date, delivery_date)` per (pair, contract month). Results are
  written to `data/fx_exchange/{VENUE}_options_contracts.json` with
  `derivation_mode = "derived"` and a `note` citing the venue's rule.
- Runtime: the Listed Option tab calls `fx_holiday_calculator.options.get_contract(venue, code)`
  (and friends — `list_venues()`, `list_contracts()`, `days_until()`).

### 10A.2 Expiry rule

`derive_contract` counts 2 good business days backward from the unrolled
3rd Wednesday of the contract month, on the venue's exchange calendar. Two
spec wordings exist:

- **CME** option-on-FX-future: "Trading terminates on the second business
  day prior to the third Wednesday of the contract month" — anchored on
  the UNROLLED 3rd Wed.
- **HKEX** CNHO-S-2 (USD/CNH Options): "Expiry Day: Two Trading Days prior
  to the Final Settlement Day" where FSD = "the third Wednesday of the
  Contract Month. If it is not a Business Day, the Final Settlement Day
  shall be the next Business Day" — anchored on the ROLLED FSD.

These wordings produce IDENTICAL dates in every case (the chain of non-BDs
between unrolled 3rd Wed and rolled FSD is traversed by the 2-BD back-count
regardless of the anchor). `derive_contract` uses the unrolled anchor as
the canonical form and surfaces the spec citation in
`DeriveContractResult.spec_cite`.

SGX FX-options expiry wording is not separately verified in v1.x; the same
algorithm is used with a caveat in the citation string.

### 10A.3 Delivery rule

Delivery = expiry + `pair.spot_offset_days` good business days on
RTGS{base, quote}. Reference currency does not enter the listed-contract
path (cash legs are bilateral).

### 10A.4 Validations

- `ContractMonthDerivationError` — raised at refresh time by
  `derive_contract` when venue ∉ `pair.listed_on`, when
  `exchange_calendar.venue ≠ venue`, or when `contract_month` is in the
  past (override with `from_date` for backtests).
- `ContractNotFoundError` — raised at runtime by `options.get_contract`
  when `(venue, code)` does not exist in the bundled JSON.

### 10A.5 Implementation files

- Derivation: `fx_holiday_calculator/option_listed.py`
- Lookup facade: `fx_holiday_calculator/options.py`
- Refreshers: `scripts/sources/{cme,hkex,sgx}_options_contracts.py`
- Tests: `tests/test_option_listed.py`, `tests/test_options.py`

## 11. FX Futures — last trade date & delivery date

FX futures are exchange-listed contracts with two characteristic dates:

- **Delivery date** — the 3rd Wednesday of the contract month, rolled
  `modified_following` on the combined exchange + base RTGS + quote RTGS
  calendar set.
- **Last trade date** — 2 good business days before the **unrolled** 3rd
  Wednesday, on the same combined set.

The LTD anchor is the unrolled 3rd Wednesday — not the rolled delivery
date. When 3rd Wed is a holiday and delivery rolls forward, LTD remains
anchored to the original IMM date and does not chain off delivery.

**Verified across all three v1.x venues:**

- **CME** (e.g. 6E EUR/USD, Chapter 261): "Trading terminates at 9:16 a.m.
  CT on the second business day prior to the third Wednesday of the
  contract month." Final settlement on the 3rd Wed.
- **HKEX** USD/CNH Futures (CUS, July 2022 infosheet): *Last Trading Day* =
  "Two Trading Days prior to the third Wednesday of the Contract Month"
  (unrolled-3rd-Wed anchor); *Final Settlement Day* = "The third Wednesday
  of the Contract Month".
- **SGX** USD/SGD Futures: "Two business days prior to 3rd Wednesday of
  the contract month" (per published contract specs).

All three exchanges use the same unrolled-3rd-Wed anchor for LTD, so a
single implementation suffices. The 9:16 a.m. CT (CME) and 11:00 a.m. HKT
(HKEX) intraday cut-offs are out of v1.x scope.

> **HKEX listed options (CUS).** HKEX *options* spec (CNHO-S-2) words the
> rule as "Two Trading Days prior to the Final Settlement Day" where FSD =
> 3rd Wed rolled to next BD. This is *mathematically equivalent* to the
> CME wording "2 BDs prior to the third Wednesday" — the 2-BD back-count
> absorbs the chain of non-BDs between unrolled imm and rolled FSD. The
> listed-option IMM engine handles both wordings via one algorithm; see
> §10A.2 above.

### 11.1 Input modes

- **Contract month** — user supplies `(year, month)` directly.
- **IMM tenor** — user supplies `IMM1..IMM4` plus an optional `from_date`
  (defaults to today). The contract month is resolved via
  `next_imm_date(from_date, imm_index)`.

### 11.2 Validations

- `VenueNotListedError` — pair is not listed on the chosen venue.
- `VenueCalendarMismatchError` — `exchange_calendar.venue != venue`.
- `InvalidContractMonthError` — contract month is in the past *or* the
  computed last trade date is in the past, both relative to today
  (skipped when `from_date` is supplied as an explicit backtest override).
- `InvalidTenorError` — `imm_tenor` is supplied but not an IMM kind.

### 11.3 Warnings

- Past contracts are rejected outright via `InvalidContractMonthError`
  when `from_date is None`; there is no stale-contract warning path.
  Historical queries are allowed via an explicit `from_date`.

### 11.4 Where this lives

- Engine: `fx_holiday_calculator/future.py`
- LTD helper: `fx_holiday_calculator/conventions/business_day.py`
  (`imm_last_trade_date`)
- Tests: `tests/test_future.py`

## 12. FX Forward outright

A forward outright is a single-leg trade: agree today, settle once on the
forward date. Mathematically the date math is identical to a standard swap
with no near tenor (see §1–§5) — the engine reuses `calculate_swap_dates`'s
PERIOD/IMM/BROKEN branch and discards the implicit near leg.

### 12.1 Date relations

- **Spot date** = `T + pair.spot_offset_days` on RTGS{base, quote, ref}.
  The spot date is a reference value for the forward calculation; for an
  outright there is no actual settlement at spot.
- **Settlement date** = `spot + tenor`, rolled `modified_following` on the
  selected calendar set (RTGS / Exchange / Both). EOM rule applies keyed
  on spot.

### 12.2 Validations

- `InvalidForwardTenorError` — tenor is SPOT / ON / TN / SN (forward
  outright requires a forward tenor; SPOT trades use the Spot tab, and
  ON/TN/SN use the Swap tab).
- `InvalidBrokenDateError` — rolled settlement ≤ spot (raised from the
  underlying swap engine).
- `InvalidTradeDateError` — propagated from the swap engine for invalid
  trade dates.

### 12.3 Where this lives

- Engine wrapper: `fx_holiday_calculator/forward.py`
- Underlying engine: `fx_holiday_calculator/swap.py` (PERIOD/IMM/BROKEN
  branch with `near_tenor=None`)
- Tests: `tests/test_forward.py`
- UI: `fx_holiday_calculator/ui/product_forward.py`

## 13. Per-pair conventions and the default reference currency

Some market conventions are pair-specific (e.g. USD/CAD's T+1 spot lag,
EUR/USD's split-settlement carve-out for US-only holidays). Rather than
hard-coding these in the engine or UI, the `Pair` dataclass carries
documented metadata so each convention can be surfaced with its own
primary source.

### 13.1 Data model

```python
@dataclass(frozen=True)
class ConventionSource:
    url: str
    doc_title: str
    documented_at: datetime  # when the project last verified the citation

@dataclass(frozen=True)
class PairConvention:
    rule: str
    description: str
    source: ConventionSource
    engine_divergence_note: str | None = None  # set when engine doesn't enforce the convention

@dataclass(frozen=True)
class Pair:
    # ... existing fields ...
    default_ref_currency: str | None = None
    ref_currency_source: ConventionSource | None = None
    conventions: tuple[PairConvention, ...] = ()
```

`ConventionSource` is intentionally distinct from the bundled-data
`SourceRef` type. Bundled data is parsed from a published calendar PDF /
HTML; pair conventions are documented market practice and cite a market
reference (FX Global Code, CFEC, CLS Group, etc.).

### 13.2 Default reference currency

`default_ref_currency` codifies the per-pair "third-currency rule" — the
calendar consulted for settlement in addition to the two leg currencies.

The defaulting rule used by `pairs._add`:

- If the caller passes `default_ref_currency` explicitly, that wins.
- Otherwise, **non-USD crosses default to USD** (per FX Global Code, the
  USD calendar is the canonical third currency).
- Pairs where USD is already a leg get `default_ref_currency=None` —
  USD's calendar is consulted as a leg by construction, and no separate
  third-currency check applies.
- NDF pairs get `default_ref_currency=None` — NDF spot rolls on USD only
  per §9.

The UI uses this field to drive the reference-currency picker:

- `None`, or `default_ref_currency` matches one of the two legs → the
  picker is hidden and `ref="none"` is fixed.
- Otherwise → picker shows `["none", default_ref, …extras]` and defaults
  to `default_ref`. If the user picks a different ref, the UI surfaces a
  warning that they diverged from the documented default.

### 13.3 Documented conventions in v1.x

| Pair    | Rule                                      | Enforced by engine? | Source                                                  |
|---------|-------------------------------------------|---------------------|---------------------------------------------------------|
| USD/CAD | T+1 spot lag                              | **Yes** (§2)        | [Canadian FX Committee — Market Practices][cfec]        |
| EUR/USD | Split-settlement on US-only holidays      | **No** — informational | [CLS Settlement — Currency Operating Hours][cls]     |

The USD/CAD T+1 rule is enforced by the spot-offset engine (see §2). The
new `PairConvention` entry attaches the primary-source citation so the
UI can surface *why* USD/CAD is T+1.

The EUR/USD split-settlement carve-out is **not** enforced by the engine
in v1.x — the engine still treats US holidays as moving the EUR/USD spot
date (full-shift). The `PairConvention` entry has a non-null
`engine_divergence_note`, which causes the UI to render the entry as a
prominent yellow warning box (rather than plain informational text) so
the user knows the displayed dates may diverge from desk booking
practice. Implementing the engine side (per-currency settle dates) is
deferred — the warning route is sufficient for v1.x because the typical
Hong Kong use case (USD/HKD, USD/CNH, NDFs) doesn't hit split-settlement
in the first place.

[cfec]: https://www.bankofcanada.ca/markets/canadian-foreign-exchange-committee/
[cls]: https://www.cls-group.com/products/settlement/clssettlement/

### 13.4 UI surfacing

Two widgets in `fx_holiday_calculator/ui/_widgets.py` consume this
metadata:

- `render_reference_status(pair, selected_ref, named_traces)` — per
  derived date (spot offset / settlement / near leg / far leg / expiry /
  delivery), reports whether the chosen ref calendar was consulted and
  whether it actually moved the date. Lists the ref-currency holidays
  that caused any rejections in the calculation window.
- `render_pair_conventions(pair)` — renders each `PairConvention` entry
  (rule, description, source link). No-op if `pair.conventions` is
  empty.

Both render under the "Adjustment trace" block on each product tab so
the user sees the trace, the per-date ref-calendar verdict, and the
documented conventions side-by-side.

### 13.5 Where this lives

- Model: `fx_holiday_calculator/pairs.py`
  (`ConventionSource`, `PairConvention`, `Pair.default_ref_currency`,
  `Pair.ref_currency_source`, `Pair.conventions`)
- UI widgets: `fx_holiday_calculator/ui/_widgets.py`
  (`render_reference_status`, `render_pair_conventions`)
- Consumers: every product tab (`product_spot.py`, `product_swap.py`,
  `product_forward.py`, `product_ndf.py`, `product_otc_option.py`,
  `product_listed_option.py`, `product_futures.py`, `tab_holidays.py`)
