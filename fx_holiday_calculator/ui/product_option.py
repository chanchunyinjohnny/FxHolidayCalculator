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
from fx_holiday_calculator.ui._widgets import date_input_with_today

BUNDLED = Path(__file__).resolve().parents[2] / "data"
CACHE = Path.home() / ".fx_holiday_calculator" / "cache"

AVAILABLE_RTGS = {"EUR", "USD", "GBP", "JPY"}


def _available_pairs() -> list[str]:
    return [
        f"{p.base}/{p.quote}"
        for p in list_supported_pairs()
        if not p.ndf and p.base in AVAILABLE_RTGS and p.quote in AVAILABLE_RTGS
    ]


def _available_exchange_venues() -> set[str]:
    bundled = BUNDLED / "fx_exchange"
    if not bundled.exists():
        return set()
    return {p.stem for p in bundled.glob("*.json") if not p.name.startswith("_")}


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

    has_usd = "USD" in {pair.base, pair.quote}
    if has_usd:
        ref = "none"
    else:
        ref_options = ["none", "USD", "EUR"]
        ref = st.radio(
            "Reference currency (OTC only — ignored for Listed)",
            ref_options,
            index=ref_options.index("USD"),
            horizontal=True,
            key="opt_ref",
        )

    venue: str | None = None
    if style_key == "LISTED":
        available = _available_exchange_venues()
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
        st.write(f"**Spot date:**      {result.spot_date} ({result.spot_date.strftime('%a')})")
        st.write(f"**Expiry date:**    {result.expiry_date} ({result.expiry_date.strftime('%a')})")
        st.write(
            f"**Delivery date:**  {result.delivery_date} ({result.delivery_date.strftime('%a')})"
        )

        st.markdown("### Adjustment trace")
        _render_trace(result.expiry_trace, "Expiry")
        _render_trace(result.delivery_trace, "Delivery")
