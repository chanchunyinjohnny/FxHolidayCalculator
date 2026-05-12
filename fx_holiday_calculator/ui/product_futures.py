"""Futures product sub-tab — CME / HKEX / SGX FX futures."""

from datetime import date
from pathlib import Path

import streamlit as st

from fx_holiday_calculator.calendars.loader import load_exchange_calendar, load_rtgs_calendar
from fx_holiday_calculator.calendars.types import CalendarRangeError
from fx_holiday_calculator.future import (
    InvalidContractMonthError,
    VenueNotListedError,
    calculate_future_dates,
)
from fx_holiday_calculator.pairs import list_supported_pairs, parse_pair
from fx_holiday_calculator.tenor import InvalidTenorError, parse_tenor
from fx_holiday_calculator.ui._bundled import available_exchange_venues, available_rtgs_currencies
from fx_holiday_calculator.ui._widgets import (
    date_input_with_today,
    days_caption,
    render_calendar_coverage,
    render_pair_conventions,
    render_reasoning,
    render_trace,
)

BUNDLED = Path(__file__).resolve().parents[2] / "data"
CACHE = Path.home() / ".fx_holiday_calculator" / "cache"


def _listed_pairs() -> list[str]:
    rtgs = available_rtgs_currencies()
    return [
        f"{p.base}/{p.quote}"
        for p in list_supported_pairs()
        if p.listed_on and p.base in rtgs and p.quote in rtgs
    ]


def render() -> None:
    st.subheader("FX Futures Date Calculator")
    st.caption(
        "Last trade date + delivery date for CME / HKEX / SGX FX futures. "
        "LTD is anchored to the unrolled 3rd Wednesday of the contract month."
    )

    listed = _listed_pairs()
    if not listed:
        st.warning("No listed pairs available.")
        return

    col1, col2 = st.columns(2)
    pair_code = col1.selectbox("Currency pair", listed, key="fut_pair")
    pair = parse_pair(pair_code)
    available_venues = available_exchange_venues()
    valid_venues = [v for v in pair.listed_on if v in available_venues]
    if not valid_venues:
        st.error(
            f"{pair_code} has no bundled exchange calendar. "
            f"Listed on {pair.listed_on}, but none bundled."
        )
        return
    venue = col2.selectbox("Venue", valid_venues, key="fut_venue")

    input_mode = st.radio(
        "Input mode",
        ["Contract month", "IMM tenor"],
        horizontal=True,
        key="fut_input_mode",
    )

    contract_month: tuple[int, int] | None = None
    imm_tenor_str: str | None = None
    from_date: date | None = None
    if input_mode == "Contract month":
        today = date.today()
        c1, c2 = st.columns(2)
        year = c1.number_input(
            "Year",
            min_value=today.year,
            max_value=today.year + 5,
            value=today.year,
            step=1,
            key="fut_year",
        )
        month_name = c2.selectbox(
            "Month",
            ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
            index=today.month - 1,
            key="fut_month",
        )
        month_idx = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ].index(month_name) + 1
        contract_month = (int(year), int(month_idx))
    else:
        c1, c2 = st.columns(2)
        imm_tenor_str = c1.selectbox(
            "IMM tenor",
            ["IMM1", "IMM2", "IMM3", "IMM4"],
            key="fut_imm_tenor",
        )
        from_date = date_input_with_today(c2, "Reference date", key="fut_from_date")

    # Load RTGS + exchange calendars.
    needed = {pair.base, pair.quote}
    try:
        cals = {
            c: load_rtgs_calendar(c, root=BUNDLED / "fx_rtgs", cache_root=CACHE / "fx_rtgs")
            for c in sorted(needed)
        }
    except FileNotFoundError as exc:
        st.error(f"RTGS calendar missing: {exc}")
        return
    try:
        exch_cal = load_exchange_calendar(
            venue, root=BUNDLED / "fx_exchange", cache_root=CACHE / "fx_exchange"
        )
    except FileNotFoundError as exc:
        st.error(f"Exchange calendar missing: {exc}")
        return
    if exch_cal.library_sourced:
        st.warning(
            f"Exchange calendar caveat — {venue} is library-sourced (equity session). "
            "FX-futures holidays may differ. See docs/data-sources.md."
        )

    cal_caption = f"Exchange: {venue} | RTGS: " + " · ".join(
        f"{c} ({cals[c].calendar_name})" for c in sorted(needed)
    )
    st.caption("Calendars to be used: " + cal_caption)
    render_calendar_coverage(
        [(f"{venue} Exchange", exch_cal.valid_from, exch_cal.valid_until)]
        + [
            (f"{c} RTGS ({cals[c].calendar_name})", cals[c].valid_from, cals[c].valid_until)
            for c in sorted(needed)
        ],
        trade_date=from_date,
    )

    if st.button("Calculate", key="fut_calc"):
        try:
            if input_mode == "Contract month":
                result = calculate_future_dates(
                    pair=pair,
                    venue=venue,
                    contract_month=contract_month,
                    rtgs_calendars=cals,
                    exchange_calendar=exch_cal,
                )
            else:
                result = calculate_future_dates(
                    pair=pair,
                    venue=venue,
                    imm_tenor=parse_tenor(imm_tenor_str),  # type: ignore[arg-type]
                    from_date=from_date,
                    rtgs_calendars=cals,
                    exchange_calendar=exch_cal,
                )
        except (
            VenueNotListedError,
            InvalidContractMonthError,
            InvalidTenorError,
        ) as exc:
            st.error(f"Invalid input: {exc}")
            return
        except CalendarRangeError as exc:
            st.error(f"Calculation lands outside bundled window: {exc}")
            return

        if result.warnings:
            st.warning("\n\n".join(f"• {w}" for w in result.warnings))

        st.markdown("### Result")
        cm = result.contract_month
        st.write(f"**Contract:**         {cm[0]}-{cm[1]:02d} ({venue})")
        # Futures have no "trade date" input — anchor the days-from display
        # against the reference date the user supplied (IMM-tenor mode) or
        # today's date (contract-month mode).
        anchor = from_date if from_date is not None else date.today()
        anchor_label = "ref" if from_date is not None else "today"
        st.write(
            f"**Last trade date:**  {result.last_trade_date} "
            f"({result.last_trade_date.strftime('%a')})"
            f"{days_caption(result.last_trade_date, anchor, anchor_label=anchor_label)}"
        )
        st.write(
            f"**Delivery date:**    {result.delivery_date} "
            f"({result.delivery_date.strftime('%a')})"
            f"{days_caption(result.delivery_date, anchor, anchor_label=anchor_label)}"
        )

        render_reasoning(result.reasoning)

        st.markdown("### Adjustment trace")
        render_trace(result.last_trade_trace, "Last trade date")
        render_trace(result.delivery_trace, "Delivery date")
        render_pair_conventions(pair)
