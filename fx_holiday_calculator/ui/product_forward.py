"""FX Forward outright product sub-tab.

A single-leg trade: agree today, settle once on the forward date.
"""

from datetime import date
from pathlib import Path

import streamlit as st

from fx_holiday_calculator.calendars.loader import load_exchange_calendar, load_rtgs_calendar
from fx_holiday_calculator.calendars.types import CalendarRangeError
from fx_holiday_calculator.conventions.cross import (
    MissingExchangeCalendarError,
    relevant_venues,
)
from fx_holiday_calculator.forward import (
    InvalidForwardTenorError,
    calculate_forward_dates,
)
from fx_holiday_calculator.pairs import list_supported_pairs, parse_pair
from fx_holiday_calculator.swap import InvalidBrokenDateError, InvalidTradeDateError
from fx_holiday_calculator.tenor import InvalidTenorError, parse_tenor

BUNDLED = Path(__file__).resolve().parents[2] / "data"
CACHE = Path.home() / ".fx_holiday_calculator" / "cache"

AVAILABLE_RTGS = {"EUR", "USD", "GBP", "JPY"}


def _available_pair_codes() -> list[str]:
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
    trade_date = col2.date_input("Trade date", value=date.today(), key="fwd_trade_date")
    tenor_str = col3.text_input(
        "Tenor (forward only — e.g. 3M, IMM1, 2026-08-15)",
        value="3M",
        key="fwd_tenor",
    )

    pair = parse_pair(pair_code)

    has_usd = "USD" in {pair.base, pair.quote}
    ref_options = ["none", "USD", "EUR"]
    default_ref = "none" if has_usd else "USD"
    ref = st.radio(
        "Reference currency",
        ref_options,
        index=ref_options.index(default_ref),
        horizontal=True,
        key="fwd_ref",
    )

    cal_mode = st.radio(
        "Calendar mode",
        ["FX (RTGS) only", "Exchange only", "Both"],
        index=0,
        horizontal=True,
        help=(
            "FX = roll settlement against RTGS settlement calendars. "
            "Exchange = roll against the relevant FX-futures venue. "
            "Both = roll against the union (most conservative)."
        ),
        key="fwd_cal_mode",
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
        cals = {
            c: load_rtgs_calendar(c, root=BUNDLED / "fx_rtgs", cache_root=CACHE / "fx_rtgs")
            for c in sorted(needed)
        }
    except FileNotFoundError as exc:
        st.error(f"Calendar file missing: {exc}")
        return

    exch_cals = None
    if cal_mode_key in {"EXCHANGE", "BOTH"}:
        available_venues = _available_exchange_venues()
        needed_venues = set(relevant_venues(pair, ref))  # type: ignore[arg-type]
        missing = sorted(needed_venues - available_venues)
        if missing:
            st.error(
                f"{cal_mode} requires exchange calendars for venue(s) "
                f"{', '.join(missing)}, but none are bundled. "
                "Switch to FX (RTGS) only to compute."
            )
            return
        try:
            exch_cals = {
                v: load_exchange_calendar(
                    v,
                    root=BUNDLED / "fx_exchange",
                    cache_root=CACHE / "fx_exchange",
                )
                for v in sorted(needed_venues)
            }
        except FileNotFoundError as exc:
            st.error(f"Exchange calendar file missing: {exc}")
            return
        lib_venues = sorted(v for v, c in exch_cals.items() if c.library_sourced)
        if lib_venues:
            st.warning(
                f"Exchange calendar caveat — library-sourced data in use for "
                f"{', '.join(lib_venues)}. See docs/data-sources.md."
            )

    cal_caption = "RTGS: " + " · ".join(f"{c} ({cals[c].calendar_name})" for c in sorted(needed))
    if exch_cals:
        cal_caption += " | Exchange: " + " · ".join(sorted(exch_cals))
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
                exchange_calendars=exch_cals,
                calendar_mode=cal_mode_key,
            )
        except (
            InvalidForwardTenorError,
            InvalidTenorError,
            InvalidBrokenDateError,
            InvalidTradeDateError,
        ) as exc:
            st.error(f"Invalid input: {exc}")
            return
        except MissingExchangeCalendarError as exc:
            st.error(f"Exchange calendar missing: {exc}")
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
        st.write(f"**Settlement date:**  {result.settlement_date} ({result.settlement_date.strftime('%a')})")

        st.markdown("### Adjustment trace")
        _render_trace(result.spot_trace, "Spot offset")
        _render_trace(result.settlement_trace, "Settlement")
