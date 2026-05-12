"""FX Swap product sub-tab.

Covers ON / TN / SN short-dated swaps, standard (single-tenor) swaps,
and forward-forward swaps (two tenors). All legs roll on RTGS settlement
calendars; exchange calendars are not consulted because OTC swap
settlement is bilateral and venue-independent.

Pure spot date calculations live in the Spot tab.
"""

from pathlib import Path

import streamlit as st

from fx_holiday_calculator.calendars.loader import load_rtgs_calendar
from fx_holiday_calculator.calendars.types import CalendarRangeError
from fx_holiday_calculator.pairs import list_supported_pairs, parse_pair
from fx_holiday_calculator.swap import (
    InvalidBrokenDateError,
    InvalidFFSCombinationError,
    InvalidTradeDateError,
    calculate_swap_dates,
)
from fx_holiday_calculator.tenor import InvalidTenorError, parse_tenor
from fx_holiday_calculator.ui._widgets import (
    REF_CURRENCY_HELP,
    date_input_with_today,
    render_pair_conventions,
    render_reasoning,
    render_reference_status,
    render_trace,
)

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


def render() -> None:
    st.subheader("FX Swap Date Calculator")
    st.caption(
        "Covers ON / TN / SN short-dated swaps, standard (single-tenor) swaps, "
        "and forward-forward swaps. All legs roll on RTGS settlement calendars. "
        "For a pure spot date, use the Spot tab."
    )

    pair_codes = _available_pair_codes()
    if not pair_codes:
        st.warning(
            "No supported pairs available — v1 ships with 4 RTGS calendars "
            "(EUR/USD/GBP/JPY) and the bundled data may not be loaded yet."
        )
        return

    col1, col2, col3 = st.columns(3)
    default_idx = pair_codes.index("EUR/USD") if "EUR/USD" in pair_codes else 0
    pair_code = col1.selectbox("Currency pair", pair_codes, index=default_idx, key="swap_pair")
    trade_date = date_input_with_today(col2, "Trade date", key="swap_trade_date")
    swap_kind = col3.radio(
        "Swap kind",
        ["Standard (single tenor)", "Forward-forward (two tenors)"],
        key="swap_kind",
    )

    near_tenor_str: str | None = None
    if swap_kind.startswith("Standard"):
        far_tenor_str = st.text_input(
            "Tenor (e.g. ON, TN, SN, 3M, IMM1, 2026-08-15)",
            value="3M",
            key="swap_far_tenor_std",
        )
    else:
        c1, c2 = st.columns(2)
        near_tenor_str = c1.text_input("Near tenor (e.g. 1M)", value="1M", key="swap_near_tenor")
        far_tenor_str = c2.text_input("Far tenor (e.g. 3M)", value="3M", key="swap_far_tenor_ffs")

    pair = parse_pair(pair_code)

    # Reference-currency picker: shown only when the pair has a documented
    # third-currency convention AND the reference is not already a leg.
    # v1 ref currency restriction: only {none, USD, EUR} since HKD/CNH not loaded.
    leg_ccys = {pair.base, pair.quote}
    pair_default = pair.default_ref_currency
    if pair_default is None or pair_default in leg_ccys:
        ref = "none"
    else:
        # Build options around the pair's documented default.
        ref_options = ["none"]
        for c in (pair_default, "USD", "EUR"):
            if c not in ref_options and c not in leg_ccys:
                ref_options.append(c)
        ref = st.radio(
            f"Reference currency (pair default: {pair_default})",
            ref_options,
            index=ref_options.index(pair_default),
            horizontal=True,
            help=REF_CURRENCY_HELP
            + " In v1, HKD and CNH refs are not available (calendars deferred).",
            key="swap_ref",
        )

    needed = {pair.base, pair.quote}
    if ref != "none":
        needed.add(ref)

    try:
        cals = _load_rtgs_set(sorted(needed))
    except FileNotFoundError as exc:
        st.error(f"Calendar file missing: {exc}")
        return

    cal_caption = "RTGS: " + " · ".join(f"{c} ({cals[c].calendar_name})" for c in sorted(needed))
    st.caption("Calendars to be used: " + cal_caption)

    if st.button("Calculate"):
        try:
            far_tenor = parse_tenor(far_tenor_str)
            near_tenor = parse_tenor(near_tenor_str) if near_tenor_str else None
            if far_tenor.kind == "SPOT" and near_tenor is None:
                st.info(
                    "SPOT is a single-date product — please use the **Spot** tab. "
                    "The Swap tab is for two-leg products (ON/TN/SN, standard swap, "
                    "forward-forward swap)."
                )
                return
            result = calculate_swap_dates(
                trade_date=trade_date,
                pair=pair,
                far_tenor=far_tenor,
                near_tenor=near_tenor,
                ref_currency=ref,  # type: ignore[arg-type]
                calendars=cals,
            )
        except (
            InvalidTenorError,
            InvalidFFSCombinationError,
            InvalidBrokenDateError,
            InvalidTradeDateError,
        ) as exc:
            st.error(f"Invalid input: {exc}")
            return
        except CalendarRangeError as exc:
            st.error(
                f"Calculation lands outside bundled calendar window: {exc} "
                "Refresh the calendar data or pick an earlier trade date."
            )
            return

        # Surface liquidity warnings for any annotated dates in the calculation range.
        liq_alerts = []
        for trace in (result.spot_trace, result.near_trace, result.far_trace):
            for step in trace:
                for cal_label, status in step.statuses.items():
                    if status.liquidity:
                        # Try to fetch the entry name for richer detail
                        entry_note = ""
                        ccy = cal_label.split(" ")[0]  # "EUR (TARGET2)" -> "EUR"
                        cal = cals.get(ccy)
                        if cal is not None:
                            entry = cal.get_holiday(step.candidate_date)
                            if entry:
                                entry_note = f" — {entry.name}"
                        liq_alerts.append(
                            f"{step.candidate_date.isoformat()} ({step.weekday}) "
                            f"{cal_label}: {status.liquidity}{entry_note}"
                        )

        if liq_alerts:
            # Deduplicate (same date/cal can appear in spot+near trace).
            seen = set()
            unique_alerts = []
            for a in liq_alerts:
                if a not in seen:
                    seen.add(a)
                    unique_alerts.append(a)
            st.warning(
                "Liquidity warning — these dates are flagged as thin/halted trading "
                "even though they don't block the calculation:\n\n"
                + "\n".join(f"• {a}" for a in unique_alerts)
            )

        if result.warnings:
            st.warning("Convention warning:\n\n" + "\n".join(f"• {w}" for w in result.warnings))

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

        render_reasoning(result.reasoning)

        st.markdown("### Adjustment trace")
        render_trace(result.spot_trace, "Spot offset")
        render_trace(result.near_trace, "Near leg")
        render_trace(result.far_trace, "Far leg")

        render_reference_status(
            pair=pair,
            selected_ref=ref,
            named_traces=[
                ("Spot offset", result.spot_trace),
                ("Near leg", result.near_trace),
                ("Far leg", result.far_trace),
            ],
        )
        render_pair_conventions(pair)
