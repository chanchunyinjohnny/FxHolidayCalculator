"""FX Forward outright product sub-tab.

A single-leg trade: agree today, settle once on the forward date.
"""

from pathlib import Path

import streamlit as st

from fx_holiday_calculator.calendars.loader import load_rtgs_calendar
from fx_holiday_calculator.calendars.types import CalendarRangeError
from fx_holiday_calculator.forward import InvalidForwardTenorError, calculate_forward_dates
from fx_holiday_calculator.pairs import list_supported_pairs, parse_pair
from fx_holiday_calculator.swap import InvalidBrokenDateError, InvalidTradeDateError
from fx_holiday_calculator.tenor import InvalidTenorError, parse_tenor
from fx_holiday_calculator.ui._widgets import date_input_with_today, render_reasoning, render_trace

BUNDLED = Path(__file__).resolve().parents[2] / "data"
CACHE = Path.home() / ".fx_holiday_calculator" / "cache"

AVAILABLE_RTGS = {"EUR", "USD", "GBP", "JPY"}


def _available_pair_codes() -> list[str]:
    return [
        f"{p.base}/{p.quote}"
        for p in list_supported_pairs()
        if not p.ndf and p.base in AVAILABLE_RTGS and p.quote in AVAILABLE_RTGS
    ]


def render() -> None:
    st.subheader("FX Forward Outright Date Calculator")
    st.caption(
        "Single-leg outright: agree today, settle once on the forward date. "
        "Uses the same engine as Swap (Standard mode, forward tenor) — this tab "
        "is a focused surface for outright forwards."
    )

    pair_codes = _available_pair_codes()
    if not pair_codes:
        st.warning("No supported pairs available.")
        return

    col1, col2, col3 = st.columns(3)
    default_idx = pair_codes.index("EUR/USD") if "EUR/USD" in pair_codes else 0
    pair_code = col1.selectbox("Currency pair", pair_codes, index=default_idx, key="fwd_pair")
    trade_date = date_input_with_today(col2, "Trade date", key="fwd_trade_date")
    tenor_str = col3.text_input(
        "Tenor (forward only — e.g. 3M, IMM1, 2026-08-15)",
        value="3M",
        key="fwd_tenor",
    )

    pair = parse_pair(pair_code)

    has_usd = "USD" in {pair.base, pair.quote}
    if has_usd:
        ref = "none"
    else:
        ref_options = ["none", "USD", "EUR"]
        ref = st.radio(
            "Reference currency",
            ref_options,
            index=ref_options.index("USD"),
            horizontal=True,
            key="fwd_ref",
        )

    needed = {pair.base, pair.quote}
    if ref != "none":
        needed.add(ref)

    try:
        cals = {
            c: load_rtgs_calendar(c, root=BUNDLED / "fx_rtgs", cache_root=CACHE / "fx_rtgs")
            for c in sorted(needed)
        }
    except FileNotFoundError as exc:
        st.error(f"Calendar file missing: {exc}")
        return

    cal_caption = "RTGS: " + " · ".join(f"{c} ({cals[c].calendar_name})" for c in sorted(needed))
    st.caption("Calendars to be used: " + cal_caption)

    if st.button("Calculate", key="fwd_calc"):
        try:
            tenor = parse_tenor(tenor_str)
            result = calculate_forward_dates(
                trade_date=trade_date,
                pair=pair,
                tenor=tenor,
                ref_currency=ref,  # type: ignore[arg-type]
                calendars=cals,
            )
        except (
            InvalidForwardTenorError,
            InvalidTenorError,
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

        if result.warnings:
            st.warning("\n\n".join(f"• {w}" for w in result.warnings))

        st.markdown("### Result")
        st.write(f"**Trade date:**       {result.trade_date} ({result.trade_date.strftime('%a')})")
        st.write(f"**Spot date (ref):**  {result.spot_date} ({result.spot_date.strftime('%a')})")
        st.write(
            f"**Settlement date:**  {result.settlement_date} ({result.settlement_date.strftime('%a')})"
        )

        render_reasoning(result.reasoning)

        st.markdown("### Adjustment trace")
        render_trace(result.spot_trace, "Spot offset")
        render_trace(result.settlement_trace, "Settlement")
