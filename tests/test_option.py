from datetime import date, datetime, timezone

import pytest

from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import HolidayEntry, SourceRef
from fx_holiday_calculator.option import (
    InvalidOptionStyleError,
    ListedOptionVenueRequiredError,
    OptionResult,
    calculate_option_dates,
)
from fx_holiday_calculator.pairs import parse_pair
from fx_holiday_calculator.tenor import InvalidTenorError, parse_tenor

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


def _empty_exchange(v: str) -> ExchangeCalendar:
    return ExchangeCalendar(
        venue=v, products=(), entries_by_date={}, library_sourced=False, **WINDOW
    )


def test_rejects_unknown_style():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    with pytest.raises(InvalidOptionStyleError):
        calculate_option_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("EUR/USD"),
            tenor=parse_tenor("1M"),
            style="HYBRID",  # type: ignore[arg-type]
            rtgs_calendars=cals,
        )


def test_listed_requires_venue_and_exchange_cal():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    with pytest.raises(ListedOptionVenueRequiredError):
        calculate_option_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("EUR/USD"),
            tenor=parse_tenor("1M"),
            style="LISTED",
            rtgs_calendars=cals,
        )


def test_result_dataclass_shape():
    r = OptionResult(
        trade_date=date(2026, 5, 6),
        spot_date=date(2026, 5, 8),
        expiry_date=date(2026, 6, 8),
        delivery_date=date(2026, 6, 10),
        style="OTC",
        expiry_trace=[],
        delivery_trace=[],
        calendars_used=[],
        warnings=[],
    )
    assert r.expiry_date < r.delivery_date


def test_otc_option_clean_eurusd_1m():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    r = calculate_option_dates(
        trade_date=date(2026, 5, 6),  # Wed
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("1M"),
        style="OTC",
        ref_currency="none",
        rtgs_calendars=cals,
    )
    # Spot = T+2 on EUR+USD -> 2026-05-08 (Fri)
    assert r.spot_date == date(2026, 5, 8)
    # Expiry = spot + 1M -> 2026-06-08 (Mon — good day)
    assert r.expiry_date == date(2026, 6, 8)
    # Delivery = expiry + 2 BD -> 2026-06-10 (Wed)
    assert r.delivery_date == date(2026, 6, 10)


def test_otc_option_expiry_skips_holiday():
    # EUR has a holiday on 2026-06-08 -> expiry rolls forward.
    eur_hol = HolidayEntry(
        date=date(2026, 6, 8),
        name="Mock",
        note=None,
        source=_src(),
        source_origin="bundled",
        is_closure=True,
    )
    eur = RtgsCalendar(
        currency="EUR",
        calendar_name="EUR",
        operator="x",
        entries_by_date={date(2026, 6, 8): eur_hol},
        **WINDOW,
    )
    cals = {"EUR": eur, "USD": _empty_rtgs("USD")}
    r = calculate_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("1M"),
        style="OTC",
        ref_currency="none",
        rtgs_calendars=cals,
    )
    assert r.expiry_date == date(2026, 6, 9)  # rolled past EUR holiday
    assert r.delivery_date == date(2026, 6, 11)  # spot lag from new expiry


def test_otc_option_delivery_ignores_ref_currency_holiday():
    # ref=JPY has a holiday on the delivery candidate. Delivery should not
    # be constrained by the reference currency — only by base + quote.
    jpy_hol = HolidayEntry(
        date=date(2026, 6, 10),
        name="Mock",
        note=None,
        source=_src(),
        source_origin="bundled",
        is_closure=True,
    )
    jpy = RtgsCalendar(
        currency="JPY",
        calendar_name="JPY",
        operator="x",
        entries_by_date={date(2026, 6, 10): jpy_hol},
        **WINDOW,
    )
    cals = {
        "EUR": _empty_rtgs("EUR"),
        "USD": _empty_rtgs("USD"),
        "JPY": jpy,
    }
    r = calculate_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("1M"),
        style="OTC",
        ref_currency="JPY",  # type: ignore[arg-type]
        rtgs_calendars=cals,
    )
    # Delivery still falls on 2026-06-10 because JPY does not constrain delivery.
    assert r.delivery_date == date(2026, 6, 10)


def test_listed_option_expiry_rolls_on_exchange_only():
    # CME has a holiday on 2026-06-08; EUR/USD RTGS do not.
    cme_hol = HolidayEntry(
        date=date(2026, 6, 8),
        name="CME closed",
        note=None,
        source=_src(),
        source_origin="bundled",
        is_closure=True,
    )
    cme = ExchangeCalendar(
        venue="CME",
        products=("EURUSD",),
        entries_by_date={date(2026, 6, 8): cme_hol},
        library_sourced=False,
        **WINDOW,
    )
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    r = calculate_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("1M"),
        style="LISTED",
        ref_currency="none",
        rtgs_calendars=cals,
        exchange_calendar=cme,
        venue="CME",
    )
    # Expiry rolls past CME holiday -> 2026-06-09
    assert r.expiry_date == date(2026, 6, 9)
    # Delivery on RTGS-only (no CME) -> 2026-06-11
    assert r.delivery_date == date(2026, 6, 11)


def test_listed_option_rtgs_holiday_does_not_shift_expiry():
    # EUR has a holiday on 2026-06-08 but CME does not. Expiry stays on
    # 2026-06-08 because LISTED option expiry rolls only on exchange.
    eur_hol = HolidayEntry(
        date=date(2026, 6, 8),
        name="EUR holiday",
        note=None,
        source=_src(),
        source_origin="bundled",
        is_closure=True,
    )
    eur = RtgsCalendar(
        currency="EUR",
        calendar_name="EUR",
        operator="x",
        entries_by_date={date(2026, 6, 8): eur_hol},
        **WINDOW,
    )
    cme = _empty_exchange("CME")
    cals = {"EUR": eur, "USD": _empty_rtgs("USD")}
    r = calculate_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("1M"),
        style="LISTED",
        ref_currency="none",
        rtgs_calendars=cals,
        exchange_calendar=cme,
        venue="CME",
    )
    assert r.expiry_date == date(2026, 6, 8)
    # But delivery, which uses RTGS, rolls past EUR holiday at expiry+2 BD
    assert r.delivery_date >= date(2026, 6, 10)


def test_otc_option_delivery_uses_business_day_offset():
    # USD holiday on the Tuesday between expiry (Mon) and calendar-day-2 (Wed).
    # Old logic (calendar+2 + roll) would yield Wed 2026-06-10 (clean).
    # New logic (apply_spot_offset = walk N good BDs) skips Tue and yields
    # Thu 2026-06-11.
    usd_hol = HolidayEntry(
        date=date(2026, 6, 9),
        name="Mock USD holiday on the Tuesday after expiry",
        note=None,
        source=_src(),
        source_origin="bundled",
        is_closure=True,
    )
    usd = RtgsCalendar(
        currency="USD",
        calendar_name="USD",
        operator="x",
        entries_by_date={date(2026, 6, 9): usd_hol},
        **WINDOW,
    )
    cals = {"EUR": _empty_rtgs("EUR"), "USD": usd}
    r = calculate_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("1M"),
        style="OTC",
        ref_currency="none",
        rtgs_calendars=cals,
    )
    assert r.expiry_date == date(2026, 6, 8)
    # Business-day-walk from 06-08: 06-09 (Tue, USD bad, skip), 06-10 (Wed, good, count 1),
    # 06-11 (Thu, good, count 2). Delivery = 06-11.
    assert r.delivery_date == date(2026, 6, 11)


@pytest.mark.parametrize("bad", ["SPOT", "ON", "TN", "SN"])
def test_option_rejects_non_forward_tenor(bad):
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    with pytest.raises(InvalidTenorError):
        calculate_option_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("EUR/USD"),
            tenor=parse_tenor(bad),
            style="OTC",
            ref_currency="none",
            rtgs_calendars=cals,
        )


def test_option_same_day_expiry_warning():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    # BROKEN tenor with target == spot date triggers same-day-expiry.
    r = calculate_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("2026-05-08"),  # spot
        style="OTC",
        ref_currency="none",
        rtgs_calendars=cals,
    )
    assert r.expiry_date == r.spot_date
    assert any("expires on spot" in w for w in r.warnings)
