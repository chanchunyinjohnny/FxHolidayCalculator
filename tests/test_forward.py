from datetime import date, datetime, timezone

import pytest

from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import HolidayEntry, SourceRef
from fx_holiday_calculator.forward import (
    ForwardResult,
    InvalidForwardTenorError,
    calculate_forward_dates,
)
from fx_holiday_calculator.pairs import parse_pair
from fx_holiday_calculator.swap import InvalidBrokenDateError
from fx_holiday_calculator.tenor import parse_tenor

WINDOW = dict(valid_from=date(2020, 1, 1), valid_until=date(2030, 12, 31))


def _src() -> SourceRef:
    return SourceRef(
        url="https://x",
        doc_title="x",
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        fetcher="t",
    )


def _empty(c: str) -> RtgsCalendar:
    return RtgsCalendar(currency=c, calendar_name=c, operator="x", entries_by_date={}, **WINDOW)


def test_forward_clean_eurusd_3m():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_forward_dates(
        trade_date=date(2026, 5, 6),  # Wed
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("3M"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 5, 8)  # Fri T+2
    assert r.settlement_date == date(2026, 8, 10)  # 2026-08-08 Sat -> Mon 8-10
    assert r.trade_date == date(2026, 5, 6)
    assert isinstance(r, ForwardResult)


def test_forward_broken_date():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_forward_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("2026-09-15"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.settlement_date == date(2026, 9, 15)


def test_forward_imm_tenor():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_forward_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("IMM1"),
        ref_currency="none",
        calendars=cals,
    )
    # IMM1 from spot 2026-05-08 -> June IMM = 2026-06-17 (3rd Wed).
    assert r.settlement_date == date(2026, 6, 17)


@pytest.mark.parametrize("bad", ["SPOT", "ON", "TN", "SN"])
def test_forward_rejects_non_forward_tenor(bad):
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    with pytest.raises(InvalidForwardTenorError):
        calculate_forward_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("EUR/USD"),
            tenor=parse_tenor(bad),
            ref_currency="none",
            calendars=cals,
        )


def test_forward_rejects_pre_spot_broken_target():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    with pytest.raises(InvalidBrokenDateError):
        calculate_forward_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("EUR/USD"),
            tenor=parse_tenor("2026-05-07"),  # before spot 2026-05-08
            ref_currency="none",
            calendars=cals,
        )


def test_forward_result_has_no_near_field():
    # Belt-and-braces: confirm the result dataclass does NOT expose a near_date,
    # so consumers won't be misled into thinking outright has a near leg.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_forward_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("3M"),
        ref_currency="none",
        calendars=cals,
    )
    assert not hasattr(r, "near_date")
    assert not hasattr(r, "near_trace")


def test_forward_holiday_rolls_settlement():
    # USD holiday on 2026-08-10 -> settlement rolls to next good BD.
    usd_hol = HolidayEntry(
        date=date(2026, 8, 10),
        name="Mock USD holiday",
        note=None,
        source=_src(),
        source_origin="bundled",
        is_closure=True,
    )
    usd = RtgsCalendar(
        currency="USD",
        calendar_name="USD",
        operator="x",
        entries_by_date={date(2026, 8, 10): usd_hol},
        **WINDOW,
    )
    cals = {"EUR": _empty("EUR"), "USD": usd}
    r = calculate_forward_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("3M"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.settlement_date == date(2026, 8, 11)


def test_forward_warnings_passthrough():
    # Forward should carry through any warnings produced by the swap engine.
    # An empty-calendar EUR/USD with no special conditions: warnings list is empty.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_forward_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("3M"),
        ref_currency="none",
        calendars=cals,
    )
    assert isinstance(r.warnings, list)
