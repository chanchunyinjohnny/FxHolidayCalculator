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
