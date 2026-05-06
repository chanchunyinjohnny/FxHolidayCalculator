from datetime import date, datetime, timezone

from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.national import get_national_calendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import HolidayEntry, SourceRef
from fx_holiday_calculator.holidays_view import HolidayRow, list_holidays
from fx_holiday_calculator.pairs import parse_pair


def _cal(c: str, days_with_names: list[tuple[date, str]]) -> RtgsCalendar:
    src = SourceRef(url="https://x", doc_title="x",
                    fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc), fetcher="t")
    entries = {d: HolidayEntry(d, n, None, src, "bundled") for d, n in days_with_names}
    return RtgsCalendar(currency=c, calendar_name=c, operator="x", entries_by_date=entries)


def _exch(v: str, days: list[tuple[date, str]]) -> ExchangeCalendar:
    src = SourceRef(url="https://e", doc_title="e",
                    fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc), fetcher="t")
    entries = {d: HolidayEntry(d, n, None, src, "bundled") for d, n in days}
    return ExchangeCalendar(venue=v, products=("X",), entries_by_date=entries)


def test_lists_fx_holidays_for_pair_in_range():
    rtgs = {
        "USD": _cal("USD", [(date(2026, 1, 1), "New Year's Day"),
                              (date(2026, 1, 19), "MLK Day")]),
        "JPY": _cal("JPY", [(date(2026, 1, 1), "New Year's Day"),
                              (date(2026, 1, 12), "Coming of Age Day")]),
    }
    rows = list_holidays(
        pair=parse_pair("USD/JPY"),
        ref_currency="none",
        start=date(2026, 1, 1),
        end=date(2026, 1, 31),
        calendar_mode="FX",
        rtgs_calendars=rtgs,
        exchange_calendars={},
    )
    # 4 entries: USD x 2, JPY x 2 (one shared date but 2 calendars produce 2 rows on Jan 1).
    assert len(rows) == 4
    assert all(isinstance(r, HolidayRow) for r in rows)
    assert all(r.type == "FX_RTGS" for r in rows)


def test_exchange_rows_appear_when_mode_exchange():
    rtgs = {"USD": _cal("USD", []), "CNH": _cal("CNH", [])}
    exch = {"HKEX": _exch("HKEX", [(date(2026, 2, 17), "Lunar New Year")])}
    rows = list_holidays(
        pair=parse_pair("USD/CNH"), ref_currency="none",
        start=date(2026, 1, 1), end=date(2026, 12, 31),
        calendar_mode="EXCHANGE",
        rtgs_calendars=rtgs, exchange_calendars=exch,
    )
    assert len(rows) == 1
    assert rows[0].type == "EXCHANGE"
    assert rows[0].calendar == "HKEX"


def test_both_mode_includes_rtgs_and_exchange():
    rtgs = {"USD": _cal("USD", [(date(2026, 1, 1), "NYD")]),
            "CNH": _cal("CNH", [(date(2026, 1, 1), "NYD")])}
    exch = {"HKEX": _exch("HKEX", [(date(2026, 1, 1), "NYD")])}
    rows = list_holidays(
        pair=parse_pair("USD/CNH"), ref_currency="none",
        start=date(2026, 1, 1), end=date(2026, 1, 1),
        calendar_mode="BOTH",
        rtgs_calendars=rtgs, exchange_calendars=exch,
    )
    types = {r.type for r in rows}
    assert types == {"FX_RTGS", "EXCHANGE"}


def test_holiday_row_carries_liquidity_when_informational():
    src = SourceRef(url="https://x", doc_title="x",
                    fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc), fetcher="t")
    info = HolidayEntry(date=date(2026, 11, 27), name="DAT", note=None,
                        source=src, source_origin="bundled",
                        is_closure=False, liquidity="thin")
    cal = RtgsCalendar(currency="USD", calendar_name="USD", operator="x",
                       entries_by_date={date(2026, 11, 27): info})
    rows = list_holidays(
        pair=parse_pair("EUR/USD"), ref_currency="none",
        start=date(2026, 11, 1), end=date(2026, 11, 30),
        calendar_mode="FX",
        rtgs_calendars={"USD": cal, "EUR": _cal("EUR", [])},
        exchange_calendars={},
    )
    # Should still be in the list (the listing iterates entries_by_date).
    matching = [r for r in rows if r.date == date(2026, 11, 27)]
    assert len(matching) == 1
    assert matching[0].is_closure is False
    assert matching[0].liquidity == "thin"


def test_national_rows_appear_only_when_toggled():
    rtgs = {"USD": _cal("USD", []), "JPY": _cal("JPY", [])}
    nationals = {"US": get_national_calendar("US"), "JP": get_national_calendar("JP")}
    rows_off = list_holidays(
        pair=parse_pair("USD/JPY"), ref_currency="none",
        start=date(2026, 7, 1), end=date(2026, 7, 31),
        calendar_mode="FX", include_national=False,
        rtgs_calendars=rtgs, exchange_calendars={}, national_calendars=nationals,
    )
    rows_on = list_holidays(
        pair=parse_pair("USD/JPY"), ref_currency="none",
        start=date(2026, 7, 1), end=date(2026, 7, 31),
        calendar_mode="FX", include_national=True,
        rtgs_calendars=rtgs, exchange_calendars={}, national_calendars=nationals,
    )
    assert all(r.type != "NATIONAL" for r in rows_off)
    assert any(r.type == "NATIONAL" and r.is_reference_only for r in rows_on)
