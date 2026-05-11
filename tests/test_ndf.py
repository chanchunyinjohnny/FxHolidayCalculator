from datetime import date, datetime, timezone

import pytest

from fx_holiday_calculator.calendars.fixing import FixingCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import HolidayEntry, SourceRef
from fx_holiday_calculator.ndf import (
    InvalidNdfPairError,
    NdfResult,
    calculate_ndf_dates,
)
from fx_holiday_calculator.pairs import parse_pair
from fx_holiday_calculator.tenor import parse_tenor

WINDOW = dict(valid_from=date(2020, 1, 1), valid_until=date(2030, 12, 31))


def _src() -> SourceRef:
    return SourceRef(
        url="https://x",
        doc_title="x",
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        fetcher="t",
    )


def _empty_rtgs(c: str) -> RtgsCalendar:
    return RtgsCalendar(currency=c, calendar_name=c, operator="x", entries_by_date={}, **WINDOW)


def _empty_fixing(c: str) -> FixingCalendar:
    return FixingCalendar(
        currency=c, calendar_name=c, operator="x", entries_by_date={}, **WINDOW
    )


def test_reject_non_ndf_pair():
    cals = {"USD": _empty_rtgs("USD"), "EUR": _empty_rtgs("EUR")}
    fix = _empty_fixing("EUR")  # placeholder; will be rejected before use
    with pytest.raises(InvalidNdfPairError):
        calculate_ndf_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("EUR/USD"),
            tenor=parse_tenor("3M"),
            rtgs_calendars=cals,
            fixing_calendar=fix,
        )


def test_result_dataclass_shape():
    r = NdfResult(
        trade_date=date(2026, 5, 6),
        spot_date=date(2026, 5, 8),
        fixing_date=date(2026, 8, 6),
        settlement_date=date(2026, 8, 10),
        spot_trace=[],
        settlement_trace=[],
        fixing_trace=[],
        calendars_used=[],
        warnings=[],
    )
    assert r.trade_date == date(2026, 5, 6)
    assert r.fixing_date < r.settlement_date


def test_tenor_driven_3m_clean_dates():
    cals = {"USD": _empty_rtgs("USD")}
    fix = _empty_fixing("CNY")
    r = calculate_ndf_dates(
        trade_date=date(2026, 5, 6),  # Wed
        pair=parse_pair("USD/CNY"),
        tenor=parse_tenor("3M"),
        rtgs_calendars=cals,
        fixing_calendar=fix,
    )
    # Spot is T+2 on USD only -> 2026-05-08 (Fri)
    assert r.spot_date == date(2026, 5, 8)
    # Settlement = spot + 3M = 2026-08-08 (Sat) -> mod-following -> Mon 2026-08-10
    assert r.settlement_date == date(2026, 8, 10)
    # Fixing = settlement - 2BD on fixing cal -> 2026-08-06 (Thu)
    assert r.fixing_date == date(2026, 8, 6)
    assert r.fixing_date < r.settlement_date


def test_tenor_driven_fixing_skips_fixing_holiday():
    # CNY fixing has a holiday on Mon 2026-08-10 -> settlement rolls forward,
    # but if 2026-08-10 is good USD/RTGS but bad fixing, settlement must roll.
    cny_hol = HolidayEntry(
        date=date(2026, 8, 10),
        name="Mock holiday",
        note=None,
        source=_src(),
        source_origin="bundled",
        is_closure=True,
    )
    fix = FixingCalendar(
        currency="CNY",
        calendar_name="CNY",
        operator="x",
        entries_by_date={date(2026, 8, 10): cny_hol},
        **WINDOW,
    )
    cals = {"USD": _empty_rtgs("USD")}
    r = calculate_ndf_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("USD/CNY"),
        tenor=parse_tenor("3M"),
        rtgs_calendars=cals,
        fixing_calendar=fix,
    )
    # Settlement must skip 2026-08-10 -> 2026-08-11
    assert r.settlement_date == date(2026, 8, 11)
    # Fixing = settlement - 2 good BD on fixing cal.
    # From 2026-08-11 (Tue) walking back: 8-10 Mon (CNY holiday, skip),
    # 8-9 Sun, 8-8 Sat, 8-7 Fri (good, count=1), 8-6 Thu (good, count=2).
    assert r.fixing_date == date(2026, 8, 6)


def test_tenor_driven_imm_tenor():
    cals = {"USD": _empty_rtgs("USD")}
    fix = _empty_fixing("CNY")
    r = calculate_ndf_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("USD/CNY"),
        tenor=parse_tenor("IMM1"),  # next IMM after spot
        rtgs_calendars=cals,
        fixing_calendar=fix,
    )
    # IMM1 after spot 2026-05-08 -> June IMM = 2026-06-17 (3rd Wed)
    assert r.settlement_date == date(2026, 6, 17)
    # Fixing = 2 BD before, all good days -> 2026-06-15
    assert r.fixing_date == date(2026, 6, 15)


def test_trade_date_not_good_usd_rtgs():
    cals = {"USD": _empty_rtgs("USD")}
    fix = _empty_fixing("CNY")
    from fx_holiday_calculator.ndf import InvalidTradeDateError
    with pytest.raises(InvalidTradeDateError):
        calculate_ndf_dates(
            trade_date=date(2026, 5, 9),  # Sat
            pair=parse_pair("USD/CNY"),
            tenor=parse_tenor("3M"),
            rtgs_calendars=cals,
            fixing_calendar=fix,
        )


def test_maturity_driven_clean():
    cals = {"USD": _empty_rtgs("USD")}
    fix = _empty_fixing("CNY")
    r = calculate_ndf_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("USD/CNY"),
        target_settlement=date(2026, 8, 10),  # Mon — already a good day
        rtgs_calendars=cals,
        fixing_calendar=fix,
    )
    assert r.settlement_date == date(2026, 8, 10)
    assert r.fixing_date == date(2026, 8, 6)


def test_maturity_driven_rejects_pre_spot_target():
    cals = {"USD": _empty_rtgs("USD")}
    fix = _empty_fixing("CNY")
    from fx_holiday_calculator.ndf import InvalidBrokenDateError
    with pytest.raises(InvalidBrokenDateError):
        calculate_ndf_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("USD/CNY"),
            target_settlement=date(2026, 5, 7),  # before spot 2026-05-08
            rtgs_calendars=cals,
            fixing_calendar=fix,
        )


def test_rejects_both_tenor_and_target():
    cals = {"USD": _empty_rtgs("USD")}
    fix = _empty_fixing("CNY")
    with pytest.raises(ValueError):
        calculate_ndf_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("USD/CNY"),
            tenor=parse_tenor("3M"),
            target_settlement=date(2026, 8, 10),
            rtgs_calendars=cals,
            fixing_calendar=fix,
        )


def test_rejects_neither_tenor_nor_target():
    cals = {"USD": _empty_rtgs("USD")}
    fix = _empty_fixing("CNY")
    with pytest.raises(ValueError):
        calculate_ndf_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("USD/CNY"),
            rtgs_calendars=cals,
            fixing_calendar=fix,
        )


def test_ndf_eom_keyed_on_usd_not_fixing():
    # If the last BD of the spot month on the fixing calendar is BEFORE the
    # last BD on USD, and spot lands on the USD last-BD (good on USD, bad on
    # fixing), the EOM rule must STILL fire because spot was determined by
    # USD only. Without the fix, settle_cs's last-BD differs from spot, and
    # the EOM rule would incorrectly fail to fire.
    # Scenario: spot = 2026-05-29 (Fri, USD good). CNY has 2026-05-29 as
    # a holiday, making CNY's last May BD = 2026-05-28. Trade date chosen
    # so spot offset lands on 2026-05-29.
    cny_hol = HolidayEntry(
        date=date(2026, 5, 29),
        name="Mock CNY May-end holiday",
        note=None,
        source=_src(),
        source_origin="bundled",
        is_closure=True,
    )
    fix = FixingCalendar(
        currency="CNY",
        calendar_name="CNY",
        operator="x",
        entries_by_date={date(2026, 5, 29): cny_hol},
        **WINDOW,
    )
    cals = {"USD": _empty_rtgs("USD")}
    r = calculate_ndf_dates(
        trade_date=date(2026, 5, 27),  # Wed -> spot T+2 USD = 2026-05-29 Fri
        pair=parse_pair("USD/CNY"),
        tenor=parse_tenor("1M"),
        rtgs_calendars=cals,
        fixing_calendar=fix,
    )
    # Spot = 2026-05-29 (USD good, CNY bad — but spot uses USD only).
    assert r.spot_date == date(2026, 5, 29)
    # EOM rule fires: settlement = last BD of June 2026 on USD+CNY combined.
    # June 2026 last BD = 2026-06-30 (Tue) assuming no holidays.
    assert r.settlement_date == date(2026, 6, 30)


@pytest.mark.parametrize("bad", ["SPOT", "ON", "TN", "SN"])
def test_ndf_rejects_non_forward_tenor(bad):
    cals = {"USD": _empty_rtgs("USD")}
    fix = _empty_fixing("CNY")
    from fx_holiday_calculator.tenor import InvalidTenorError
    with pytest.raises(InvalidTenorError):
        calculate_ndf_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("USD/CNY"),
            tenor=parse_tenor(bad),
            rtgs_calendars=cals,
            fixing_calendar=fix,
        )
