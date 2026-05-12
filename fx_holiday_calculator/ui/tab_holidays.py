import json
from datetime import date
from pathlib import Path

import streamlit as st

from fx_holiday_calculator.calendars.loader import load_exchange_calendar, load_rtgs_calendar
from fx_holiday_calculator.calendars.national import get_national_calendar
from fx_holiday_calculator.conventions.cross import relevant_venues
from fx_holiday_calculator.holidays_view import list_holidays
from fx_holiday_calculator.pairs import list_supported_pairs, parse_pair
from fx_holiday_calculator.ui._widgets import (
    REF_CURRENCY_HELP,
    date_input_with_today,
    render_pair_conventions,
)

BUNDLED = Path(__file__).resolve().parents[2] / "data"
CACHE = Path.home() / ".fx_holiday_calculator" / "cache"

AVAILABLE_RTGS = {"EUR", "USD", "GBP", "JPY"}


def _available_exchange_venues() -> set[str]:
    bundled = BUNDLED / "fx_exchange"
    if not bundled.exists():
        return set()
    return {p.stem for p in bundled.glob("*.json") if not p.name.startswith("_")}


_CCY_TO_NATIONAL = {
    "USD": "US",
    "EUR": "DE",
    "GBP": "GB",
    "JPY": "JP",
}


def _available_pair_codes() -> list[str]:
    return [
        f"{p.base}/{p.quote}"
        for p in list_supported_pairs()
        if p.base in AVAILABLE_RTGS and p.quote in AVAILABLE_RTGS
    ]


def render() -> None:
    st.subheader("Holiday Calendar")

    pair_codes = _available_pair_codes()
    if not pair_codes:
        st.warning("No supported pairs available.")
        return

    col1, col2 = st.columns(2)
    default_idx = pair_codes.index("EUR/USD") if "EUR/USD" in pair_codes else 0
    pair_code = col1.selectbox("Currency pair", pair_codes, index=default_idx, key="hol_pair")
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
        ref = col2.radio(
            f"Reference currency (pair default: {pair_default})",
            ref_options,
            index=ref_options.index(pair_default),
            horizontal=True,
            help=REF_CURRENCY_HELP,
            key="hol_ref",
        )

    cal_mode = st.radio(
        "Calendar mode",
        ["FX (RTGS) only", "Exchange only", "Both"],
        index=0,
        horizontal=True,
        help=(
            "FX = RTGS settlement calendars (EUR/USD/GBP/JPY). "
            "Exchange = FX-futures venues (CME/HKEX/SGX). "
            "Both = union. Exchange and Both require bundled exchange data."
        ),
        key="hol_cal_mode",
    )
    cal_mode_key = {
        "FX (RTGS) only": "FX",
        "Exchange only": "EXCHANGE",
        "Both": "BOTH",
    }[cal_mode]

    include_national = st.checkbox(
        "Include national holidays (reference only)", value=False, key="hol_national"
    )

    today = date.today()
    c3, c4 = st.columns(2)
    start = date_input_with_today(c3, "Start date", key="hol_start", default=date(today.year, 1, 1))
    end = c4.date_input("End date", value=date(today.year, 12, 31), key="hol_end")

    needed_rtgs = {pair.base, pair.quote}
    if ref != "none":
        needed_rtgs.add(ref)

    try:
        rtgs = {
            c: load_rtgs_calendar(c, root=BUNDLED / "fx_rtgs", cache_root=CACHE / "fx_rtgs")
            for c in sorted(needed_rtgs)
        }
    except FileNotFoundError as exc:
        st.error(f"Calendar file missing: {exc}")
        return

    nat_cals = None
    if include_national:
        nat_cals = {}
        for c in needed_rtgs:
            code = _CCY_TO_NATIONAL.get(c)
            if code:
                nat_cals[code] = get_national_calendar(code)

    exch_cals: dict = {}
    if cal_mode_key in {"EXCHANGE", "BOTH"}:
        available_venues = _available_exchange_venues()
        needed_venues = set(relevant_venues(pair, ref))  # type: ignore[arg-type]
        missing = sorted(needed_venues - available_venues)
        if missing:
            st.error(
                f"{cal_mode} requires exchange calendars for venue(s) "
                f"{', '.join(missing)}, but none are bundled. "
                "Switch to FX (RTGS) only to view holidays."
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
                "**Exchange data caveat — library-sourced for "
                f"{', '.join(lib_venues)}.**\n\n"
                "Rows below come from `exchange_calendars` (equity session), "
                "not a primary venue document. Real FX-futures holidays may "
                "differ — these calendars omit per-product observances "
                "(e.g. CME equity calendar does NOT include US bank "
                "holidays observed by CME Globex FX futures). "
                "See `docs/data-sources.md` for the full caveat."
            )

    render_pair_conventions(pair)

    if st.button("Show"):
        rows = list_holidays(
            pair=pair,
            ref_currency=ref,  # type: ignore[arg-type]
            start=start,
            end=end,
            calendar_mode=cal_mode_key,
            include_national=include_national,
            rtgs_calendars=rtgs,
            exchange_calendars=exch_cals,
            national_calendars=nat_cals,
        )
        st.write(f"**{len(rows)} rows**")
        if not rows:
            return

        rendered = [
            {
                "Date": r.date.isoformat(),
                "Day": r.weekday,
                "Type": r.type,
                "Calendar": r.calendar,
                "Holiday": r.holiday_name,
                "Closure": "✓" if r.is_closure else "info",
                "Liquidity": r.liquidity or "",
                "Source": r.source_url,
                "Fetched": r.source_fetched_at.isoformat(),
                "Origin": r.source_origin,
            }
            for r in rows
        ]
        st.dataframe(rendered, use_container_width=True)

        csv = (
            "Date,Day,Type,Calendar,Holiday,Closure,Liquidity,Source,Fetched,Origin\n"
            + "\n".join(
                ",".join(str(v).replace(",", ";") for v in row.values()) for row in rendered
            )
        )
        st.download_button("Export CSV", data=csv, file_name="holidays.csv", mime="text/csv")
        st.download_button(
            "Export JSON",
            data=json.dumps(rendered, indent=2),
            file_name="holidays.json",
            mime="application/json",
        )
