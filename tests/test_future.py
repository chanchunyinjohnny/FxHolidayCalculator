from datetime import date, datetime, timezone

import pytest

from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import HolidayEntry, SourceRef
from fx_holiday_calculator.future import (
    FutureResult,
    InvalidContractMonthError,
    VenueCalendarMismatchError,
    VenueNotListedError,
    calculate_future_dates,
)
from fx_holiday_calculator.pairs import parse_pair
from fx_holiday_calculator.tenor import InvalidTenorError, parse_tenor

WINDOW = dict(valid_from=date(2020, 1, 1), valid_until=date(2030, 12, 31))


def _src() -> SourceRef:
    return SourceRef(
        url="x",
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


def test_rejects_venue_not_on_pair():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    sgx = _empty_exchange("SGX")
    with pytest.raises(VenueNotListedError):
        calculate_future_dates(
            pair=parse_pair("EUR/USD"),  # not SGX-listed
            venue="SGX",
            contract_month=(2026, 6),
            rtgs_calendars=cals,
            exchange_calendar=sgx,
        )


def test_rejects_neither_contract_month_nor_imm_tenor():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    cme = _empty_exchange("CME")
    with pytest.raises(ValueError):
        calculate_future_dates(
            pair=parse_pair("EUR/USD"),
            venue="CME",
            rtgs_calendars=cals,
            exchange_calendar=cme,
        )


def test_result_dataclass_shape():
    r = FutureResult(
        contract_month=(2026, 6),
        venue="CME",
        last_trade_date=date(2026, 6, 15),
        delivery_date=date(2026, 6, 17),
        imm_anchor=date(2026, 6, 17),
        last_trade_trace=[],
        delivery_trace=[],
        calendars_used=[],
        warnings=[],
    )
    assert r.last_trade_date < r.delivery_date


def test_future_contract_month_clean_eurusd_cme():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    cme = _empty_exchange("CME")
    r = calculate_future_dates(
        pair=parse_pair("EUR/USD"),
        venue="CME",
        contract_month=(2026, 6),
        rtgs_calendars=cals,
        exchange_calendar=cme,
        from_date=date(2026, 5, 6),  # avoid stale-contract warning
    )
    # 3rd Wed of June 2026 = 2026-06-17. Clean -> delivery same.
    assert r.delivery_date == date(2026, 6, 17)
    # LTD = 2 BD back = 2026-06-15 (Mon).
    assert r.last_trade_date == date(2026, 6, 15)


def test_future_ltd_anchored_to_unrolled_3rd_wed():
    # Make the 3rd Wed itself a CME holiday. Delivery rolls; LTD anchors to
    # unrolled 3rd Wed -> they drift apart by one day.
    cme_hol = HolidayEntry(
        date=date(2026, 6, 17),
        name="CME closed",
        note=None,
        source=_src(),
        source_origin="bundled",
        is_closure=True,
    )
    cme = ExchangeCalendar(
        venue="CME",
        products=("EURUSD",),
        entries_by_date={date(2026, 6, 17): cme_hol},
        library_sourced=False,
        **WINDOW,
    )
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    r = calculate_future_dates(
        pair=parse_pair("EUR/USD"),
        venue="CME",
        contract_month=(2026, 6),
        rtgs_calendars=cals,
        exchange_calendar=cme,
        from_date=date(2026, 5, 6),
    )
    # Delivery rolls past 2026-06-17 -> 2026-06-18 (Thu)
    assert r.delivery_date == date(2026, 6, 18)
    # LTD anchored to UNROLLED 2026-06-17. Count back 2 good BDs:
    # 06-16 (Tue, good) -> first; 06-15 (Mon, good) -> second. So LTD = 2026-06-15.
    assert r.last_trade_date == date(2026, 6, 15)


def test_future_imm_tenor_maps_to_correct_contract_month():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    cme = _empty_exchange("CME")
    r = calculate_future_dates(
        pair=parse_pair("EUR/USD"),
        venue="CME",
        imm_tenor=parse_tenor("IMM1"),
        from_date=date(2026, 5, 6),  # IMM1 from May 2026 = June 2026
        rtgs_calendars=cals,
        exchange_calendar=cme,
    )
    assert r.contract_month == (2026, 6)
    assert r.delivery_date == date(2026, 6, 17)


def test_future_imm_tenor_rejects_non_imm_tenor():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    cme = _empty_exchange("CME")
    with pytest.raises(InvalidTenorError):
        calculate_future_dates(
            pair=parse_pair("EUR/USD"),
            venue="CME",
            imm_tenor=parse_tenor("3M"),
            from_date=date(2026, 5, 6),
            rtgs_calendars=cals,
            exchange_calendar=cme,
        )


@pytest.mark.parametrize("venue", ["CME", "HKEX", "SGX"])
def test_future_all_three_venues_produce_same_dates_when_calendars_match(venue):
    # USD/CNH is listed on all three venues. With identical (empty) calendars,
    # all three produce the same dates.
    cals = {"USD": _empty_rtgs("USD"), "CNH": _empty_rtgs("CNH")}
    ex = _empty_exchange(venue)
    r = calculate_future_dates(
        pair=parse_pair("USD/CNH"),
        venue=venue,
        contract_month=(2026, 6),
        rtgs_calendars=cals,
        exchange_calendar=ex,
        from_date=date(2026, 5, 6),
    )
    assert r.delivery_date == date(2026, 6, 17)
    assert r.last_trade_date == date(2026, 6, 15)


def test_future_rejects_mismatched_exchange_calendar():
    # Declared venue is CME but the supplied calendar is for SGX. The engine
    # must refuse to silently compute on SGX while labelling the result CME.
    cals = {"USD": _empty_rtgs("USD"), "JPY": _empty_rtgs("JPY")}
    sgx_cal = _empty_exchange("SGX")
    with pytest.raises(VenueCalendarMismatchError):
        calculate_future_dates(
            pair=parse_pair("USD/JPY"),  # listed on both CME and SGX
            venue="CME",
            contract_month=(2026, 6),
            rtgs_calendars=cals,
            exchange_calendar=sgx_cal,
            from_date=date(2026, 5, 6),
        )


def test_future_rejects_stale_current_month_after_ltd(monkeypatch):
    # Contract month is technically not past, but its LTD has already passed.
    # Existing month-only check wouldn't catch this; the new date-aware
    # check must.
    import fx_holiday_calculator.future as future_module

    class FrozenDate(date):
        @classmethod
        def today(cls):
            # Day after expected LTD (2026-06-15) for June 2026 CME EUR/USD.
            return date(2026, 6, 16)

    monkeypatch.setattr(future_module, "date", FrozenDate)

    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    cme = _empty_exchange("CME")
    with pytest.raises(InvalidContractMonthError):
        calculate_future_dates(
            pair=parse_pair("EUR/USD"),
            venue="CME",
            contract_month=(2026, 6),
            rtgs_calendars=cals,
            exchange_calendar=cme,
        )


def test_future_past_contract_rejection():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    cme = _empty_exchange("CME")
    # No from_date -> uses today(). Past contract triggers InvalidContractMonthError.
    with pytest.raises(InvalidContractMonthError):
        calculate_future_dates(
            pair=parse_pair("EUR/USD"),
            venue="CME",
            contract_month=(2020, 6),
            rtgs_calendars=cals,
            exchange_calendar=cme,
        )
