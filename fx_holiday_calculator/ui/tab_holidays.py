import json
from datetime import date
from pathlib import Path

import streamlit as st

from fx_holiday_calculator.calendars.loader import load_rtgs_calendar
from fx_holiday_calculator.calendars.national import get_national_calendar
from fx_holiday_calculator.holidays_view import list_holidays
from fx_holiday_calculator.pairs import list_supported_pairs, parse_pair

BUNDLED = Path(__file__).resolve().parents[2] / "data"
CACHE = Path.home() / ".fx_holiday_calculator" / "cache"

AVAILABLE_RTGS = {"EUR", "USD", "GBP", "JPY"}

_CCY_TO_NATIONAL = {
    "USD": "US", "EUR": "DE", "GBP": "GB", "JPY": "JP",
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
    pair_code = col1.selectbox("Currency pair", pair_codes, index=default_idx)
    pair = parse_pair(pair_code)

    has_usd = "USD" in {pair.base, pair.quote}
    ref_options = ["none", "USD", "EUR"]
    default_ref = "none" if has_usd else "USD"
    ref = col2.radio(
        "Reference currency",
        ref_options,
        index=ref_options.index(default_ref),
        horizontal=True,
    )

    cal_mode = st.radio(
        "Calendar mode",
        ["FX (RTGS) only", "Exchange only", "Both"],
        index=0,
        horizontal=True,
        help="v1 has no Exchange calendars loaded; Exchange/Both shows only FX-RTGS rows.",
    )
    cal_mode_key = {
        "FX (RTGS) only": "FX",
        "Exchange only": "EXCHANGE",
        "Both": "BOTH",
    }[cal_mode]

    include_national = st.checkbox(
        "Include national holidays (reference only)", value=False
    )

    today = date.today()
    c3, c4 = st.columns(2)
    start = c3.date_input("Start date", value=date(today.year, 1, 1))
    end = c4.date_input("End date", value=date(today.year, 12, 31))

    needed_rtgs = {pair.base, pair.quote}
    if ref != "none":
        needed_rtgs.add(ref)

    try:
        rtgs = {
            c: load_rtgs_calendar(
                c, root=BUNDLED / "fx_rtgs", cache_root=CACHE / "fx_rtgs"
            )
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

    if cal_mode_key in {"EXCHANGE", "BOTH"}:
        st.info(
            "v1 has no exchange calendars loaded. Exchange-mode rows will be empty."
        )

    if st.button("Show"):
        rows = list_holidays(
            pair=pair,
            ref_currency=ref,  # type: ignore[arg-type]
            start=start,
            end=end,
            calendar_mode=cal_mode_key,
            include_national=include_national,
            rtgs_calendars=rtgs,
            exchange_calendars={},  # v1: no exchange data
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
                "Source": r.source_url,
                "Fetched": r.source_fetched_at.isoformat(),
                "Origin": r.source_origin,
            }
            for r in rows
        ]
        st.dataframe(rendered, use_container_width=True)

        csv = "Date,Day,Type,Calendar,Holiday,Source,Fetched,Origin\n" + "\n".join(
            ",".join(str(v).replace(",", ";") for v in row.values()) for row in rendered
        )
        st.download_button(
            "Export CSV", data=csv, file_name="holidays.csv", mime="text/csv"
        )
        st.download_button(
            "Export JSON",
            data=json.dumps(rendered, indent=2),
            file_name="holidays.json",
            mime="application/json",
        )
