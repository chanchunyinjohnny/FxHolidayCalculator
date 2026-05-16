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


def _available_pair_codes() -> list[str]:
    rtgs = available_rtgs_currencies()
    return [
        f"{p.base}/{p.quote}" for p in list_supported_pairs() if p.base in rtgs and p.quote in rtgs
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
            "No supported pairs available — no bundled RTGS calendars were "
            "found under data/fx_rtgs."
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
    ffs_far_anchor = "spot"
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
        anchor_choice = st.radio(
            "Far-leg anchoring",
            [
                "Spot-anchored (standard interbank / Strata convention)",
                "Near-anchored (360T RFS - non-standard)",
            ],
            index=0,
            key="swap_ffs_far_anchor",
            help=(
                "Standard interbank practice quotes both FFS legs from spot. "
                "Example: a 1W-1M swap has the near leg at spot+1W and the "
                "far leg at spot+1M. The 360T RFS platform instead "
                "interprets the far tenor as measured from the near date "
                "(far at near+1M). This is uncommon; only use it if your "
                "counterparty or venue requires it."
            ),
        )
        ffs_far_anchor = "near" if anchor_choice.startswith("Near") else "spot"
        if ffs_far_anchor == "near":
            st.info(
                "**Non-standard mode.** Far leg will be measured from the "
                "NEAR date, not from spot. This is the 360T RFS convention. "
                "OpenGamma Strata, Bloomberg, and most interbank desks "
                "anchor both legs on spot. Confirm with your counterparty "
                "or venue."
            )

    pair = parse_pair(pair_code)

    # Reference-currency picker: shown only when the pair has a documented
    # third-currency convention AND the reference is not already a leg.
    leg_ccys = {pair.base, pair.quote}
    pair_default = pair.default_ref_currency
    if pair_default is None or pair_default in leg_ccys:
        ref = "none"
    else:
        # Build options around the pair's documented default.
        ref_options = ["none"]
        for c in (pair_default, "USD", "EUR", "HKD", "CNH"):
            if c not in ref_options and c not in leg_ccys:
                ref_options.append(c)
        ref = st.radio(
            f"Reference currency (pair default: {pair_default})",
            ref_options,
            index=ref_options.index(pair_default),
            horizontal=True,
            help=REF_CURRENCY_HELP,
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
    render_calendar_coverage(
        [
            (f"{c} RTGS ({cals[c].calendar_name})", cals[c].valid_from, cals[c].valid_until)
            for c in sorted(needed)
        ],
        trade_date=trade_date,
    )

    render_trade_date_weekend_warning(trade_date)

    if st.button("Calculate", key="swap_calc"):
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
                ffs_far_anchor=ffs_far_anchor,  # type: ignore[arg-type]
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
        render_liquidity_warnings(
            (result.spot_trace, result.near_trace, result.far_trace),
            cals,
        )

        if result.warnings:
            st.warning("Convention warning:\n\n" + "\n".join(f"• {w}" for w in result.warnings))

        st.markdown("### Result")
        st.write(f"**Trade date:** {result.trade_date} ({result.trade_date.strftime('%a')})")
        st.write(
            f"**Spot date:**  {result.spot_date} ({result.spot_date.strftime('%a')})"
            f"{days_caption(result.spot_date, result.trade_date)}"
        )
        if result.near_date:
            st.write(
                f"**Near leg:**   {result.near_date} ({result.near_date.strftime('%a')})"
                f"{days_caption(result.near_date, result.trade_date)}"
            )
        if result.far_date:
            st.write(
                f"**Far leg:**    {result.far_date} ({result.far_date.strftime('%a')})"
                f"{days_caption(result.far_date, result.trade_date)}"
            )
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
