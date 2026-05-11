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

## 3. Pre-spot tenors: ON, TN, SN

| Tenor | Near leg | Far leg | Holiday handling on trade date |
|---|---|---|---|
| **ON** (Overnight) | `T` | `T+1` rolled `following` on RTGS | **Blocked** — `InvalidTradeDateError` if `T` is a weekend or holiday in either RTGS calendar |
| **TN** (Tom-Next) | `T+1` rolled `following` on RTGS | spot | **Warns** if `T` is a weekend or holiday; computation proceeds |
| **SN** (Spot-Next) | spot | `spot+1` rolled `following` on RTGS | No warning (spot is always rolled to a good BD by construction) |

**Why block ON but only warn for TN?** The two cases sit on opposite sides of "universal
market practice":

- **ON** settles at `T+0` in both currencies. If `T` is not a good business day in
  one currency, that currency's cash leg cannot settle on `T` — the trade is
  structurally impossible. This is universal across interbank desks.
- **TN** settles `T+1` against spot. The trade can be agreed today and settled
  tomorrow even if today is a holiday in one currency, **provided** `T+1` is a good
  business day in both currencies (which the near-leg roll guarantees). Practice
  varies: some venues book TN trades on a holiday trade date, others refuse and
  require the customer to wait for the next good business day. Because there is no
  universal rule, the engine permits the trade and surfaces a warning, leaving the
  decision to the user and their counterparty.

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

## 10. FX Option — expiry & delivery

FX options have two characteristic dates:

- **Expiry date** — the day the option contract expires.
- **Delivery date** — the day the cash legs settle if the option is exercised.

Delivery date = `apply_spot_offset(expiry, pair, RTGS{base,quote})` — the
same business-day offset as the swap engine's spot, applied off the expiry
instead of the trade date. Where the dates roll on different calendars
depending on style:

| Style  | Spot anchor calendar set       | Expiry calendar set            | Delivery calendar set      |
|--------|--------------------------------|--------------------------------|----------------------------|
| OTC    | RTGS{base, quote, ref}         | RTGS{base, quote, ref}         | RTGS{base, quote} only     |
| LISTED | RTGS{base, quote}              | Exchange{venue}                | RTGS{base, quote} only     |

The delivery leg deliberately omits the reference currency: the option's
delivery is the physical exchange of two currencies, not a cross-currency
constrained spot.

For the LISTED path the spot anchor also omits the reference currency: the
exchange contract is venue-defined, and the spot used as the base for
`spot + tenor` expiry computation is treated as a bilateral base/quote
concept. The `venue` and `exchange_calendar` arguments must agree
(`exchange_calendar.venue == venue`) — mismatches raise
`VenueCalendarMismatchError` rather than silently computing on the wrong
exchange while labelling the result with the requested venue.

Reference: ISDA 1998 FX and Currency Options Definitions §3.2
(Expiration Date and Settlement Date).

### 10.1 Validations

- `InvalidOptionStyleError` — `style ∉ {OTC, LISTED}`.
- `ListedOptionVenueRequiredError` — `style == LISTED` with no venue
  provided, or venue not in `pair.listed_on`, or no exchange calendar
  provided.
- `VenueCalendarMismatchError` — `style == LISTED` with
  `exchange_calendar.venue != venue`.
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
  outright requires a forward tenor; SPOT trades use the Spot/Swap tab).
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
