from datetime import date, datetime, timezone

import pytest

from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import HolidayEntry, SourceRef
from fx_holiday_calculator.option_listed import ContractMonthDerivationError, derive_contract
from fx_holiday_calculator.pairs import parse_pair

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


def _hol_exchange(venue: str, days: list[date]) -> ExchangeCalendar:
    entries = {
        d: HolidayEntry(d, "Exchange closed", None, _src(), "bundled", is_closure=True)
        for d in days
    }
    return ExchangeCalendar(
        venue=venue, products=(), entries_by_date=entries, library_sourced=False, **WINDOW
    )


def test_derive_clean_cme_eurusd_jun2026():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    result = derive_contract(
        venue="CME",
        pair=parse_pair("EUR/USD"),
        contract_month=(2026, 6),
        rtgs_calendars=cals,
        exchange_calendar=_empty_exchange("CME"),
    )
    # 3rd Wed Jun 2026 = 06-17. Expiry = 2 BD prior = 06-15 (Mon). Delivery = +2 BD = 06-17.
    assert result.expiry_date == date(2026, 6, 15)
    assert result.delivery_date == date(2026, 6, 17)
    assert result.imm_anchor == date(2026, 6, 17)


def test_derive_clean_hkex_usdcnh_jun2026():
    cals = {"USD": _empty_rtgs("USD"), "CNH": _empty_rtgs("CNH")}
    result = derive_contract(
        venue="HKEX",
        pair=parse_pair("USD/CNH"),
        contract_month=(2026, 6),
        rtgs_calendars=cals,
        exchange_calendar=_empty_exchange("HKEX"),
    )
    assert result.expiry_date == date(2026, 6, 15)
    assert result.delivery_date == date(2026, 6, 17)


def test_derive_skips_exchange_holiday_in_back_count():
    cals = {"USD": _empty_rtgs("USD"), "CNH": _empty_rtgs("CNH")}
    result = derive_contract(
        venue="HKEX",
        pair=parse_pair("USD/CNH"),
        contract_month=(2026, 6),
        rtgs_calendars=cals,
        exchange_calendar=_hol_exchange("HKEX", [date(2026, 6, 16)]),
    )
    # 06-17 (3rd Wed) - back: 06-16 (hol skip), 06-15 (Mon)=1,
    # 06-14/06-13 weekend skip, 06-12 (Fri)=2 -> expiry 06-12.
    assert result.expiry_date == date(2026, 6, 12)


def test_derive_rejects_venue_not_in_pair_listed_on():
    cals = {"EUR": _empty_rtgs("EUR"), "USD": _empty_rtgs("USD")}
    with pytest.raises(ContractMonthDerivationError, match="not listed on HKEX"):
        derive_contract(
            venue="HKEX",
            pair=parse_pair("EUR/USD"),
            contract_month=(2026, 6),
            rtgs_calendars=cals,
            exchange_calendar=_empty_exchange("HKEX"),
        )


def test_derive_rejects_exchange_calendar_mismatch():
    cals = {"USD": _empty_rtgs("USD"), "CNH": _empty_rtgs("CNH")}
    with pytest.raises(ContractMonthDerivationError, match="exchange_calendar.venue"):
        derive_contract(
            venue="HKEX",
            pair=parse_pair("USD/CNH"),
            contract_month=(2026, 6),
            rtgs_calendars=cals,
            exchange_calendar=_empty_exchange("CME"),
        )


def test_derive_delivery_uses_spot_offset_on_rtgs():
    # USD holiday on Tue 06-16 between expiry (Mon 06-15) and Wed 06-17 ->
    # delivery should walk past USD hol to Thu 06-18.
    usd_hol = HolidayEntry(
        date=date(2026, 6, 16),
        name="USD bad",
        note=None,
        source=_src(),
        source_origin="bundled",
        is_closure=True,
    )
    usd = RtgsCalendar(
        currency="USD",
        calendar_name="USD",
        operator="x",
        entries_by_date={date(2026, 6, 16): usd_hol},
        **WINDOW,
    )
    cals = {"EUR": _empty_rtgs("EUR"), "USD": usd}
    result = derive_contract(
        venue="CME",
        pair=parse_pair("EUR/USD"),
        contract_month=(2026, 6),
        rtgs_calendars=cals,
        exchange_calendar=_empty_exchange("CME"),
    )
    assert result.expiry_date == date(2026, 6, 15)
    # Expiry 06-15: walk 2 good BDs on RTGS{EUR,USD}. 06-16 (USD bad), 06-17 (good)=1,
    # 06-18 (good)=2 -> delivery = 06-18.
    assert result.delivery_date == date(2026, 6, 18)
