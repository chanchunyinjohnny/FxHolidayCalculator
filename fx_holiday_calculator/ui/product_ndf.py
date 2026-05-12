"""NDF product sub-tab — inputs for USD/CNY, USD/KRW, USD/TWD with fixing dates."""

from datetime import date
from pathlib import Path

import streamlit as st

from fx_holiday_calculator.calendars.fixing import FixingCalendar
from fx_holiday_calculator.calendars.loader import load_fixing_calendar, load_rtgs_calendar
from fx_holiday_calculator.calendars.types import CalendarRangeError
from fx_holiday_calculator.ndf import (
    InvalidBrokenDateError,
    InvalidNdfPairError,
    InvalidTradeDateError,
    calculate_ndf_dates,
)
from fx_holiday_calculator.pairs import list_supported_pairs, parse_pair
from fx_holiday_calculator.tenor import InvalidTenorError, parse_tenor
from fx_holiday_calculator.ui._widgets import (
    date_input_with_today,
    render_pair_conventions,
    render_reasoning,
    render_trace,
)

BUNDLED = Path(__file__).resolve().parents[2] / "data"
CACHE = Path.home() / ".fx_holiday_calculator" / "cache"


def _ndf_pair_codes() -> list[str]:
    return [f"{p.base}/{p.quote}" for p in list_supported_pairs() if p.ndf]


def _load_fixing(currency: str) -> FixingCalendar:
    return load_fixing_calendar(
        currency,
        root=BUNDLED / "fx_fixing",
        cache_root=CACHE / "fx_fixing",
    )


def render() -> None:
    st.subheader("NDF Date Calculator")
    st.caption(
        "Non-deliverable forwards: USD settlement, fixing on primary-source "
        "calendar of the non-deliverable currency (CFETS / KFTC / Taipei Forex)."
    )

    pair_codes = _ndf_pair_codes()
    if not pair_codes:
        st.warning("No NDF pairs available — check pair-table configuration.")
        return

    col1, col2 = st.columns(2)
    pair_code = col1.selectbox("Currency pair", pair_codes, key="ndf_pair")
    trade_date = date_input_with_today(col2, "Trade date", key="ndf_trade_date")
    pair = parse_pair(pair_code)

    input_mode = st.radio(
        "Input mode",
        ["Tenor", "Maturity date"],
        horizontal=True,
        key="ndf_input_mode",
    )

    tenor_str: str | None = None
    target_date: date | None = None
    if input_mode == "Tenor":
        tenor_str = st.text_input(
            "Tenor (forward only — PERIOD / IMM / BROKEN, e.g. 3M, IMM1, 2026-08-15)",
            value="3M",
            key="ndf_tenor",
        )
    else:
        target_date = st.date_input(
            "Target settlement date",
            value=date(date.today().year, date.today().month, 15),
            key="ndf_target",
        )

    # Load USD RTGS + fixing calendar.
    try:
        usd = load_rtgs_calendar(
            "USD",
            root=BUNDLED / "fx_rtgs",
            cache_root=CACHE / "fx_rtgs",
        )
    except FileNotFoundError as exc:
        st.error(f"USD RTGS calendar missing: {exc}")
        return

    try:
        fixing = _load_fixing(pair.fixing_currency)  # type: ignore[arg-type]
    except FileNotFoundError as exc:
        st.error(
            f"Fixing calendar for {pair.fixing_currency} missing: {exc}. "
            f"Refresh via the sidebar."
        )
        return

    if fixing.library_sourced:
        st.warning(
            f"Fixing calendar caveat — {fixing.currency} is library-sourced "
            f"(python-holidays). NDF fixing dates may differ slightly from the "
            f"primary CFETS / KFTC / Taipei Forex publications. For high-stakes "
            f"decisions, verify against the official document. See "
            f"`docs/data-sources.md` for primary-fetch instructions."
        )

    st.caption(
        f"Calendars to be used: RTGS: USD ({usd.calendar_name}) | "
        f"Fixing: {fixing.currency} ({fixing.calendar_name})"
    )

    if st.button("Calculate", key="ndf_calc"):
        try:
            if input_mode == "Tenor":
                tenor = parse_tenor(tenor_str)  # type: ignore[arg-type]
                result = calculate_ndf_dates(
                    trade_date=trade_date,
                    pair=pair,
                    tenor=tenor,
                    rtgs_calendars={"USD": usd},
                    fixing_calendar=fixing,
                )
            else:
                result = calculate_ndf_dates(
                    trade_date=trade_date,
                    pair=pair,
                    target_settlement=target_date,
                    rtgs_calendars={"USD": usd},
                    fixing_calendar=fixing,
                )
        except (
            InvalidNdfPairError,
            InvalidTenorError,
            InvalidTradeDateError,
            InvalidBrokenDateError,
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
        st.write(f"**Spot date:**        {result.spot_date} ({result.spot_date.strftime('%a')})")
        st.write(
            f"**Fixing date:**      {result.fixing_date} ({result.fixing_date.strftime('%a')})"
        )
        st.write(
            f"**Settlement date:**  {result.settlement_date} ({result.settlement_date.strftime('%a')})"
        )

        render_reasoning(result.reasoning)

        st.markdown("### Adjustment trace")
        render_trace(result.spot_trace, "Spot offset")
        render_trace(result.settlement_trace, "Settlement")
        render_pair_conventions(pair)
        render_trace(result.fixing_trace, "Fixing")
