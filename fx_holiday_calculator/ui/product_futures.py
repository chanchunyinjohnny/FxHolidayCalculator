"""Futures product sub-tab — listed-contract lookup.

Replaces the earlier tenor-driven futures tab. The new flow mirrors a market
maker's actual workflow: pick an exchange, pick a contract from the venue's
published listings, get its key dates plus business-days-remaining against
an as-of date.

Per-contract provenance is surfaced as a badge:
- ``scrape``  → grey "scraped from venue page" (no warning).
- ``derived`` → yellow warning; the row was generated from the venue's
  standard rule because the live scrape failed or did not cover this month.
- ``manual``  → blue "manual override" chip; a maintainer curated this row.

The derivation logic itself lives in ``scripts/sources/<venue>_contracts.py``
(invoked by the fetcher path) and ``fx_holiday_calculator/future.py``. The
UI consumes already-resolved ``ContractEntry`` rows from
``fx_holiday_calculator.futures``.
"""

from datetime import date

import streamlit as st

from fx_holiday_calculator.futures import days_until, list_contracts, list_venues


def _render_provenance(contract) -> None:
    src = contract.source
    mode = contract.derivation_mode
    if mode == "derived":
        st.warning(
            "Derived from venue rule — not scraped from the official contract "
            "page. Verify before trading. If this contract has non-standard "
            "key dates, add a manual override to the JSON."
        )
    elif mode == "manual":
        st.info("Manual override — dates curated by a maintainer.")
    # Provenance caption is shown for all modes so the user can audit.
    badge = {"scrape": "scrape", "derived": "derived ⚠", "manual": "manual"}[mode]
    st.caption(
        f"Source: [{src.doc_title}]({src.url}) — fetched "
        f"{src.fetched_at:%Y-%m-%d}  ·  derivation: `{badge}`"
    )


def render() -> None:
    st.subheader("FX Futures — listed contract lookup")
    st.caption(
        "Pick an exchange, then a listed contract. Dates come from the venue's "
        "published contract calendar where possible. Rows derived from the "
        "venue's standard rule carry a yellow warning."
    )

    venues = list_venues()
    if not venues:
        st.warning(
            "No exchange contract-listings files bundled. Run "
            "`python -m fx_holiday_calculator.refresh` to generate them."
        )
        return

    venue = st.radio("Exchange", venues, horizontal=True, key="fut_v2_venue")

    # Pair filter — discovered from contracts actually present on this venue.
    try:
        all_contracts = list_contracts(venue, include_expired=True)
    except FileNotFoundError as exc:
        st.error(f"Contract-listings file missing for {venue}: {exc}")
        return
    if not all_contracts:
        st.info(f"No contracts bundled for {venue}.")
        return

    pair_options = ["Any"] + sorted({c.pair for c in all_contracts})
    pair_filter = st.selectbox("Pair (optional)", pair_options, key="fut_v2_pair")

    include_expired = st.checkbox("Include expired contracts", value=False, key="fut_v2_exp")

    pair_arg = None if pair_filter == "Any" else pair_filter
    contracts = list_contracts(
        venue, pair=pair_arg, asof=date.today(), include_expired=include_expired
    )
    if not contracts:
        st.info("No contracts match this filter.")
        return

    labels = [f"{c.code} · {c.product_name} · {c.contract_month}" for c in contracts]
    idx = st.selectbox(
        "Contract",
        list(range(len(contracts))),
        format_func=lambda i: labels[i],
        key="fut_v2_contract",
    )
    contract = contracts[idx]

    asof = st.date_input("As of", value=date.today(), key="fut_v2_asof")
    countdown = days_until(contract, asof)

    # Per-row provenance chip / banner.
    _render_provenance(contract)

    st.markdown("### Result")
    st.write(f"**Contract:**        {contract.code}  ({contract.pair}, {contract.product_name})")
    st.write(f"**Contract month:**  {contract.contract_month}")
    st.write(
        f"**Last Trading Day:** {contract.last_trading_day} "
        f"({contract.last_trading_day.strftime('%a')})  ·  "
        f"{countdown.business_days_to_ltd} business days from {asof}  "
        f"({countdown.calendar_days_to_ltd} calendar)"
    )
    st.write(
        f"**Settlement date:**  {contract.settlement_date} "
        f"({contract.settlement_date.strftime('%a')})  ·  "
        f"{countdown.business_days_to_settlement} business days from {asof}  "
        f"({countdown.calendar_days_to_settlement} calendar)"
    )
    if contract.first_notice_day:
        st.write(f"**First notice day:** {contract.first_notice_day}")
    st.caption(f"Business-day calendar used: {countdown.bd_calendar_used}")
    if contract.note:
        st.caption(contract.note)


def render_lookup() -> None:
    """Alias for the new lookup-style render. Kept so callers that prefer the
    explicit name don't have to know that `render` was repurposed."""
    render()
