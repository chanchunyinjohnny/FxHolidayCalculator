"""Spot product sub-tab.

A single-date calculator: trade date → spot date, on RTGS settlement
calendars. EOM and tenor projection do not apply at spot — spot is just
T+N business days from the trade date. For two-leg products (swap, FFS,
ON/TN/SN) use the Swap tab.
"""

from pathlib import Path

import streamlit as st

from fx_holiday_calculator.calendars.loader import load_rtgs_calendar
from fx_holiday_calculator.calendars.types import CalendarRangeError
from fx_holiday_calculator.pairs import list_supported_pairs, parse_pair
from fx_holiday_calculator.swap import InvalidTradeDateError, calculate_swap_dates
from fx_holiday_calculator.tenor import parse_tenor
from fx_holiday_calculator.ui._bundled import available_rtgs_currencies
from fx_holiday_calculator.ui._widgets import (
    REF_CURRENCY_HELP,
    date_input_with_today,
    days_caption,
    render_pair_conventions,
    render_reasoning,
    render_reference_status,
    render_trace,
)

BUNDLED = Path(__file__).resolve().parents[2] / "data"
CACHE = Path.home() / ".fx_holiday_calculator" / "cache"


def _available_pair_codes() -> list[str]:
    rtgs = available_rtgs_currencies()
    return [
        f"{p.base}/{p.quote}" for p in list_supported_pairs() if p.base in rtgs and p.quote in rtgs
    ]


def render() -> None:
    st.subheader("FX Spot Date Calculator")
    st.caption(
        "Single-date: trade date → spot date on RTGS settlement calendars. "
        "T+N from trade date, where N is the pair's spot offset (e.g. 2 for "
        "EUR/USD, 1 for USD/CAD). For swap / ON / TN / SN / forward / FFS, "
        "use the Swap tab."
    )

    pair_codes = _available_pair_codes()
    if not pair_codes:
        st.warning("No supported pairs available.")
        return

    col1, col2 = st.columns(2)
    default_idx = pair_codes.index("EUR/USD") if "EUR/USD" in pair_codes else 0
    pair_code = col1.selectbox("Currency pair", pair_codes, index=default_idx, key="spot_pair")
    trade_date = date_input_with_today(col2, "Trade date", key="spot_trade_date")

    pair = parse_pair(pair_code)

    leg_ccys = {pair.base, pair.quote}
    pair_default = pair.default_ref_currency
    if pair_default is None or pair_default in leg_ccys:
        ref = "none"
    else:
        ref_options = ["none"]
        for c in (pair_default, "USD", "EUR"):
            if c not in ref_options and c not in leg_ccys:
                ref_options.append(c)
        ref = st.radio(
            f"Reference currency (pair default: {pair_default})",
            ref_options,
            index=ref_options.index(pair_default),
            horizontal=True,
            help=REF_CURRENCY_HELP,
            key="spot_ref",
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

    if st.button("Calculate", key="spot_calc"):
        try:
            result = calculate_swap_dates(
                trade_date=trade_date,
                pair=pair,
                far_tenor=parse_tenor("SPOT"),
                near_tenor=None,
                ref_currency=ref,  # type: ignore[arg-type]
                calendars=cals,
            )
        except InvalidTradeDateError as exc:
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
        st.write(f"**Trade date:** {result.trade_date} ({result.trade_date.strftime('%a')})")
        st.write(
            f"**Spot date:**  {result.spot_date} ({result.spot_date.strftime('%a')})"
            f"{days_caption(result.spot_date, result.trade_date)}"
        )

        render_reasoning(result.reasoning)

        st.markdown("### Adjustment trace")
        render_trace(result.spot_trace, "Spot offset")

        render_reference_status(
            pair=pair,
            selected_ref=ref,
            named_traces=[("Spot offset", result.spot_trace)],
        )
        render_pair_conventions(pair)
