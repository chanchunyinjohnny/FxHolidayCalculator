from datetime import date, datetime, timezone

import pytest

from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import HolidayEntry, SourceRef
from fx_holiday_calculator.option_otc import OtcOptionResult, calculate_otc_option_dates
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


def test_result_dataclass_shape():
    r = OtcOptionResult(
        trade_date=date(2026, 5, 6),
        spot_date=date(2026, 5, 8),
        expiry_date=date(2026, 6, 8),
        delivery_date=date(2026, 6, 10),
        spot_trace=[],
        expiry_trace=[],
        delivery_trace=[],
        calendars_used=[],
        warnings=[],
    )
    assert r.expiry_date < r.delivery_date


def test_otc_clean_eurusd_1m():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    r = calculate_otc_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("1M"),
        ref_currency="none",
        rtgs_calendars=cals,
    )
    assert r.spot_date == date(2026, 5, 8)
    assert r.expiry_date == date(2026, 6, 8)
    assert r.delivery_date == date(2026, 6, 10)


def test_otc_expiry_skips_holiday():
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
    r = calculate_otc_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("1M"),
        ref_currency="none",
        rtgs_calendars=cals,
    )
    assert r.expiry_date == date(2026, 6, 9)
    assert r.delivery_date == date(2026, 6, 11)


def test_otc_delivery_ignores_ref_currency_holiday():
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
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD"), "JPY": jpy}
    r = calculate_otc_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("1M"),
        ref_currency="JPY",  # type: ignore[arg-type]
        rtgs_calendars=cals,
    )
    assert r.delivery_date == date(2026, 6, 10)


def test_otc_delivery_uses_business_day_offset():
    usd_hol = HolidayEntry(
        date=date(2026, 6, 9),
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
        entries_by_date={date(2026, 6, 9): usd_hol},
        **WINDOW,
    )
    cals = {"EUR": _empty_rtgs("EUR"), "USD": usd}
    r = calculate_otc_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("1M"),
        ref_currency="none",
        rtgs_calendars=cals,
    )
    assert r.expiry_date == date(2026, 6, 8)
    assert r.delivery_date == date(2026, 6, 11)


@pytest.mark.parametrize("bad", ["SPOT", "ON", "TN", "SN"])
def test_otc_rejects_non_forward_tenor(bad):
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    with pytest.raises(InvalidTenorError):
        calculate_otc_option_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("EUR/USD"),
            tenor=parse_tenor(bad),
            ref_currency="none",
            rtgs_calendars=cals,
        )


def test_otc_spot_anchor_respects_ref_currency():
    jpy_hol = HolidayEntry(
        date=date(2026, 5, 8),
        name="JPY holiday on spot",
        note=None,
        source=_src(),
        source_origin="bundled",
        is_closure=True,
    )
    jpy = RtgsCalendar(
        currency="JPY",
        calendar_name="JPY",
        operator="x",
        entries_by_date={date(2026, 5, 8): jpy_hol},
        **WINDOW,
    )
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD"), "JPY": jpy}
    r = calculate_otc_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("1M"),
        ref_currency="JPY",  # type: ignore[arg-type]
        rtgs_calendars=cals,
    )
    assert r.spot_date == date(2026, 5, 11)


def test_otc_same_day_expiry_warning():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    r = calculate_otc_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("2026-05-08"),
        ref_currency="none",
        rtgs_calendars=cals,
    )
    assert r.expiry_date == r.spot_date
    assert any("expires on spot" in w for w in r.warnings)


def test_otc_imm_uses_rtgs_mod_following():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    r = calculate_otc_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("IMM1"),
        ref_currency="none",
        rtgs_calendars=cals,
    )
    # 3rd Wed Jun 2026 = 06-17 (Wed), clean -> expiry 06-17
    assert r.expiry_date == date(2026, 6, 17)
