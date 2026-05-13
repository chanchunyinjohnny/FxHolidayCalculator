# Split FX Option Tab Into OTC and Listed — Design

**Date:** 2026-05-13
**Author:** Chan Chun Yin Johnny
**Status:** Approved (brainstorming complete; pending implementation plan)
**Builds on:** `docs/superpowers/specs/2026-05-11-fx-products-ui-engine-design.md`
**License:** MIT

---

## 1. Purpose

The current "FX Option" tab covers both OTC and listed options behind a single OTC/LISTED radio with a tenor-driven input. That conflates two products with different trading conventions:

- **OTC options** are quoted and traded by **tenor** (1W / 1M / 3M / IMM / broken date). Expiry is derived from spot + tenor on RTGS{base, quote, ref}; delivery = expiry + spot offset on RTGS{base, quote}. This is the ISDA 1998 FX & Currency Options Definitions §3.2 convention and is correctly handled by the current engine's OTC branch.

- **Listed options** trade as fixed-contract-month products like FX futures — the user picks a contract code with a published last trading day and delivery date. The current engine approximates this by accepting a tenor and rolling on the venue calendar; for IMM tenors it does the right "2 BDs prior to 3rd Wed" math, but the tenor-input UI fiction does not match how a trader actually picks a listed-option contract.

This design splits the single tab into two sibling tabs — **FX OTC Option** and **FX Listed Option** — and refactors the engine to match. The Listed tab mirrors the Futures tab's exchange → pair → contract picker pattern, with contract dates pre-derived into `{VENUE}_options_contracts.json` files (same `derived` provenance pattern the futures contract files already use).

## 2. Non-goals

- **Listed-option weekly / serial / EOM products.** v1 covers monthly contracts only (the listed-option analog of the monthly futures already shipped). Weeklies and non-IMM monthlies are a documented v1.x gap.
- **Strike / put-call / contract-size data.** The Listed Option tab is a *date* calculator; it does not surface strikes or option chains. One JSON entry per (venue, pair, contract month) — strike-level granularity is out of scope.
- **Cut times** (NY 10am, Tokyo 3pm, London 4pm). Already excluded by the parent design and still excluded here.
- **OTC engine functional changes.** The OTC math is correct today; this redesign removes its LISTED branch but does not alter how OTC dates are computed.
- **Live exchange scraping for listed-option contracts.** v1 derives contracts from each venue's documented expiry rule (the (C) hybrid agreed during brainstorming). True-fetch per venue is a v1.x improvement, not a v1 requirement.
- **Listed-option support on venues other than CME, HKEX, and SGX.** Same venue set as Futures.
- **A parallel `pair.options_listed_on` field.** Venue discovery is data-driven from the JSON files (see §5.2).

## 3. UI

### 3.1 Sidebar order

```
Spot · Swap · Forward · NDF · FX OTC Option · FX Futures · FX Listed Option · Holidays
```

OTC products (Spot, Swap, Forward, NDF, FX OTC Option) are grouped first; listed products (FX Futures, FX Listed Option) are grouped together at the end before Holidays. FX Futures precedes FX Listed Option in the listed group because Futures shipped first and is the more familiar entry point; FX Listed Option sits adjacent so the user can move between the two listed-product workflows without crossing back through the OTC group.

### 3.2 FX OTC Option tab

Inputs:

- Trade date
- Pair (any pair from the existing pair registry)
- Tenor (PERIOD / IMM / BROKEN — same tenor model as today)
- Reference currency for cross-spot anchor (default USD)

Outputs:

- Spot date, expiry date, delivery date
- Reasoning bullets (style anchor, expiry roll, delivery roll)
- Per-leg adjustment traces
- Provenance (calendars used, with source URLs)

This is the existing OTC code path, unchanged in behaviour. Only the LISTED branch and venue/exchange-calendar plumbing are removed.

### 3.3 FX Listed Option tab

Mirrors the FX Futures tab's input shape:

- Venue picker — populated from the set of `{VENUE}_options_contracts.json` files that exist *and* contain at least one entry for the selected pair (see §5.2). v1 candidates: CME, HKEX, SGX.
- Pair picker — filtered to pairs that have at least one contract in the chosen venue's options-contracts JSON.
- Contract picker — list of contracts for (venue, pair), each row showing contract code, contract month, and expiry date. Sort ascending by contract month; default selection = nearest contract whose expiry is on or after today.

Outputs:

- Contract code, contract month, product name
- Expiry date, delivery date
- Days-to-expiry countdown (business days on venue ∪ RTGS{base, quote}; calendar days)
- Provenance (`source_url`, `source_doc_title`, `source_fetched_at`, `derivation_mode`, `note`)
- Caveat banner when `derivation_mode == "derived"` (the v1 default) reminding the user to verify against the official contract specs page before trading

No tenor input. No reference-currency input. The contract picker is the only date-driving input.

## 4. Engine module structure

The existing pattern in the codebase splits derivation math from runtime lookup across two files (e.g., `future.py` does the math; `futures.py` is the read-only lookup facade over `{VENUE}_contracts.json`). Listed options follow the same pattern. OTC stays a pure-math module.

### 4.1 New / renamed modules

| Module | Role | Replaces / mirrors |
|---|---|---|
| `fx_holiday_calculator/option_otc.py` | OTC option date math (tenor → expiry → delivery). Single public entry point: `calculate_otc_option_dates(...)`. | Replaces the OTC half of today's `option.py`. |
| `fx_holiday_calculator/option_listed.py` | Listed-option derivation math. Single public entry point: `derive_contract(venue, pair, contract_month, exchange_calendar, rtgs_calendars) -> ContractEntry`. Invoked at refresh time by the per-venue scripts, not at UI time. | Replaces the LISTED half of today's `option.py`. Mirrors `future.py`. |
| `fx_holiday_calculator/options.py` | Listed-option lookup facade. Public surface: `list_venues()`, `list_contracts(venue, pair=None, asof=None, include_expired=False)`, `get_contract(venue, code)`, `days_until(contract, asof)`. Reads `{VENUE}_options_contracts.json`. | Mirrors `futures.py`. |

### 4.2 Deletions

- `fx_holiday_calculator/option.py` — deleted outright (no deprecation shim, per standing preference against backward-compat shims).
- `OptionStyle` literal type, `InvalidOptionStyleError`, `ListedOptionVenueRequiredError`, `VenueCalendarMismatchError` — deleted from the option engine. OTC has no styles; Listed has its own errors (see §4.3). `VenueCalendarMismatchError` continues to live in `future.py` for the futures path.
- Test cleanup is part of this step (not an afterthought): every reference to `style=`, `InvalidOptionStyleError`, `ListedOptionVenueRequiredError`, the LISTED branch, and `OptionResult.style` is removed from the option test files when they're split (see §9). Tests that exercised the LISTED branch of `option.py` are rewritten under `tests/test_option_listed.py` to exercise `option_listed.derive_contract(...)` instead — the LISTED test cases do not disappear, they migrate.

### 4.3 Listed-option errors

Defined in `option_listed.py` (for derivation) and `options.py` (for lookup):

- `ContractNotFoundError` — raised by `options.get_contract(...)` when (venue, code) does not exist.
- `ContractMonthDerivationError` — raised by `option_listed.derive_contract(...)` when inputs are inconsistent (e.g., venue not in `pair.listed_on`, exchange calendar venue mismatch, contract month already in the past).

Both inherit from `ValueError` to match the existing convention in `future.py` / `futures.py`.

### 4.4 OTC engine simplifications

After the LISTED branch is removed, `option_otc.py`:

- No longer takes `style`, `venue`, or `exchange_calendar` arguments.
- Drops the spot-anchor branching (`ref_currency if style == "OTC" else "none"`); the OTC path always uses the ref-aware calendar set.
- Drops the `_listed_imm_expiry` helper (moves to `option_listed.py`).
- Result type `OptionResult` drops the `style: OptionStyle` field.

Net: the OTC engine is single-purpose and noticeably smaller.

## 5. Data layout

### 5.1 File naming

```
data/fx_exchange/CME_options_contracts.json
data/fx_exchange/HKEX_options_contracts.json
data/fx_exchange/SGX_options_contracts.json   # conditional — see §6.3
```

Sits alongside the existing futures contract files (`CME_contracts.json` etc.) in the same directory. The `_options_contracts.json` suffix disambiguates and lets the lookup facade discover venues by globbing the directory.

### 5.2 Venue discovery

`options.list_venues()` returns the set of venues `V` such that `data/fx_exchange/{V}_options_contracts.json` exists and contains at least one contract entry. The UI venue picker calls this. Pair filtering inside a venue is similarly data-driven: a pair appears in the pair picker iff the venue's JSON contains at least one contract for that pair.

This means:

- No parallel `pair.options_listed_on` field on the `Pair` model.
- If the SGX implementation step (§6.3) concludes that SGX has no listed USD/CNH option product, `SGX_options_contracts.json` simply does not exist, and SGX does not appear in the Listed Option venue picker. The user is never confused by an empty venue.

### 5.3 JSON schema

Per-venue file structure (one JSON object per venue):

```json
{
  "schema_version": 1,
  "venue": "CME",
  "calendar_kind": "EXCHANGE_OPTIONS_CONTRACTS",
  "valid_from": "YYYY-MM-DD",
  "valid_until": "YYYY-MM-DD",
  "default_source": {
    "url": "https://www.cmegroup.com/markets/fx.html",
    "doc_title": "CME Group — FX Options Contract Specifications",
    "fetched_at": "YYYY-MM-DDTHH:MM:SSZ",
    "fetcher": "scripts/sources/cme_options_contracts.py@v1",
    "default_derivation_mode": "derived"
  },
  "contracts": [
    {
      "code": "<venue-defined contract code>",
      "pair": "EUR/USD",
      "product_name": "Options on Euro FX Futures",
      "contract_month": "2026-06",
      "expiry_date": "2026-06-05",
      "delivery_date": "2026-06-09",
      "derivation_mode": "derived",
      "source": null,
      "note": "Derived from CME's standard rule (expiry = 2 BDs prior to 3rd Wed of contract month on CME calendar; delivery = expiry + spot offset on RTGS{base,quote}). Verify against the official contract specs page before trading."
    }
  ]
}
```

Schema differences from `{VENUE}_contracts.json`:

- `last_trading_day` → `expiry_date` (option-native terminology, matching the OTC engine, the UI labels, and `docs/conventions.md §10`).
- `settlement_date` → `delivery_date` (same rationale).
- `first_notice_day` is omitted (not applicable to options).
- `calendar_kind` is `"EXCHANGE_OPTIONS_CONTRACTS"` (vs `"EXCHANGE_CONTRACTS"` for futures), letting the loader distinguish the two file types unambiguously.

All other fields and the `default_source` block are structurally identical to the futures contract files. The loader in `options.py` translates the option-native field names into the same `ContractEntry`-like dataclass the futures lookup already uses, so consumers of both lookups see compatible shapes.

### 5.4 Refresh scripts

One script per venue, mirroring the futures refresher layout:

```
scripts/sources/cme_options_contracts.py
scripts/sources/hkex_options_contracts.py
scripts/sources/sgx_options_contracts.py   # conditional — see §6.3
```

Each script:

1. Loads the venue's exchange calendar and the RTGS calendars for each pair's base/quote currencies.
2. For each (venue, pair) in the v1 scope (§6), iterates contract months from `today` to `today + horizon` (horizon to match the futures refresher; same value).
3. Calls `option_listed.derive_contract(...)` to compute `(expiry_date, delivery_date)`.
4. Writes the resulting list of contracts plus a `default_source` block to `data/fx_exchange/{VENUE}_options_contracts.json`.

Refresh scripts are invoked the same way as the futures refreshers (via the existing `scripts/refresh.py` / `fx_holiday_calculator.refresh` entry points).

## 6. v1 scope

### 6.1 Pair × venue matrix

| Venue | Pair | Product (descriptive) | Source verification |
|---|---|---|---|
| CME | EUR/USD | Options on Euro FX Futures | CME FX options chapter, already cited in `docs/conventions.md §10.0` |
| CME | GBP/USD | Options on British Pound Futures | Same CME chapter |
| CME | USD/JPY | Options on Japanese Yen Futures | Same CME chapter |
| CME | AUD/USD | Options on Australian Dollar Futures | Same CME chapter |
| CME | USD/CAD | Options on Canadian Dollar Futures | Same CME chapter |
| CME | USD/CHF | Options on Swiss Franc Futures | Same CME chapter |
| CME | NZD/USD | Options on New Zealand Dollar Futures | Same CME chapter |
| HKEX | USD/CNH | USD/CNH Options (CNHO) | HKEX CNHO-S-2 spec, already cited in `docs/conventions.md §10.0` |
| SGX | USD/CNH | (verified at implementation time — see §6.3) | sgx.com — verify product line exists before scripting |

### 6.2 Contract codes

Codes are venue-defined and populated by the refresher scripts. The spec does not pre-commit to specific code strings; each refresher derives them from the venue's documented coding convention (CME uses month/year codes appended to a product root; HKEX uses a similar pattern). If a venue does not publish a stable code scheme for monthly options, the refresher falls back to `{PRODUCT_ROOT}-{YYYY-MM}` and documents the choice in the script's docstring.

### 6.3 SGX verification step

Before implementing `scripts/sources/sgx_options_contracts.py`, the implementer verifies on sgx.com whether SGX lists a USD/CNH options product (distinct from USD/CNH futures):

- **If yes:** wire the refresher up, cite the SGX spec URL in `default_source`, derive monthlies the same way as CME / HKEX.
- **If no:** the SGX refresher is not built. `SGX_options_contracts.json` does not exist. SGX does not appear in the Listed Option venue picker for any pair. The v1.x backlog gets a single line: "verify whether SGX has added listed FX options."

Either outcome is acceptable for v1 completion; the spec does not depend on which one obtains.

## 7. Provenance contract

Unchanged from the parent design. Every contract entry in `{VENUE}_options_contracts.json` carries:

- A non-null `source` (either an entry-specific source dict, or `null` to inherit from `default_source` — same convention as the futures contract files).
- A non-null `derivation_mode` (`"derived"` for v1; `"scrape"` and `"manual"` reserved for v1.x).
- A non-null `note` when `derivation_mode == "derived"`, citing the rule used.

The data-integrity test (`tests/test_data_integrity.py`) gets new cases ensuring the same contract is enforced for `_options_contracts.json` files (see §9).

## 8. Documentation updates

- `docs/conventions.md §10` — revise to describe the OTC-only engine. The IMM-LISTED derivation discussion stays in the doc but moves to a new `§10A` titled "Listed FX Options — contract lookup", which describes the JSON-driven flow.
- `docs/data-sources.md` — add three new entries (one per venue) under a new "Listed FX options contract sources" section, citing the upstream URL and refresher script per venue.
- `docs/superpowers/specs/2026-05-11-fx-products-ui-engine-design.md` — add an amendment header pointing to this spec, analogous to the 2026-05-12 spot/swap-split amendment header.

## 9. Tests

- `tests/test_option.py` — split into `tests/test_option_otc.py` (the existing OTC cases, with `style=` arguments removed) and `tests/test_option_listed.py` (new — covers `option_listed.derive_contract(...)` math and error paths).
- `tests/test_options.py` — new. Covers the `options.py` lookup facade: `list_venues()`, `list_contracts()`, `get_contract()`, `days_until()`, error paths (`ContractNotFoundError`).
- `tests/test_data_integrity.py` — new cases enforcing the provenance contract on every `_options_contracts.json` file.
- `tests/test_ui_*.py` — Streamlit smoke tests for the two new product tabs (mirroring the existing `product_futures.py` smoke test pattern).

## 10. Out-of-scope follow-ups

- Listed-option weeklies / serials / EOM products.
- True-fetch (scrape) refreshers per venue, replacing the derived-only v1 path.
- `derivation_mode == "scrape"` and `"manual"` support in the lookup and UI caveat banner.
- Listed-option support on additional venues (ICE, EUREX, TFX).
- Strike-level / put-call / contract-size data in the JSON or UI.

These are noted here so they don't get pulled into the v1 implementation plan.
