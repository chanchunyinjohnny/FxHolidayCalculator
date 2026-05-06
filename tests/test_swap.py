import pytest
from datetime import date, datetime, timezone

from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import HolidayEntry, SourceRef
from fx_holiday_calculator.pairs import parse_pair
from fx_holiday_calculator.swap import calculate_swap_dates, InvalidFFSCombinationError
from fx_holiday_calculator.tenor import parse_tenor


def _empty(c: str) -> RtgsCalendar:
    return RtgsCalendar(currency=c, calendar_name=c, operator="x", entries_by_date={})


def _hol(c: str, days: list[date]) -> RtgsCalendar:
    src = SourceRef(url="https://x", doc_title="x",
                    fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc), fetcher="t")
    return RtgsCalendar(currency=c, calendar_name=c, operator="x",
                        entries_by_date={d: HolidayEntry(d, "x", None, src, "bundled") for d in days})


def test_spot_tenor_returns_only_spot():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    result = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("SPOT"),
        ref_currency="none",
        calendars=cals,
    )
    assert result.spot_date == date(2026, 5, 8)
    assert result.near_date is None
    assert result.far_date is None


def test_on_tenor():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6), pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("ON"), ref_currency="none", calendars=cals,
    )
    assert r.near_date == date(2026, 5, 6)
    assert r.far_date == date(2026, 5, 7)


def test_tn_tenor():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6), pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("TN"), ref_currency="none", calendars=cals,
    )
    assert r.near_date == date(2026, 5, 7)
    assert r.far_date == date(2026, 5, 8)
    assert r.far_date == r.spot_date


def test_sn_tenor():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6), pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("SN"), ref_currency="none", calendars=cals,
    )
    assert r.near_date == r.spot_date  # 5-8 Fri
    assert r.far_date == date(2026, 5, 11)  # next BD after Fri (Mon)


def test_period_3m_eurusd():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6), pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("3M"), ref_currency="none", calendars=cals,
    )
    assert r.spot_date == date(2026, 5, 8)
    assert r.near_date == date(2026, 5, 8)
    # raw far = 2026-08-08 (Sat) → mod-following → 2026-08-10 (Mon).
    assert r.far_date == date(2026, 8, 10)


def test_imm_tenor():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6), pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("IMM1"), ref_currency="none", calendars=cals,
    )
    # IMM1 from May 6 spot 5/8 → next IMM month = Jun 2026 → 3rd Wed = 2026-06-17
    assert r.far_date == date(2026, 6, 17)


def test_broken_date():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6), pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("2026-08-15"), ref_currency="none", calendars=cals,
    )
    # 2026-08-15 is Sat → mod-following → Mon 2026-08-17.
    assert r.far_date == date(2026, 8, 17)


def test_ffs_period_period():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6), pair=parse_pair("EUR/USD"),
        near_tenor=parse_tenor("1M"),
        far_tenor=parse_tenor("3M"),
        ref_currency="none", calendars=cals,
    )
    # spot = 2026-05-08; near = +1M → 2026-06-08; far = +3M → 2026-08-08 (Sat) → 08-10.
    assert r.spot_date == date(2026, 5, 8)
    assert r.near_date == date(2026, 6, 8)
    assert r.far_date == date(2026, 8, 10)


def test_ffs_rejects_on_in_far_tenor():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    with pytest.raises(InvalidFFSCombinationError):
        calculate_swap_dates(
            trade_date=date(2026, 5, 6), pair=parse_pair("EUR/USD"),
            near_tenor=parse_tenor("1M"),
            far_tenor=parse_tenor("ON"),
            ref_currency="none", calendars=cals,
        )


def test_ffs_rejects_far_le_near():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    with pytest.raises(InvalidFFSCombinationError):
        calculate_swap_dates(
            trade_date=date(2026, 5, 6), pair=parse_pair("EUR/USD"),
            near_tenor=parse_tenor("3M"),
            far_tenor=parse_tenor("1M"),
            ref_currency="none", calendars=cals,
        )
