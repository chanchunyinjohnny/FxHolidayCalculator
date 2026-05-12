from datetime import date, datetime, timezone

import pytest

from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import HolidayEntry, SourceRef
from fx_holiday_calculator.option import (
    InvalidOptionStyleError,
    ListedOptionVenueRequiredError,
    OptionResult,
    VenueCalendarMismatchError,
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
        spot_trace=[],
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


def test_listed_rejects_mismatched_exchange_calendar():
    # Declared venue is CME but the supplied exchange_calendar is for SGX.
    # Engine must refuse to silently compute on SGX while labelling as CME.
    cals = {"USD": _empty_rtgs("USD"), "JPY": _empty_rtgs("JPY")}
    sgx_cal = _empty_exchange("SGX")
    with pytest.raises(VenueCalendarMismatchError):
        calculate_option_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("USD/JPY"),  # listed on both CME and SGX
            tenor=parse_tenor("1M"),
            style="LISTED",
            ref_currency="none",
            rtgs_calendars=cals,
            exchange_calendar=sgx_cal,
            venue="CME",
        )


def test_listed_option_ignores_ref_currency_in_spot_anchor():
    # ref=JPY has a holiday on what would be the OTC spot date for EUR/USD
    # (T+2 from Wed 2026-05-06 -> Fri 2026-05-08). For LISTED, ref must not
    # enter the spot anchor calendar set, so spot stays on 2026-05-08.
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
    cme = _empty_exchange("CME")
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD"), "JPY": jpy}
    r = calculate_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("1M"),
        style="LISTED",
        ref_currency="JPY",  # type: ignore[arg-type]
        rtgs_calendars=cals,
        exchange_calendar=cme,
        venue="CME",
    )
    # Spot anchor ignores JPY — stays on 2026-05-08
    assert r.spot_date == date(2026, 5, 8)
    # Expiry rolls only on the (empty) CME calendar — clean Mon 2026-06-08
    assert r.expiry_date == date(2026, 6, 8)


def test_otc_option_spot_anchor_respects_ref_currency():
    # Mirror of the LISTED test above: confirm OTC path *does* shift the
    # spot anchor when ref currency has a holiday on the otherwise-spot date.
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
    r = calculate_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("1M"),
        style="OTC",
        ref_currency="JPY",  # type: ignore[arg-type]
        rtgs_calendars=cals,
    )
    # OTC spot moves past JPY holiday -> Mon 2026-05-11
    assert r.spot_date == date(2026, 5, 11)


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


# --- Listed-option IMM expiry: 2 BDs before unrolled 3rd Wed on exchange ---


def _hol_exchange(venue: str, days: list[date]) -> ExchangeCalendar:
    entries = {
        d: HolidayEntry(d, "Exchange closed", None, _src(), "bundled", is_closure=True)
        for d in days
    }
    return ExchangeCalendar(
        venue=venue, products=(), entries_by_date=entries, library_sourced=False, **WINDOW
    )


def test_listed_imm_expiry_clean_cme_eurusd():
    # IMM1 from May 6 2026 → contract month June 2026. 3rd Wed = 06-17 (Wed).
    # No exchange holidays → expiry = 2 BD before = 06-15 (Mon). Delivery
    # = expiry + 2 BD = 06-17 (Wed).
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    r = calculate_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("IMM1"),
        style="LISTED",
        rtgs_calendars=cals,
        exchange_calendar=_empty_exchange("CME"),
        venue="CME",
    )
    assert r.expiry_date == date(2026, 6, 15)
    assert r.delivery_date == date(2026, 6, 17)


def test_listed_imm_expiry_clean_hkex_usdcnh():
    # Same as above but on HKEX USD/CNH. The HKEX spec wording uses rolled
    # FSD as the anchor; the back-count produces the identical date.
    cals = {"USD": _empty_rtgs("USD"), "CNH": _empty_rtgs("CNH")}
    r = calculate_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("USD/CNH"),
        tenor=parse_tenor("IMM1"),
        style="LISTED",
        rtgs_calendars=cals,
        exchange_calendar=_empty_exchange("HKEX"),
        venue="HKEX",
    )
    assert r.expiry_date == date(2026, 6, 15)
    assert r.delivery_date == date(2026, 6, 17)


def test_listed_imm_expiry_skips_exchange_holiday_in_back_count():
    # 3rd Wed = 06-17 (Wed). Make Tue 06-16 a HKEX holiday. Back-count from
    # 06-17 skips 06-16 → expiry = 06-15 (Mon). Skipping 06-12 weekend isn't
    # tested here; this is the holiday-skip case.
    cals = {"USD": _empty_rtgs("USD"), "CNH": _empty_rtgs("CNH")}
    hkex_hol = _hol_exchange("HKEX", [date(2026, 6, 16)])
    r = calculate_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("USD/CNH"),
        tenor=parse_tenor("IMM1"),
        style="LISTED",
        rtgs_calendars=cals,
        exchange_calendar=hkex_hol,
        venue="HKEX",
    )
    # Back from 06-17: 06-16 (holiday, skip), 06-15 (Mon, good)=1,
    # 06-14 (Sun skip), 06-13 (Sat skip), 06-12 (Fri, good)=2 → 06-12.
    assert r.expiry_date == date(2026, 6, 12)


def test_listed_imm_expiry_hkex_cme_rule_equivalence():
    # The HKEX rule and the CME rule produce identical expiry dates in
    # every case because the back-count traverses the chain of non-BDs
    # between the unrolled 3rd Wed and the rolled FSD identically. This
    # test pins that property: same exchange calendar (modulo venue label),
    # same expiry.
    cals_eu = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    cals_uc = {"USD": _empty_rtgs("USD"), "CNH": _empty_rtgs("CNH")}
    holidays = [date(2026, 6, 17), date(2026, 6, 16)]  # 3rd Wed + Tue both closed
    cme = calculate_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("IMM1"),
        style="LISTED",
        rtgs_calendars=cals_eu,
        exchange_calendar=_hol_exchange("CME", holidays),
        venue="CME",
    )
    hkex = calculate_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("USD/CNH"),
        tenor=parse_tenor("IMM1"),
        style="LISTED",
        rtgs_calendars=cals_uc,
        exchange_calendar=_hol_exchange("HKEX", holidays),
        venue="HKEX",
    )
    assert cme.expiry_date == hkex.expiry_date
    # And the date itself: imm=06-17 holiday, 06-16 holiday → back from 06-17:
    # 06-16 (skip), 06-15 (Mon)=1, 06-14 (Sun skip), 06-13 (Sat skip),
    # 06-12 (Fri)=2 → expiry = 06-12.
    assert cme.expiry_date == date(2026, 6, 12)


def test_otc_imm_unaffected_by_listed_rule_change():
    # OTC + IMM keeps the original "3rd Wed rolled modified-following on RTGS"
    # behavior — no 2-BD back-count for OTC.
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    r = calculate_option_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        tenor=parse_tenor("IMM1"),
        style="OTC",
        ref_currency="none",
        rtgs_calendars=cals,
    )
    # 3rd Wed = 06-17 (Wed), no RTGS holidays → no adjustment → expiry = 06-17.
    assert r.expiry_date == date(2026, 6, 17)
