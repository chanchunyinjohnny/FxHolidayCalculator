"""Listed FX Option sub-tab — listed-contract lookup.

Mirrors `product_futures.py`. The user picks a venue, then a contract from
the venue's published listings. Dates come from
`data/fx_exchange/{VENUE}_options_contracts.json` (derived for v1, with a
yellow caveat banner). No tenor input.
"""

from datetime import date

import streamlit as st

from fx_holiday_calculator.options import days_until, list_contracts, list_venues


def _render_provenance(contract) -> None:
    src = contract.source
    mode = contract.derivation_mode
    if mode == "derived":
        st.warning(
            "Derived from venue rule — not scraped from the official contract "
            "page. Verify before trading."
        )
    elif mode == "manual":
        st.info("Manual override — dates curated by a maintainer.")
    badge = {"scrape": "scrape", "derived": "derived ⚠", "manual": "manual"}[mode]
    st.caption(
        f"Source: [{src.doc_title}]({src.url}) — fetched "
        f"{src.fetched_at:%Y-%m-%d}  ·  derivation: `{badge}`"
    )


def render() -> None:
    st.subheader("FX Listed Option — listed contract lookup")
    st.caption(
        "Pick an exchange, then a listed option contract. Dates come from the "
        "venue's published contract specs (derived for v1). No tenor input — "
        "listed options trade as fixed-month contracts like FX futures."
    )

    venues = list_venues()
    if not venues:
        st.warning(
            "No listed-option contract files bundled. Run "
            "`python -m scripts.sources.cme_options_contracts` (and the "
            "HKEX / SGX equivalents) to generate them."
        )
        return

    venue = st.radio("Exchange", venues, horizontal=True, key="lopt_venue")

    try:
        all_contracts = list_contracts(venue, include_expired=True)
    except FileNotFoundError as exc:
        st.error(f"Options-contract file missing for {venue}: {exc}")
        return
    if not all_contracts:
        st.info(f"No listed-option contracts bundled for {venue}.")
        return

    pair_options = ["Any"] + sorted({c.pair for c in all_contracts})
    pair_filter = st.selectbox("Pair (optional)", pair_options, key="lopt_pair")
    include_expired = st.checkbox("Include expired contracts", value=False, key="lopt_exp")

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
        key="lopt_contract",
    )
    contract = contracts[idx]

    asof = st.date_input("As of", value=date.today(), key="lopt_asof")
    countdown = days_until(contract, asof)

    _render_provenance(contract)

    st.markdown("### Result")
    st.write(f"**Contract:**        {contract.code}  ({contract.pair}, {contract.product_name})")
    st.write(f"**Contract month:**  {contract.contract_month}")
    st.write(
        f"**Expiry date:**     {contract.expiry_date} "
        f"({contract.expiry_date.strftime('%a')})  ·  "
        f"{countdown.business_days_to_expiry} business days from {asof}  "
        f"({countdown.calendar_days_to_expiry} calendar)"
    )
    st.write(
        f"**Delivery date:**   {contract.delivery_date} "
        f"({contract.delivery_date.strftime('%a')})  ·  "
        f"{countdown.business_days_to_delivery} business days from {asof}  "
        f"({countdown.calendar_days_to_delivery} calendar)"
    )
    st.caption(f"Business-day calendar used: {countdown.bd_calendar_used}")
    if contract.note:
        st.caption(contract.note)
