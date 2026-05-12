"""Option product sub-tab — OTC and Listed FX options."""

from pathlib import Path

import streamlit as st

from fx_holiday_calculator.calendars.loader import load_exchange_calendar, load_rtgs_calendar
from fx_holiday_calculator.calendars.types import CalendarRangeError
from fx_holiday_calculator.option import (
    InvalidOptionStyleError,
    ListedOptionVenueRequiredError,
    calculate_option_dates,
)
from fx_holiday_calculator.pairs import list_supported_pairs, parse_pair
from fx_holiday_calculator.tenor import InvalidTenorError, parse_tenor
from fx_holiday_calculator.ui._bundled import available_exchange_venues, available_rtgs_currencies
from fx_holiday_calculator.ui._widgets import (
    REF_CURRENCY_HELP,
    date_input_with_today,
    days_caption,
    render_calendar_coverage,
    render_pair_conventions,
    render_reasoning,
    render_reference_status,
    render_trace,
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
    st.subheader("FX Option Date Calculator")
    st.caption(
        "Expiry + delivery dates for vanilla FX options. "
        "OTC = expiry rolls on RTGS; Listed = expiry rolls on the venue's exchange calendar."
    )

    pairs = _available_pairs()
    if not pairs:
        st.warning("No supported pairs available.")
        return

    col1, col2, col3 = st.columns(3)
    pair_code = col1.selectbox("Currency pair", pairs, key="opt_pair")
    trade_date = date_input_with_today(col2, "Trade date", key="opt_trade_date")
    tenor_str = col3.text_input(
        "Tenor (forward only — e.g. 1M, 3M, IMM1, 2026-08-15)",
        value="1M",
        key="opt_tenor",
    )

    pair = parse_pair(pair_code)
    style = st.radio("Style", ["OTC", "Listed"], horizontal=True, key="opt_style")
    style_key = "OTC" if style == "OTC" else "LISTED"

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
            f"Reference currency (pair default: {pair_default}) — OTC only, ignored for Listed",
            ref_options,
            index=ref_options.index(pair_default),
            horizontal=True,
            help=REF_CURRENCY_HELP,
            key="opt_ref",
        )

    venue: str | None = None
    if style_key == "LISTED":
        available = available_exchange_venues()
        valid_for_pair = [v for v in pair.listed_on if v in available]
        if not valid_for_pair:
            st.error(
                f"{pair_code} is not listed on any venue with bundled exchange data. "
                f"Switch to OTC."
            )
            return
        venue = st.selectbox("Venue", valid_for_pair, key="opt_venue")

    # Load RTGS calendars.
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

    exch_cal = None
    if style_key == "LISTED":
        try:
            exch_cal = load_exchange_calendar(
                venue,  # type: ignore[arg-type]
                root=BUNDLED / "fx_exchange",
                cache_root=CACHE / "fx_exchange",
            )
        except FileNotFoundError as exc:
            st.error(f"Exchange calendar missing: {exc}")
            return
        if exch_cal.library_sourced:
            st.warning(
                f"Exchange calendar caveat — {venue} is library-sourced (equity session). "
                "FX-options holidays may differ. See docs/data-sources.md."
            )

    cal_caption = "RTGS: " + " · ".join(f"{c} ({cals[c].calendar_name})" for c in sorted(needed))
    if exch_cal:
        cal_caption += f" | Exchange: {venue}"
    st.caption("Calendars to be used: " + cal_caption)
    coverage_items = [
        (f"{c} RTGS ({cals[c].calendar_name})", cals[c].valid_from, cals[c].valid_until)
        for c in sorted(needed)
    ]
    if exch_cal is not None:
        coverage_items.append((f"{venue} Exchange", exch_cal.valid_from, exch_cal.valid_until))
    render_calendar_coverage(coverage_items, trade_date=trade_date)

    if st.button("Calculate", key="opt_calc"):
        try:
            tenor = parse_tenor(tenor_str)
            result = calculate_option_dates(
                trade_date=trade_date,
                pair=pair,
                tenor=tenor,
                style=style_key,
                ref_currency=ref,  # type: ignore[arg-type]
                rtgs_calendars=cals,
                exchange_calendar=exch_cal,
                venue=venue,
            )
        except (
            InvalidTenorError,
            InvalidOptionStyleError,
            ListedOptionVenueRequiredError,
        ) as exc:
            st.error(f"Invalid input: {exc}")
            return
        except CalendarRangeError as exc:
            st.error(f"Calculation lands outside bundled window: {exc}")
            return

        if result.warnings:
            st.warning("\n\n".join(f"• {w}" for w in result.warnings))

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

        # OTC only — Listed options roll on exchange calendar, not the
        # OTC reference-currency rule.
        if style_key == "OTC":
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
