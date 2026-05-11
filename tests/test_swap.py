from datetime import date, datetime, timezone

import pytest

from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import HolidayEntry, SourceRef
from fx_holiday_calculator.conventions.cross import MissingExchangeCalendarError
from fx_holiday_calculator.pairs import parse_pair
from fx_holiday_calculator.swap import (
    InvalidBrokenDateError,
    InvalidFFSCombinationError,
    InvalidTradeDateError,
    calculate_swap_dates,
)
from fx_holiday_calculator.tenor import parse_tenor


def test_swap_does_not_reject_informational_dates():
    # If an informational date falls on a candidate spot date, the calc proceeds.
    src = SourceRef(
        url="https://x",
        doc_title="x",
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        fetcher="t",
    )
    info_entry = HolidayEntry(
        date=date(2026, 5, 7),
        name="Informational",
        note=None,
        source=src,
        source_origin="bundled",
        is_closure=False,
        liquidity="thin",
    )
    window = dict(valid_from=date(2020, 1, 1), valid_until=date(2030, 12, 31))
    eur = RtgsCalendar(
        currency="EUR", calendar_name="EUR", operator="x", entries_by_date={}, **window
    )
    usd = RtgsCalendar(
        currency="USD",
        calendar_name="USD",
        operator="x",
        entries_by_date={date(2026, 5, 7): info_entry},
        **window,
    )
    cals = {"EUR": eur, "USD": usd}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("SPOT"),
        ref_currency="none",
        calendars=cals,
    )
    # Spot proceeds normally; the +1 step should be accepted (not rejected).
    # The candidate date 2026-05-07 has liquidity but is_good=True.
    step = r.spot_trace[0]
    assert step.decision == "accepted"
    usd_status = step.statuses["USD"]
    assert usd_status.is_good is True
    assert usd_status.liquidity == "thin"


def _empty(c: str) -> RtgsCalendar:
    return RtgsCalendar(
        currency=c,
        calendar_name=c,
        operator="x",
        entries_by_date={},
        valid_from=date(2020, 1, 1),
        valid_until=date(2030, 12, 31),
    )


def _hol(c: str, days: list[date]) -> RtgsCalendar:
    src = SourceRef(
        url="https://x",
        doc_title="x",
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        fetcher="t",
    )
    return RtgsCalendar(
        currency=c,
        calendar_name=c,
        operator="x",
        entries_by_date={d: HolidayEntry(d, "x", None, src, "bundled") for d in days},
        valid_from=date(2020, 1, 1),
        valid_until=date(2030, 12, 31),
    )


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
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("ON"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.near_date == date(2026, 5, 6)
    assert r.far_date == date(2026, 5, 7)


def test_tn_tenor():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("TN"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.near_date == date(2026, 5, 7)
    assert r.far_date == date(2026, 5, 8)
    assert r.far_date == r.spot_date


def test_sn_tenor():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("SN"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.near_date == r.spot_date  # 5-8 Fri
    assert r.far_date == date(2026, 5, 11)  # next BD after Fri (Mon)


def test_period_3m_eurusd():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("3M"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 5, 8)
    assert r.near_date == date(2026, 5, 8)
    # raw far = 2026-08-08 (Sat) → mod-following → 2026-08-10 (Mon).
    assert r.far_date == date(2026, 8, 10)


def test_imm_tenor():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("IMM1"),
        ref_currency="none",
        calendars=cals,
    )
    # IMM1 from May 6 spot 5/8 → next IMM month = Jun 2026 → 3rd Wed = 2026-06-17
    assert r.far_date == date(2026, 6, 17)


def test_broken_date():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("2026-08-15"),
        ref_currency="none",
        calendars=cals,
    )
    # 2026-08-15 is Sat → mod-following → Mon 2026-08-17.
    assert r.far_date == date(2026, 8, 17)


def test_ffs_period_period():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        near_tenor=parse_tenor("1M"),
        far_tenor=parse_tenor("3M"),
        ref_currency="none",
        calendars=cals,
    )
    # spot = 2026-05-08; near = +1M → 2026-06-08; far = +3M → 2026-08-08 (Sat) → 08-10.
    assert r.spot_date == date(2026, 5, 8)
    assert r.near_date == date(2026, 6, 8)
    assert r.far_date == date(2026, 8, 10)


def test_ffs_rejects_on_in_far_tenor():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    with pytest.raises(InvalidFFSCombinationError):
        calculate_swap_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("EUR/USD"),
            near_tenor=parse_tenor("1M"),
            far_tenor=parse_tenor("ON"),
            ref_currency="none",
            calendars=cals,
        )


def test_ffs_rejects_far_le_near():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    with pytest.raises(InvalidFFSCombinationError):
        calculate_swap_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("EUR/USD"),
            near_tenor=parse_tenor("3M"),
            far_tenor=parse_tenor("1M"),
            ref_currency="none",
            calendars=cals,
        )


def test_ffs_rejects_broken_near_before_spot():
    # Trade 2026-05-06; spot = 2026-05-08. A BROKEN near of 2026-05-07
    # rolls to itself (Thu, good BD), which is before spot — invalid FFS.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    with pytest.raises(InvalidFFSCombinationError):
        calculate_swap_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("EUR/USD"),
            near_tenor=parse_tenor("2026-05-07"),
            far_tenor=parse_tenor("3M"),
            ref_currency="none",
            calendars=cals,
        )


def test_ffs_rejects_broken_near_equal_to_spot():
    # Trade 2026-05-06; spot = 2026-05-08. A BROKEN near equal to spot
    # is not strictly after spot — invalid FFS.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    with pytest.raises(InvalidFFSCombinationError):
        calculate_swap_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("EUR/USD"),
            near_tenor=parse_tenor("2026-05-08"),
            far_tenor=parse_tenor("3M"),
            ref_currency="none",
            calendars=cals,
        )


def test_far_trace_populated_for_period():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("3M"),
        ref_currency="none",
        calendars=cals,
    )
    # raw far = 2026-08-08 (Sat) → reject; +1 (Sun) reject; +2 (Mon) accepted
    assert len(r.far_trace) == 3
    assert r.far_trace[0].candidate_date == date(2026, 8, 8)
    assert r.far_trace[0].decision == "reject_weekend"
    assert r.far_trace[-1].candidate_date == date(2026, 8, 10)
    assert r.far_trace[-1].decision == "accepted"


def test_far_trace_single_step_when_no_adjustment():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 4),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("1M"),
        ref_currency="none",
        calendars=cals,
    )
    # Whichever, the trace should not be empty.
    assert len(r.far_trace) >= 1
    assert r.far_trace[-1].decision == "accepted"


def test_near_trace_populated_for_ffs():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        near_tenor=parse_tenor("1M"),
        far_tenor=parse_tenor("3M"),
        ref_currency="none",
        calendars=cals,
    )
    # Both legs are forwards → both should have trace
    assert len(r.near_trace) >= 1
    assert len(r.far_trace) >= 1
    assert r.near_trace[-1].decision == "accepted"
    assert r.far_trace[-1].decision == "accepted"


def _exch(venue: str, days: list[date]) -> ExchangeCalendar:
    src = SourceRef(
        url="https://e",
        doc_title="e",
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        fetcher="t",
    )
    entries = {d: HolidayEntry(d, "x", None, src, "bundled") for d in days}
    return ExchangeCalendar(
        venue=venue,
        products=("X",),
        entries_by_date=entries,
        valid_from=date(2020, 1, 1),
        valid_until=date(2030, 12, 31),
    )


def test_on_rejects_non_business_trade_date():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    # 2026-05-09 is Saturday
    with pytest.raises(InvalidTradeDateError):
        calculate_swap_dates(
            trade_date=date(2026, 5, 9),
            pair=parse_pair("EUR/USD"),
            far_tenor=parse_tenor("ON"),
            ref_currency="none",
            calendars=cals,
        )


def test_on_rejects_holiday_trade_date():
    # Trade date is a USD holiday → ON near=trade_date is invalid.
    cals = {"EUR": _empty("EUR"), "USD": _hol("USD", [date(2026, 7, 3)])}
    with pytest.raises(InvalidTradeDateError):
        calculate_swap_dates(
            trade_date=date(2026, 7, 3),
            pair=parse_pair("EUR/USD"),
            far_tenor=parse_tenor("ON"),
            ref_currency="none",
            calendars=cals,
        )


def test_broken_date_before_spot_raises():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    # Trade 2026-05-06; spot ~ 2026-05-08. Target 2026-05-01 is before spot.
    with pytest.raises(InvalidBrokenDateError):
        calculate_swap_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("EUR/USD"),
            far_tenor=parse_tenor("2026-05-01"),
            ref_currency="none",
            calendars=cals,
        )


def test_broken_date_equal_to_spot_raises():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    # Spot is 2026-05-08; targeting 2026-05-08 directly means no swap.
    with pytest.raises(InvalidBrokenDateError):
        calculate_swap_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("EUR/USD"),
            far_tenor=parse_tenor("2026-05-08"),
            ref_currency="none",
            calendars=cals,
        )


def test_exchange_mode_requires_exchange_calendars():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    with pytest.raises(MissingExchangeCalendarError):
        calculate_swap_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("EUR/USD"),
            far_tenor=parse_tenor("3M"),
            ref_currency="none",
            calendars=cals,
            exchange_calendars=None,
            calendar_mode="EXCHANGE",
        )


def test_both_mode_requires_exchange_calendars():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    with pytest.raises(MissingExchangeCalendarError):
        calculate_swap_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("EUR/USD"),
            far_tenor=parse_tenor("3M"),
            ref_currency="none",
            calendars=cals,
            exchange_calendars={},
            calendar_mode="BOTH",
        )


def test_exchange_mode_rolls_against_exchange_calendar():
    # Same raw far date; verify exchange holiday is what gets rejected (not RTGS).
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    # 2026-08-10 is Mon; make it an exchange holiday on CME.
    exch = {"CME": _exch("CME", [date(2026, 8, 10)])}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("3M"),
        ref_currency="none",
        calendars=cals,
        exchange_calendars=exch,
        calendar_mode="EXCHANGE",
    )
    # raw far = 2026-08-08 (Sat). mod-following with CME closed on 8-10 → 8-11.
    assert r.far_date == date(2026, 8, 11)
    assert r.calendar_mode == "EXCHANGE"


def test_both_mode_unions_rtgs_and_exchange():
    # If RTGS says good but exchange says holiday, BOTH must reject.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    exch = {"CME": _exch("CME", [date(2026, 8, 10)])}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("3M"),
        ref_currency="none",
        calendars=cals,
        exchange_calendars=exch,
        calendar_mode="BOTH",
    )
    assert r.far_date == date(2026, 8, 11)
    assert r.calendar_mode == "BOTH"


def test_spot_offset_always_uses_rtgs_even_in_exchange_mode():
    # RTGS is closed on 2026-05-07; spot for EUR/USD trade 2026-05-06 must roll to 5-8.
    cals = {"EUR": _hol("EUR", [date(2026, 5, 7)]), "USD": _empty("USD")}
    # Exchange calendar empty — should not affect spot computation.
    exch = {"CME": _exch("CME", [])}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("SPOT"),
        ref_currency="none",
        calendars=cals,
        exchange_calendars=exch,
        calendar_mode="EXCHANGE",
    )
    assert r.spot_date == date(2026, 5, 11)  # delayed by EUR holiday on 5-7


def test_near_trace_populated_for_tn():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("TN"),
        ref_currency="none",
        calendars=cals,
    )
    # T+1 = 2026-05-07 (Thu, no holidays) → 1 accepted step
    assert len(r.near_trace) == 1
    assert r.near_trace[0].candidate_date == date(2026, 5, 7)
    assert r.near_trace[0].decision == "accepted"


# --- OTC tenors (SPOT/ON/TN/SN) ignore exchange calendars ---


def test_on_ignores_exchange_holiday_in_exchange_mode():
    # ON is OTC-only; exchange holiday on T+1 must NOT delay the far date.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    # 2026-05-07 (Thu) is a CME holiday — would shift far to 5-8 if used.
    exch = {"CME": _exch("CME", [date(2026, 5, 7)])}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("ON"),
        ref_currency="none",
        calendars=cals,
        exchange_calendars=exch,
        calendar_mode="EXCHANGE",
    )
    # Far should still be 5-7 (RTGS-only roll).
    assert r.near_date == date(2026, 5, 6)
    assert r.far_date == date(2026, 5, 7)
    # Labels reflect only RTGS calendars, no CME.
    assert all("CME" not in lbl for lbl in r.calendars_used)


def test_tn_ignores_exchange_holiday_in_both_mode():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    # CME holiday on the TN near date — must be ignored for OTC TN.
    exch = {"CME": _exch("CME", [date(2026, 5, 7)])}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("TN"),
        ref_currency="none",
        calendars=cals,
        exchange_calendars=exch,
        calendar_mode="BOTH",
    )
    assert r.near_date == date(2026, 5, 7)
    assert r.far_date == date(2026, 5, 8)
    assert all("CME" not in lbl for lbl in r.calendars_used)


def test_sn_ignores_exchange_holiday_in_exchange_mode():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    # CME holiday on SN far (2026-05-11 Mon) — must be ignored for OTC SN.
    exch = {"CME": _exch("CME", [date(2026, 5, 11)])}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("SN"),
        ref_currency="none",
        calendars=cals,
        exchange_calendars=exch,
        calendar_mode="EXCHANGE",
    )
    assert r.near_date == date(2026, 5, 8)
    assert r.far_date == date(2026, 5, 11)
    assert all("CME" not in lbl for lbl in r.calendars_used)


def test_spot_tenor_in_exchange_mode_uses_only_rtgs_labels():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    exch = {"CME": _exch("CME", [])}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("SPOT"),
        ref_currency="none",
        calendars=cals,
        exchange_calendars=exch,
        calendar_mode="EXCHANGE",
    )
    # SPOT itself only ever rolls on RTGS; labels should not include CME.
    assert all("CME" not in lbl for lbl in r.calendars_used)


def test_on_in_exchange_mode_does_not_require_exchange_calendars():
    # If calendar_mode is EXCHANGE/BOTH but tenor is OTC, exchange_calendars
    # may be omitted entirely — no MissingExchangeCalendarError should fire.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("ON"),
        ref_currency="none",
        calendars=cals,
        exchange_calendars=None,
        calendar_mode="EXCHANGE",
    )
    assert r.near_date == date(2026, 5, 6)
    assert r.far_date == date(2026, 5, 7)


# --- TN warnings on non-business trade dates ---


def test_tn_on_weekend_trade_date_emits_warning_but_does_not_raise():
    # 2026-05-09 is Saturday. TN should not raise (unlike ON) but should warn.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 9),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("TN"),
        ref_currency="none",
        calendars=cals,
    )
    assert len(r.warnings) >= 1
    assert "TN trade date 2026-05-09" in r.warnings[0]
    # Computation still completes: near rolls forward to next good BD.
    assert r.near_date is not None
    assert r.far_date is not None


def test_tn_on_holiday_trade_date_emits_warning():
    # Trade date is a USD holiday. TN warns but still computes.
    cals = {"EUR": _empty("EUR"), "USD": _hol("USD", [date(2026, 7, 3)])}
    r = calculate_swap_dates(
        trade_date=date(2026, 7, 3),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("TN"),
        ref_currency="none",
        calendars=cals,
    )
    assert len(r.warnings) >= 1
    assert "not a good business day" in r.warnings[0]


def test_tn_on_good_trade_date_emits_no_warning():
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("TN"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.warnings == []
