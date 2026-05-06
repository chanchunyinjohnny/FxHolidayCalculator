from datetime import date
from pathlib import Path

import streamlit as st

from fx_holiday_calculator.calendars.loader import load_rtgs_calendar
from fx_holiday_calculator.pairs import list_supported_pairs, parse_pair
from fx_holiday_calculator.swap import (
    InvalidFFSCombinationError,
    calculate_swap_dates,
)
from fx_holiday_calculator.tenor import InvalidTenorError, parse_tenor

BUNDLED = Path(__file__).resolve().parents[2] / "data"
CACHE = Path.home() / ".fx_holiday_calculator" / "cache"

# v1: only these RTGS calendars are bundled.
AVAILABLE_RTGS = {"EUR", "USD", "GBP", "JPY"}


def _available_pair_codes() -> list[str]:
    return [
        f"{p.base}/{p.quote}"
        for p in list_supported_pairs()
        if p.base in AVAILABLE_RTGS and p.quote in AVAILABLE_RTGS
    ]


def _load_rtgs_set(currencies):
    return {
        c: load_rtgs_calendar(
            c,
            root=BUNDLED / "fx_rtgs",
            cache_root=CACHE / "fx_rtgs",
        )
        for c in currencies
    }


def _render_trace(steps, label: str) -> None:
    if not steps:
        st.write(f"_{label}: no adjustment steps_")
        return
    with st.expander(f"{label} — {len(steps)} candidate(s)", expanded=True):
        for s in steps:
            cols = st.columns([1.4, 0.5, 4, 1])
            cols[0].write(s.candidate_date.isoformat())
            cols[1].write(s.weekday)
            cells = []
            for cal_label, status in s.statuses.items():
                if status.is_good:
                    cells.append(f"{cal_label}: ✓")
                else:
                    cells.append(f"{cal_label}: ✘ {status.holiday_name}")
            cols[2].write("  ·  ".join(cells))
            cols[3].write(s.decision)
            for cal_label, status in s.statuses.items():
                if status.source is not None:
                    st.caption(
                        f"{cal_label}: [{status.source.doc_title}]({status.source.url}) · "
                        f"fetched {status.source.fetched_at.isoformat()} · "
                        f"{status.source_origin}"
                    )


def render() -> None:
    st.subheader("Swap Date Calculator")

    pair_codes = _available_pair_codes()
    if not pair_codes:
        st.warning(
            "No supported pairs available — v1 ships with 4 RTGS calendars "
            "(EUR/USD/GBP/JPY) and the bundled data may not be loaded yet."
        )
        return

    col1, col2, col3 = st.columns(3)
    default_idx = pair_codes.index("EUR/USD") if "EUR/USD" in pair_codes else 0
    pair_code = col1.selectbox("Currency pair", pair_codes, index=default_idx)
    trade_date = col2.date_input("Trade date", value=date.today())
    swap_kind = col3.radio(
        "Swap kind",
        ["Standard (single tenor)", "Forward-forward (two tenors)"],
    )

    near_tenor_str: str | None = None
    if swap_kind.startswith("Standard"):
        far_tenor_str = st.text_input(
            "Tenor (e.g. SPOT, ON, 3M, IMM1, 2026-08-15)", value="3M"
        )
    else:
        c1, c2 = st.columns(2)
        near_tenor_str = c1.text_input("Near tenor (e.g. 1M)", value="1M")
        far_tenor_str = c2.text_input("Far tenor (e.g. 3M)", value="3M")

    pair = parse_pair(pair_code)

    # v1 ref currency restriction: only {none, USD, EUR} since HKD/CNH not loaded.
    has_usd = "USD" in {pair.base, pair.quote}
    ref_options = ["none", "USD", "EUR"]
    default_ref = "none" if has_usd else "USD"
    ref = st.radio(
        "Reference currency",
        ref_options,
        index=ref_options.index(default_ref),
        horizontal=True,
        help="In v1, HKD and CNH refs are not available (calendars deferred).",
    )

    cal_mode = st.radio(
        "Calendar mode",
        ["FX (RTGS) only", "Exchange only", "Both"],
        index=0,
        horizontal=True,
        help="v1 has no Exchange calendars loaded; Exchange/Both will fall back to FX-only.",
    )
    cal_mode_key = {
        "FX (RTGS) only": "FX",
        "Exchange only": "EXCHANGE",
        "Both": "BOTH",
    }[cal_mode]

    needed = {pair.base, pair.quote}
    if ref != "none":
        needed.add(ref)

    try:
        cals = _load_rtgs_set(sorted(needed))
    except FileNotFoundError as exc:
        st.error(f"Calendar file missing: {exc}")
        return

    st.caption(
        "Calendars to be used: "
        + " · ".join(f"{c} ({cals[c].calendar_name})" for c in sorted(needed))
    )

    if st.button("Calculate"):
        try:
            far_tenor = parse_tenor(far_tenor_str)
            near_tenor = parse_tenor(near_tenor_str) if near_tenor_str else None
            result = calculate_swap_dates(
                trade_date=trade_date,
                pair=pair,
                far_tenor=far_tenor,
                near_tenor=near_tenor,
                ref_currency=ref,  # type: ignore[arg-type]
                calendars=cals,
                calendar_mode=cal_mode_key,
            )
        except (InvalidTenorError, InvalidFFSCombinationError) as exc:
            st.error(f"Invalid input: {exc}")
            return

        if cal_mode_key == "EXCHANGE":
            st.warning(
                "Calendar mode: Exchange only — settlement here would be "
                "exchange-cleared (FX futures), NOT RTGS settlement. "
                "v1 has no Exchange calendars loaded; the math falls back "
                "to RTGS calendars."
            )

        st.markdown("### Result")
        st.write(f"**Trade date:** {result.trade_date} ({result.trade_date.strftime('%a')})")
        st.write(f"**Spot date:**  {result.spot_date} ({result.spot_date.strftime('%a')})")
        if result.near_date:
            st.write(f"**Near leg:**   {result.near_date} ({result.near_date.strftime('%a')})")
        if result.far_date:
            st.write(f"**Far leg:**    {result.far_date} ({result.far_date.strftime('%a')})")
            if result.near_date:
                gap = (result.far_date - result.near_date).days
                st.caption(f"Near→Far: {gap} calendar days")

        st.markdown("### Adjustment trace")
        _render_trace(result.spot_trace, "Spot offset")
        _render_trace(result.near_trace, "Near leg")
        _render_trace(result.far_trace, "Far leg")
