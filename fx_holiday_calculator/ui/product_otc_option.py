"""OTC FX Option sub-tab."""

from pathlib import Path

import streamlit as st

from fx_holiday_calculator.calendars.loader import load_rtgs_calendar
from fx_holiday_calculator.calendars.types import CalendarRangeError
from fx_holiday_calculator.option_otc import calculate_otc_option_dates
from fx_holiday_calculator.pairs import list_supported_pairs, parse_pair
from fx_holiday_calculator.tenor import InvalidTenorError, parse_tenor
from fx_holiday_calculator.ui._bundled import available_rtgs_currencies
from fx_holiday_calculator.ui._widgets import (
    REF_CURRENCY_HELP,
    date_input_with_today,
    days_caption,
    render_calendar_coverage,
    render_liquidity_warnings,
    render_pair_conventions,
    render_reasoning,
    render_reference_status,
    render_trace,
    render_trade_date_weekend_warning,
)

BUNDLED = Path(__file__).resolve().parents[2] / "data"
CACHE = Path.home() / ".fx_holiday_calculator" / "cache"


def _available_pairs() -> list[str]:
    rtgs = available_rtgs_currencies()
    return [
        f"{p.base}/{p.quote}"
        for p in list_supported_pairs()
        if not p.ndf and p.base in rtgs and p.quote in rtgs
    ]


def render() -> None:
    st.subheader("FX OTC Option — Expiry & Delivery")
    st.caption(
        "Tenor-driven OTC FX option dates. Expiry rolls on RTGS{base, quote, ref}; "
        "delivery rolls on RTGS{base, quote}. ISDA 1998 FX & Currency Options Definitions §3.2."
    )

    pairs = _available_pairs()
    if not pairs:
        st.warning("No supported pairs available.")
        return

    col1, col2, col3 = st.columns(3)
    pair_code = col1.selectbox("Currency pair", pairs, key="otcopt_pair")
    trade_date = date_input_with_today(col2, "Trade date", key="otcopt_trade_date")
    tenor_str = col3.text_input(
        "Tenor (forward only — e.g. 1M, 3M, IMM1, 2026-08-15)",
        value="1M",
        key="otcopt_tenor",
    )

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
            "Reference currency (pair default: " + pair_default + ")",
            ref_options,
            index=ref_options.index(pair_default),
            horizontal=True,
            help=REF_CURRENCY_HELP,
            key="otcopt_ref",
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
        st.error(f"RTGS calendar missing: {exc}")
        return

    cal_caption = "RTGS: " + " · ".join(f"{c} ({cals[c].calendar_name})" for c in sorted(needed))
    st.caption("Calendars to be used: " + cal_caption)
    coverage_items = [
        (f"{c} RTGS ({cals[c].calendar_name})", cals[c].valid_from, cals[c].valid_until)
        for c in sorted(needed)
    ]
    render_calendar_coverage(coverage_items, trade_date=trade_date)

    render_trade_date_weekend_warning(trade_date)

    if st.button("Calculate", key="otcopt_calc"):
        try:
            tenor = parse_tenor(tenor_str)
            result = calculate_otc_option_dates(
                trade_date=trade_date,
                pair=pair,
                tenor=tenor,
                ref_currency=ref,  # type: ignore[arg-type]
                rtgs_calendars=cals,
            )
        except InvalidTenorError as exc:
            st.error(f"Invalid input: {exc}")
            return
        except CalendarRangeError as exc:
            st.error(f"Calculation lands outside bundled window: {exc}")
            return

        if result.warnings:
            st.warning("\n\n".join(f"• {w}" for w in result.warnings))

        render_liquidity_warnings(
            (result.spot_trace, result.expiry_trace, result.delivery_trace),
            cals,
        )

        st.markdown("### Result")
        st.write(f"**Trade date:**     {result.trade_date} ({result.trade_date.strftime('%a')})")
        st.write(
            f"**Spot date:**      {result.spot_date} ({result.spot_date.strftime('%a')})"
            f"{days_caption(result.spot_date, result.trade_date)}"
        )
        st.write(
            f"**Expiry date:**    {result.expiry_date} ({result.expiry_date.strftime('%a')})"
            f"{days_caption(result.expiry_date, result.trade_date)}"
        )
        st.write(
            f"**Delivery date:**  {result.delivery_date} "
            f"({result.delivery_date.strftime('%a')})"
            f"{days_caption(result.delivery_date, result.trade_date)}"
        )

        render_reasoning(result.reasoning)

        st.markdown("### Adjustment trace")
        render_trace(result.spot_trace, "Spot offset")
        render_trace(result.expiry_trace, "Expiry")
        render_trace(result.delivery_trace, "Delivery")

        render_reference_status(
            pair=pair,
            selected_ref=ref,
            named_traces=[
                ("Spot offset", result.spot_trace),
                ("Expiry", result.expiry_trace),
                ("Delivery", result.delivery_trace),
            ],
        )
        render_pair_conventions(pair)
