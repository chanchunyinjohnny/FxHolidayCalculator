from datetime import date, datetime, timezone

from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import HolidayEntry, SourceRef
from fx_holiday_calculator.conventions.business_day import CalendarSet
from fx_holiday_calculator.conventions.spot_offset import apply_spot_offset
from fx_holiday_calculator.pairs import parse_pair


def _empty_cal(c: str) -> RtgsCalendar:
    return RtgsCalendar(currency=c, calendar_name=c, operator="x", entries_by_date={})


def _holiday_cal(c: str, h: list[date]) -> RtgsCalendar:
    src = SourceRef(
        url="https://x", doc_title="x",
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc), fetcher="t",
    )
    return RtgsCalendar(
        currency=c, calendar_name=c, operator="x",
        entries_by_date={d: HolidayEntry(d, "x", None, src, "bundled") for d in h},
    )


def test_eurusd_t2_simple():
    cs = CalendarSet({"EUR": _empty_cal("EUR"), "USD": _empty_cal("USD")})
    pair = parse_pair("EUR/USD")
    result = apply_spot_offset(date(2026, 5, 6), pair, cs)
    assert result.spot_date == date(2026, 5, 8)
    assert len(result.trace) == 2  # +1, +2


def test_usdcad_t1():
    cs = CalendarSet({"USD": _empty_cal("USD"), "CAD": _empty_cal("CAD")})
    pair = parse_pair("USD/CAD")
    result = apply_spot_offset(date(2026, 5, 6), pair, cs)
    assert result.spot_date == date(2026, 5, 7)
    assert len(result.trace) == 1


def test_holiday_extends_spot_offset():
    cs = CalendarSet({
        "EUR": _holiday_cal("EUR", [date(2026, 5, 7)]),
        "USD": _empty_cal("USD"),
    })
    pair = parse_pair("EUR/USD")
    result = apply_spot_offset(date(2026, 5, 6), pair, cs)
    # +1 (5-7) is EUR holiday → reject; +1 (5-8) accepted; +2 (5-11 Mon, since 5-9/10 weekend).
    assert result.spot_date == date(2026, 5, 11)
