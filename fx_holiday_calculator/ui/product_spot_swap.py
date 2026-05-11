"""Spot / Swap product sub-tab.

Renders the existing engine surface (calculate_swap_dates) under a
product-aware label. Covers spot, cross-spot, ON/TN/SN, forward outright,
standard swap, and forward-forward swap — all sharing identical RTGS-only
calendar logic, with optional exchange/both mode for forward legs.
"""

from datetime import date
from pathlib import Path

import streamlit as st

from fx_holiday_calculator.calendars.loader import load_exchange_calendar, load_rtgs_calendar
from fx_holiday_calculator.calendars.types import CalendarRangeError
from fx_holiday_calculator.conventions.cross import MissingExchangeCalendarError, relevant_venues
from fx_holiday_calculator.pairs import list_supported_pairs, parse_pair
from fx_holiday_calculator.swap import (
    InvalidBrokenDateError,
    InvalidFFSCombinationError,
    InvalidTradeDateError,
    calculate_swap_dates,
)
from fx_holiday_calculator.tenor import InvalidTenorError, parse_tenor

BUNDLED = Path(__file__).resolve().parents[2] / "data"
CACHE = Path.home() / ".fx_holiday_calculator" / "cache"

# v1: only these RTGS calendars are bundled.
AVAILABLE_RTGS = {"EUR", "USD", "GBP", "JPY"}


def _available_exchange_venues() -> set[str]:
    bundled = BUNDLED / "fx_exchange"
    if not bundled.exists():
        return set()
    return {p.stem for p in bundled.glob("*.json") if not p.name.startswith("_")}


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


def _load_exchange_set(venues):
    return {
        v: load_exchange_calendar(
            v,
            root=BUNDLED / "fx_exchange",
            cache_root=CACHE / "fx_exchange",
        )
        for v in venues
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
    st.subheader("Spot & Swap Date Calculator")
    st.caption(
        "Covers spot, cross-spot, ON/TN/SN, forward outright, standard swap, "
        "and forward-forward swap. All rolling on RTGS calendars; exchange "
        "calendar mode optional for forward legs."
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
    trade_date = col2.date_input("Trade date", value=date.today(), key="swap_trade_date")
    swap_kind = col3.radio(
        "Swap kind",
        ["Standard (single tenor)", "Forward-forward (two tenors)"],
        key="swap_kind",
    )

    near_tenor_str: str | None = None
    if swap_kind.startswith("Standard"):
        far_tenor_str = st.text_input(
            "Tenor (e.g. SPOT, ON, 3M, IMM1, 2026-08-15)",
            value="3M",
            key="swap_far_tenor_std",
        )
    else:
        c1, c2 = st.columns(2)
        near_tenor_str = c1.text_input("Near tenor (e.g. 1M)", value="1M", key="swap_near_tenor")
        far_tenor_str = c2.text_input("Far tenor (e.g. 3M)", value="3M", key="swap_far_tenor_ffs")

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
        key="swap_ref",
    )

    cal_mode = st.radio(
        "Calendar mode",
        ["FX (RTGS) only", "Exchange only", "Both"],
        index=0,
        horizontal=True,
        help=(
            "FX = roll legs against RTGS settlement calendars. "
            "Exchange = roll legs against the relevant FX-futures venue (CME/HKEX/SGX). "
            "Both = roll against the union (most conservative). "
            "Spot date is always RTGS-based regardless of mode."
        ),
        key="swap_cal_mode",
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
            exch_cals = _load_exchange_set(sorted(needed_venues))
        except FileNotFoundError as exc:
            st.error(f"Exchange calendar file missing: {exc}")
            return
        lib_venues = sorted(v for v, c in exch_cals.items() if c.library_sourced)
        if lib_venues:
            st.warning(
                "**Exchange calendar caveat — library-sourced data in use for "
                f"{', '.join(lib_venues)}.**\n\n"
                "These calendars come from the `exchange_calendars` library "
                "(equity session), not a primary venue document. Real-world "
                "FX-futures holidays may differ:\n"
                "- Library encodes the venue's **equity** session — "
                "FX-futures products often observe additional closures "
                "(US bank holidays for CME, Hari Raya for SGX FX-INR, etc.).\n"
                "- Exchange holidays are **per-product**, not per-venue — "
                "a date may close one FX contract and not another.\n"
                "- Library coverage horizon lags real-world year-ahead "
                "publication, especially for lunar/Islamic dates.\n\n"
                "**For high-stakes decisions, verify against the venue's "
                "primary holiday document.** See `docs/data-sources.md`."
            )

    cal_caption = "RTGS: " + " · ".join(f"{c} ({cals[c].calendar_name})" for c in sorted(needed))
    if exch_cals:
        cal_caption += " | Exchange: " + " · ".join(sorted(exch_cals))
    st.caption("Calendars to be used: " + cal_caption)

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
                exchange_calendars=exch_cals,
                calendar_mode=cal_mode_key,
            )
        except (
            InvalidTenorError,
            InvalidFFSCombinationError,
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

        st.markdown("### Adjustment trace")
        _render_trace(result.spot_trace, "Spot offset")
        _render_trace(result.near_trace, "Near leg")
        _render_trace(result.far_trace, "Far leg")
