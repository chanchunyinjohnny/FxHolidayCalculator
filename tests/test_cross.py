from datetime import date, datetime, timezone

from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import HolidayEntry, SourceRef
from fx_holiday_calculator.conventions.cross import rtgs_calendar_set, relevant_venues
from fx_holiday_calculator.pairs import parse_pair


def _empty(c: str) -> RtgsCalendar:
    return RtgsCalendar(currency=c, calendar_name=c, operator="x", entries_by_date={})


def test_eurusd_with_ref_none_uses_two_calendars():
    cs = rtgs_calendar_set(parse_pair("EUR/USD"), ref="none",
                            calendars={"EUR": _empty("EUR"), "USD": _empty("USD"),
                                       "JPY": _empty("JPY")})
    assert set(cs.members.keys()) == {"EUR", "USD"}


def test_eurjpy_with_ref_usd_unions_three():
    cs = rtgs_calendar_set(parse_pair("EUR/JPY"), ref="USD",
                            calendars={"EUR": _empty("EUR"), "JPY": _empty("JPY"),
                                       "USD": _empty("USD")})
    assert set(cs.members.keys()) == {"EUR", "JPY", "USD"}


def test_usdjpy_with_ref_usd_dedups():
    cs = rtgs_calendar_set(parse_pair("USD/JPY"), ref="USD",
                            calendars={"USD": _empty("USD"), "JPY": _empty("JPY")})
    assert set(cs.members.keys()) == {"USD", "JPY"}


def test_eurjpy_relevant_venues_via_usd():
    venues = relevant_venues(parse_pair("EUR/JPY"), ref="USD")
    assert "CME" in venues   # EUR/JPY listed on CME directly + EUR/USD + USD/JPY also CME


def test_hkdcnh_relevant_venues_via_usd():
    venues = relevant_venues(parse_pair("HKD/CNH"), ref="USD")
    # HKD/CNH on HKEX directly, USD/HKD on HKEX, USD/CNH on CME/HKEX/SGX.
    assert "HKEX" in venues
    assert "CME" in venues
    assert "SGX" in venues
