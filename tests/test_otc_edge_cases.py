"""Edge-case coverage for OTC products: spot, cross-pair, swap, forward.

Focus areas:
  - weekend rolls and holiday cascades on the spot offset,
  - cross-pair behaviour with `ref=USD` vs `ref=none` (incl. the documented
    §2.1 single-pass limitation, pinned as a regression guard),
  - EOM rule triggered through the swap engine across month / year / Feb
    boundaries,
  - modified-following preceding fallback when forward roll crosses a
    month boundary,
  - IMM with the 3rd Wed itself blocked,
  - BROKEN-date targets landing on weekends / non-BDs,
  - FFS with EOM-firing legs, mixed-tenor legs, USD/CAD,
  - forward outright on cross pairs, with EOM, with holidays,
  - **USD/CAD** specifically — the T+1 pair exercises off-by-one logic,
    TN ≡ SN collapse, and asymmetric CAD-vs-USD holiday behaviour.

Each test pins the expected dates against hand-computed values; comments
walk through the day-by-day derivation so future readers can verify
without re-running the engine.
"""
from datetime import date, datetime, timezone

import pytest

from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import HolidayEntry, SourceRef
from fx_holiday_calculator.forward import calculate_forward_dates
from fx_holiday_calculator.pairs import parse_pair
from fx_holiday_calculator.swap import (
    InvalidBrokenDateError,
    InvalidFFSCombinationError,
    InvalidTradeDateError,
    calculate_swap_dates,
)
from fx_holiday_calculator.tenor import parse_tenor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WINDOW = dict(valid_from=date(2020, 1, 1), valid_until=date(2030, 12, 31))
_SRC = SourceRef(
    url="https://test",
    doc_title="test",
    fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    fetcher="test",
)


def _empty(currency: str) -> RtgsCalendar:
    return RtgsCalendar(
        currency=currency,
        calendar_name=currency,
        operator="test",
        entries_by_date={},
        **_WINDOW,
    )


def _hol(currency: str, days: list[date]) -> RtgsCalendar:
    entries = {d: HolidayEntry(d, "holiday", None, _SRC, "bundled") for d in days}
    return RtgsCalendar(
        currency=currency,
        calendar_name=currency,
        operator="test",
        entries_by_date=entries,
        **_WINDOW,
    )


# ===========================================================================
# Section 1: Spot offset edge cases
# ===========================================================================


def test_spot_eurusd_friday_trade_rolls_through_weekend():
    # Trade Fri 2026-05-08 EUR/USD (T+2):
    #   T+1 candidate Sat 5-9 reject; Sun 5-10 reject; Mon 5-11 good count=1
    #   T+2 candidate Tue 5-12 good count=2 -> spot Tue 5-12.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 8),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("SPOT"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 5, 12)


def test_spot_usdcad_friday_trade_rolls_through_weekend():
    # Trade Fri 2026-05-08 USD/CAD (T+1):
    #   T+1 candidate Sat 5-9 reject; Sun 5-10 reject; Mon 5-11 good count=1
    #   -> spot Mon 5-11.
    cals = {"USD": _empty("USD"), "CAD": _empty("CAD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 8),
        pair=parse_pair("USD/CAD"),
        far_tenor=parse_tenor("SPOT"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 5, 11)


def test_spot_usdcad_us_only_holiday_at_t_plus_1():
    # US Thanksgiving Thu 2026-11-26 closes USD but CAD stays open.
    # Trade Wed 2026-11-25 USD/CAD: T+1 = Thu 11-26 (USD closed) reject
    # -> Fri 11-27 (both good) count=1 -> spot Fri 11-27.
    cals = {"USD": _hol("USD", [date(2026, 11, 26)]), "CAD": _empty("CAD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 11, 25),
        pair=parse_pair("USD/CAD"),
        far_tenor=parse_tenor("SPOT"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 11, 27)


def test_spot_usdcad_cad_only_holiday_at_t_plus_1():
    # Canada Day Wed 2026-07-01 closes CAD but USD stays open.
    # Trade Tue 2026-06-30 USD/CAD: T+1 = Wed 7-1 (CAD closed) reject
    # -> Thu 7-2 (both good) count=1 -> spot Thu 7-2.
    cals = {"USD": _empty("USD"), "CAD": _hol("CAD", [date(2026, 7, 1)])}
    r = calculate_swap_dates(
        trade_date=date(2026, 6, 30),
        pair=parse_pair("USD/CAD"),
        far_tenor=parse_tenor("SPOT"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 7, 2)


def test_spot_eurusd_holiday_at_t_plus_2_pushes_spot():
    # US July 4 observed Fri 2026-07-03 falls on the natural spot date.
    # Trade Wed 2026-07-01 EUR/USD: T+1 Thu 7-2 good count=1
    # -> T+2 Fri 7-3 (USD closed) reject -> Sat 7-4 reject -> Sun 7-5 reject
    # -> Mon 7-6 good count=2 -> spot Mon 7-6.
    cals = {"EUR": _empty("EUR"), "USD": _hol("USD", [date(2026, 7, 3)])}
    r = calculate_swap_dates(
        trade_date=date(2026, 7, 1),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("SPOT"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 7, 6)


def test_spot_consecutive_holidays_christmas_boxing_day():
    # Realistic cascade: Christmas Thu 2025-12-25 + Boxing Day Fri 12-26 +
    # weekend. Trade Tue 2025-12-23 EUR/USD:
    #   T+1 = Wed 12-24 good count=1
    #   T+2 candidate Thu 12-25 (closed) -> Fri 12-26 (closed) -> Sat reject
    #   -> Sun reject -> Mon 12-29 good count=2 -> spot Mon 2025-12-29.
    closures = [date(2025, 12, 25), date(2025, 12, 26)]
    cals = {
        "EUR": _hol("EUR", closures),
        "USD": _hol("USD", closures),
    }
    r = calculate_swap_dates(
        trade_date=date(2025, 12, 23),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("SPOT"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2025, 12, 29)


def test_spot_year_end_crossing():
    # Trade Thu 2026-12-31 EUR/USD (year-end). No holidays specified.
    #   T+1 = Fri 2027-01-01 good count=1
    #   T+2 = Sat 2027-01-02 reject -> Sun reject -> Mon 2027-01-04 good=2
    # -> spot Mon 2027-01-04.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 12, 31),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("SPOT"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2027, 1, 4)


def test_spot_trace_records_every_skip():
    # The trace must contain one entry per candidate considered, not
    # only the accepted one — important for verifiability in the UI.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 8),  # Fri, T+2 EUR/USD spans weekend
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("SPOT"),
        ref_currency="none",
        calendars=cals,
    )
    # Sat 5-9, Sun 5-10, Mon 5-11, Tue 5-12 = 4 candidates.
    assert [s.candidate_date for s in r.spot_trace] == [
        date(2026, 5, 9),
        date(2026, 5, 10),
        date(2026, 5, 11),
        date(2026, 5, 12),
    ]
    assert [s.decision for s in r.spot_trace] == [
        "reject_weekend",
        "reject_weekend",
        "accepted",
        "accepted",
    ]


# ===========================================================================
# Section 2: Cross-pair ref currency behaviour
# ===========================================================================


def test_cross_eurjpy_ref_usd_pushes_spot_when_us_holiday_lands_on_spot():
    # Trade Wed 2026-07-01 EUR/JPY, ref=USD. US July 4 observed Fri 7-3
    # would naturally be the spot day; ref=USD pushes it forward.
    cals = {
        "EUR": _empty("EUR"),
        "JPY": _empty("JPY"),
        "USD": _hol("USD", [date(2026, 7, 3)]),
    }
    r = calculate_swap_dates(
        trade_date=date(2026, 7, 1),
        pair=parse_pair("EUR/JPY"),
        far_tenor=parse_tenor("SPOT"),
        ref_currency="USD",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 7, 6)


def test_cross_eurjpy_ref_none_ignores_usd_holiday():
    # Same setup as above but ref=none -> USD calendar is not consulted.
    # Spot should land on Fri 7-3 itself, since EUR + JPY are open.
    cals = {
        "EUR": _empty("EUR"),
        "JPY": _empty("JPY"),
    }
    r = calculate_swap_dates(
        trade_date=date(2026, 7, 1),
        pair=parse_pair("EUR/JPY"),
        far_tenor=parse_tenor("SPOT"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 7, 3)


def test_cross_eurjpy_documented_intermediate_hop_limitation():
    # Regression guard for the §2.1 known limitation: when a US-only
    # holiday falls on the INTERMEDIATE T+1 hop (not on spot), the
    # textbook market algorithm would still return T+2 = Wed; the
    # engine's single-pass algorithm returns T+3 = Thu instead.
    #
    # Trade Mon 2026-05-04 EUR/JPY, ref=USD. Synthetic US holiday Tue 5-5.
    #   Engine path: T+1 Tue 5-5 (USD closed) reject -> Wed 5-6 good=1
    #               -> Thu 5-7 good=2. Spot = Thu 5-7.
    #   Convention path (NOT implemented): count on EUR+JPY only -> spot
    #                  candidate Wed 5-6; check vs USD; Wed is USD-good ->
    #                  spot = Wed 5-6.
    cals = {
        "EUR": _empty("EUR"),
        "JPY": _empty("JPY"),
        "USD": _hol("USD", [date(2026, 5, 5)]),
    }
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 4),
        pair=parse_pair("EUR/JPY"),
        far_tenor=parse_tenor("SPOT"),
        ref_currency="USD",
        calendars=cals,
    )
    # Pin engine behavior. If/when the two-pass algorithm is implemented,
    # update this test together with docs §2.1.
    assert r.spot_date == date(2026, 5, 7)


def test_cross_eurjpy_jpy_holiday_at_t_plus_1():
    # JPY-only holiday should always push spot regardless of ref.
    # Trade Mon 2026-05-04 EUR/JPY, JPY closed Tue 5-5 (Children's Day).
    #   T+1 Tue 5-5 (JPY closed) reject -> Wed 5-6 good=1
    #   T+2 Thu 5-7 good=2 -> spot Thu 5-7.
    cals = {
        "EUR": _empty("EUR"),
        "JPY": _hol("JPY", [date(2026, 5, 5)]),
        "USD": _empty("USD"),
    }
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 4),
        pair=parse_pair("EUR/JPY"),
        far_tenor=parse_tenor("SPOT"),
        ref_currency="USD",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 5, 7)


# ===========================================================================
# Section 3: ON / TN / SN with holidays at the rolled legs
# ===========================================================================


def test_on_eurusd_far_rolls_through_weekend():
    # Trade Fri 2026-05-08 EUR/USD ON: near=Fri, far=Sat reject -> Sun
    # reject -> Mon 5-11. (ON itself doesn't block on Friday — Friday is
    # a good business day.)
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 8),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("ON"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.near_date == date(2026, 5, 8)
    assert r.far_date == date(2026, 5, 11)


def test_on_usdcad_far_holiday_pushes_far():
    # USD/CAD ON: near=T, far=T+1. With CAD-only holiday at T+1, far rolls.
    # Trade Tue 2026-06-30 USD/CAD. Canada Day = Wed 7-1.
    #   near = Tue 6-30, far candidate Wed 7-1 (CAD closed) reject ->
    #   Thu 7-2 good -> far = Thu 7-2.
    cals = {"USD": _empty("USD"), "CAD": _hol("CAD", [date(2026, 7, 1)])}
    r = calculate_swap_dates(
        trade_date=date(2026, 6, 30),
        pair=parse_pair("USD/CAD"),
        far_tenor=parse_tenor("ON"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.near_date == date(2026, 6, 30)
    assert r.far_date == date(2026, 7, 2)


def test_tn_usdcad_near_rolls_through_holiday_collapses_with_sn():
    # USD/CAD trade Tue 6-30. Canada Day on Wed 7-1 closes CAD.
    # TN near = T+1 candidate Wed 7-1 (CAD closed) reject -> Thu 7-2 good.
    # TN far = near+1 = Fri 7-3 good.
    # SN near = spot = Thu 7-2 (since spot also lands on Thu after rolling
    # through Canada Day). SN far = spot+1 = Fri 7-3.
    cals = {"USD": _empty("USD"), "CAD": _hol("CAD", [date(2026, 7, 1)])}
    tn = calculate_swap_dates(
        trade_date=date(2026, 6, 30),
        pair=parse_pair("USD/CAD"),
        far_tenor=parse_tenor("TN"),
        ref_currency="none",
        calendars=cals,
    )
    sn = calculate_swap_dates(
        trade_date=date(2026, 6, 30),
        pair=parse_pair("USD/CAD"),
        far_tenor=parse_tenor("SN"),
        ref_currency="none",
        calendars=cals,
    )
    assert tn.near_date == sn.near_date == date(2026, 7, 2)
    assert tn.far_date == sn.far_date == date(2026, 7, 3)


def test_sn_far_rolls_through_holiday():
    # EUR/USD trade Wed 2026-05-06 -> spot Fri 5-8. SN far = spot+1.
    # Make Mon 5-11 a USD holiday. SN far candidate Sat reject -> Sun reject
    # -> Mon 5-11 (USD closed) reject -> Tue 5-12 good -> far = Tue 5-12.
    cals = {"EUR": _empty("EUR"), "USD": _hol("USD", [date(2026, 5, 11)])}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("SN"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.near_date == date(2026, 5, 8)
    assert r.far_date == date(2026, 5, 12)


def test_on_blocked_on_holiday_trade_for_usdcad():
    # ON requires trade_date itself to be a good BD on both currencies.
    # Trade Wed 2026-07-01 (Canada Day, CAD closed) USD/CAD ON -> raise.
    cals = {"USD": _empty("USD"), "CAD": _hol("CAD", [date(2026, 7, 1)])}
    with pytest.raises(InvalidTradeDateError):
        calculate_swap_dates(
            trade_date=date(2026, 7, 1),
            pair=parse_pair("USD/CAD"),
            far_tenor=parse_tenor("ON"),
            ref_currency="none",
            calendars=cals,
        )


def test_tn_warns_but_proceeds_on_usdcad_cad_holiday_trade():
    # Trade Wed 2026-07-01 (Canada Day for CAD) USD/CAD TN: warns but
    # still computes. Near rolls forward: Wed 7-1 trade -> near candidate
    # Thu 7-2 good -> far Fri 7-3 good.
    cals = {"USD": _empty("USD"), "CAD": _hol("CAD", [date(2026, 7, 1)])}
    r = calculate_swap_dates(
        trade_date=date(2026, 7, 1),
        pair=parse_pair("USD/CAD"),
        far_tenor=parse_tenor("TN"),
        ref_currency="none",
        calendars=cals,
    )
    assert len(r.warnings) >= 1
    assert "TN trade date 2026-07-01" in r.warnings[0]
    assert r.near_date == date(2026, 7, 2)
    assert r.far_date == date(2026, 7, 3)


# ===========================================================================
# Section 4: EOM rule via the swap engine
# ===========================================================================


def test_eom_fires_when_spot_is_last_bd_of_may():
    # Trade Wed 2026-05-27 EUR/USD: T+1 Thu 5-28, T+2 Fri 5-29 = spot.
    # May 30 = Sat, May 31 = Sun, so Fri 5-29 is last BD of May.
    # +1M -> raw Mon 6-29 (good). EOM fires -> last BD of Jun.
    # Jun 30 2026 = Tue (good) -> far = Tue 6-30.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 27),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("1M"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 5, 29)
    assert r.far_date == date(2026, 6, 30)


def test_eom_fires_for_february_short_month():
    # Trade Wed 2026-02-25 EUR/USD: T+1 Thu 2-26, T+2 Fri 2-27 = spot.
    # Feb 28 2026 = Sat, so Fri 2-27 is last BD of Feb. +1M: relativedelta
    # gives Fri 3-27 raw (good). EOM fires -> last BD of Mar = Tue 3-31
    # (since Mar 31 2026 = Tue). far = Tue 2026-03-31.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 2, 25),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("1M"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 2, 27)
    assert r.far_date == date(2026, 3, 31)


def test_eom_fires_across_year_boundary_with_1y_tenor():
    # Trade Tue 2026-04-28 EUR/USD: T+1 Wed 4-29, T+2 Thu 4-30 = spot.
    # Apr 30 2026 = last BD of Apr (May 1 2026 = Fri is technically a BD
    # but we test against THIS month's last BD; spot is Apr-30 which is
    # last day of Apr). +1Y raw = Fri 2027-04-30 (good, last day Apr 2027).
    # EOM fires -> last BD Apr 2027 = Fri 2027-04-30 (same date). far = it.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 4, 28),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("1Y"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 4, 30)
    assert r.far_date == date(2027, 4, 30)


def test_eom_does_not_fire_when_spot_not_last_bd():
    # Same trade Wed 2026-04-29 -> spot Mon 5-4 (since T+2 of Wed = Fri 5-1
    # which is good, wait Fri May 1 2026 is a Fri good BD with no holidays).
    # Actually: Wed 4-29 -> T+1 Thu 4-30 -> T+2 Fri 5-1. Fri 5-1 is good.
    # spot = Fri 5-1. Not last BD of its month. +1M raw = Mon 6-1 good.
    # No EOM fire, no roll needed. far = Mon 6-1.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 4, 29),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("1M"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 5, 1)
    assert r.far_date == date(2026, 6, 1)


def test_eom_fires_for_usdcad_t_plus_1():
    # USD/CAD trade Thu 2026-01-29: T+1 = Fri 1-30 good = spot.
    # Jan 30 2026 = last BD of Jan (Jan 31 = Sat). +1M -> raw = Feb 30
    # which relativedelta normalises to Feb 28 = Sat. EOM fires (spot is
    # last BD of Jan) -> last BD of Feb = Fri 2-27 -> far = Fri 2-27.
    cals = {"USD": _empty("USD"), "CAD": _empty("CAD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 1, 29),
        pair=parse_pair("USD/CAD"),
        far_tenor=parse_tenor("1M"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 1, 30)
    assert r.far_date == date(2026, 2, 27)


# ===========================================================================
# Section 5: Modified-following preceding fallback (month-cross)
# ===========================================================================


def test_mod_following_falls_back_to_preceding_on_month_cross():
    # Spot = Wed 2026-04-29 (NOT last BD of Apr, since Thu 4-30 is a good
    # BD). +1M raw = Fri 2026-05-29. Force a holiday on Fri 5-29 in USD.
    # Mod-following: Fri 5-29 reject_holiday -> Sat 5-30 reject_weekend ->
    # Sun 5-31 reject_weekend -> Mon 6-1 good -> crosses month -> switch
    # to preceding direction: Thu 5-28 good -> accepted. far = Thu 5-28.
    cals = {
        "EUR": _empty("EUR"),
        "USD": _hol("USD", [date(2026, 5, 29)]),
    }
    r = calculate_swap_dates(
        trade_date=date(2026, 4, 27),  # Mon
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("1M"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 4, 29)
    assert r.far_date == date(2026, 5, 28)
    # Trace must include a `rolled_eom` marker (used by the helper to flag
    # the direction-switch event, even though the EOM *rule* didn't fire).
    assert any(s.decision == "rolled_eom" for s in r.far_trace)


def test_mod_following_no_month_cross_keeps_forward_direction():
    # Same setup but holiday is on Tue 5-26 (not month-end). Raw 5-29 good
    # already. No roll needed; far = Fri 5-29.
    cals = {
        "EUR": _empty("EUR"),
        "USD": _hol("USD", [date(2026, 5, 26)]),
    }
    r = calculate_swap_dates(
        trade_date=date(2026, 4, 27),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("1M"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 4, 29)
    assert r.far_date == date(2026, 5, 29)


# ===========================================================================
# Section 6: IMM with 3rd Wed holidays
# ===========================================================================


def test_imm_3rd_wed_holiday_rolls_mod_following():
    # Trade Wed 2026-05-06 EUR/USD -> spot Fri 5-8. IMM1 = 3rd Wed Jun =
    # Wed 6-17. Make Wed 6-17 an EUR holiday. Mod-following: Wed reject ->
    # Thu 6-18 good (no month cross) -> far = Thu 6-18.
    cals = {
        "EUR": _hol("EUR", [date(2026, 6, 17)]),
        "USD": _empty("USD"),
    }
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("IMM1"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.far_date == date(2026, 6, 18)


def test_imm_when_trade_is_exactly_on_an_imm_date():
    # Trade Wed 2026-06-17 (itself a 3rd Wed). IMM1 must be the NEXT IMM,
    # not this June; so IMM1 = Wed 2026-09-16.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 6, 17),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("IMM1"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.far_date == date(2026, 9, 16)


def test_imm_index_2_picks_second_quarter_ahead():
    # Trade Wed 2026-05-06 -> spot Fri 5-8 -> IMM2 picks the second IMM
    # after spot. Jun-17 is IMM1, Sep-16 is IMM2.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("IMM2"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.far_date == date(2026, 9, 16)


# ===========================================================================
# Section 7: BROKEN edge cases
# ===========================================================================


def test_broken_target_on_saturday_rolls_to_monday_same_month():
    # Spot Fri 5-8. Target Sat 5-30 -> Sun 5-31 reject -> Mon 6-1 good
    # -> crosses month -> preceding: Fri 5-29 good -> far Fri 5-29.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("2026-05-30"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.far_date == date(2026, 5, 29)


def test_broken_target_on_monday_holiday_rolls_forward():
    # Target Mon 2026-08-03 (synthetic CAD Civic Holiday). Spot is much
    # earlier so no risk of "≤ spot". USD/CAD trade Wed 5-6 -> spot Thu 5-7.
    # Target Mon 8-3 (CAD closed) -> Tue 8-4 good -> far = Tue 8-4.
    # No month-cross from Aug 3 to Aug 4, so plain mod-following forward.
    cals = {"USD": _empty("USD"), "CAD": _hol("CAD", [date(2026, 8, 3)])}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("USD/CAD"),
        far_tenor=parse_tenor("2026-08-03"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.far_date == date(2026, 8, 4)


def test_broken_target_one_day_after_spot_is_valid():
    # Spot Fri 2026-05-08. Target Mon 2026-05-11 (good BD). Far must equal
    # exactly the target. This is the minimal valid post-spot broken date.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("2026-05-11"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.far_date == date(2026, 5, 11)


# ===========================================================================
# Section 8: FFS edge cases
# ===========================================================================


def test_ffs_usdcad_clean_1m_vs_3m():
    # USD/CAD trade Wed 5-6 -> spot Thu 5-7. Near = spot+1M raw Sun 6-7
    # -> mod-following Mon 6-8 good. Far = spot+3M raw Mon 8-7? wait
    # relativedelta from May 7 plus 3M = Aug 7 = Fri (good). far = Fri 8-7.
    cals = {"USD": _empty("USD"), "CAD": _empty("CAD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("USD/CAD"),
        near_tenor=parse_tenor("1M"),
        far_tenor=parse_tenor("3M"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 5, 7)
    assert r.near_date == date(2026, 6, 8)
    assert r.far_date == date(2026, 8, 7)


def test_ffs_both_legs_trigger_eom():
    # USD/CAD trade Thu 1-29 -> spot Fri 1-30 = last BD of Jan -> EOM fires
    # on BOTH legs of the FFS (Strata convention anchors both on spot).
    #   Near = spot+1M raw normalised to Sat 2-28 -> EOM: last BD Feb =
    #          Fri 2-27.
    #   Far  = spot+3M raw = Thu 4-30 (last day of Apr; good BD).
    #          EOM: last BD Apr 2026 = Thu 4-30.
    cals = {"USD": _empty("USD"), "CAD": _empty("CAD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 1, 29),
        pair=parse_pair("USD/CAD"),
        near_tenor=parse_tenor("1M"),
        far_tenor=parse_tenor("3M"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 1, 30)
    assert r.near_date == date(2026, 2, 27)
    assert r.far_date == date(2026, 4, 30)


def test_ffs_mixed_period_vs_imm():
    # EUR/USD trade Wed 5-6 -> spot Fri 5-8.
    # Near = 1M -> raw Mon 6-8 good. Far = IMM1 = Wed 6-17 good.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        near_tenor=parse_tenor("1M"),
        far_tenor=parse_tenor("IMM1"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.near_date == date(2026, 6, 8)
    assert r.far_date == date(2026, 6, 17)


def test_ffs_mixed_period_vs_broken():
    # EUR/USD trade Wed 5-6 -> spot Fri 5-8.
    # Near = 1M = Mon 6-8. Far = broken Thu 2026-08-20 (good).
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        near_tenor=parse_tenor("1M"),
        far_tenor=parse_tenor("2026-08-20"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.near_date == date(2026, 6, 8)
    assert r.far_date == date(2026, 8, 20)


def test_ffs_rejects_broken_near_after_broken_far():
    # Both broken; near = Aug 14, far = Aug 10 -> far ≤ near -> raise.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    with pytest.raises(InvalidFFSCombinationError):
        calculate_swap_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("EUR/USD"),
            near_tenor=parse_tenor("2026-08-14"),
            far_tenor=parse_tenor("2026-08-10"),
            ref_currency="none",
            calendars=cals,
        )


# ===========================================================================
# Section 9: Forward outright edge cases
# ===========================================================================


def test_forward_usdcad_3m_clean():
    # USD/CAD trade Wed 5-6 -> spot Thu 5-7 -> +3M = Fri 8-7 good.
    cals = {"USD": _empty("USD"), "CAD": _empty("CAD")}
    r = calculate_forward_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("USD/CAD"),
        tenor=parse_tenor("3M"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 5, 7)
    assert r.settlement_date == date(2026, 8, 7)


def test_forward_usdcad_eom_one_month():
    # USD/CAD trade Thu 1-29 -> spot Fri 1-30 = last BD Jan. EOM 1M -> Fri 2-27.
    cals = {"USD": _empty("USD"), "CAD": _empty("CAD")}
    r = calculate_forward_dates(
        trade_date=date(2026, 1, 29),
        pair=parse_pair("USD/CAD"),
        tenor=parse_tenor("1M"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 1, 30)
    assert r.settlement_date == date(2026, 2, 27)


def test_forward_usdcad_imm():
    # USD/CAD trade Wed 5-6 -> spot Thu 5-7. IMM1 = 3rd Wed Jun = Wed 6-17.
    cals = {"USD": _empty("USD"), "CAD": _empty("CAD")}
    r = calculate_forward_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("USD/CAD"),
        tenor=parse_tenor("IMM1"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.settlement_date == date(2026, 6, 17)


def test_forward_eurjpy_with_usd_ref():
    # Cross pair forward with ref=USD. Trade Wed 5-6 EUR/JPY ref=USD.
    # All clean: spot Fri 5-8, +3M raw Sat 8-8 -> mod-following Mon 8-10.
    cals = {"EUR": _empty("EUR"), "JPY": _empty("JPY"), "USD": _empty("USD")}
    r = calculate_forward_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/JPY"),
        tenor=parse_tenor("3M"),
        ref_currency="USD",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 5, 8)
    assert r.settlement_date == date(2026, 8, 10)


def test_forward_rejects_broken_at_or_before_spot():
    # Forward outright must reject when rolled target ≤ spot.
    cals = {"EUR": _empty("EUR"), "USD": _empty("USD")}
    with pytest.raises(InvalidBrokenDateError):
        calculate_forward_dates(
            trade_date=date(2026, 5, 6),
            pair=parse_pair("EUR/USD"),
            tenor=parse_tenor("2026-05-08"),  # = spot
            ref_currency="none",
            calendars=cals,
        )


# ===========================================================================
# Section 10: USD/CAD comprehensive
# ===========================================================================


def test_usdcad_tn_warns_on_weekend_trade():
    # USD/CAD trade Sat 5-9 (not a BD). TN must warn and proceed.
    # Near = T+1 = Sun 5-10 reject -> Mon 5-11 good. Far = near+1 =
    # Tue 5-12 good.
    cals = {"USD": _empty("USD"), "CAD": _empty("CAD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 9),
        pair=parse_pair("USD/CAD"),
        far_tenor=parse_tenor("TN"),
        ref_currency="none",
        calendars=cals,
    )
    assert any("TN trade date 2026-05-09" in w for w in r.warnings)
    assert r.near_date == date(2026, 5, 11)
    assert r.far_date == date(2026, 5, 12)


def test_usdcad_friday_trade_all_short_tenors():
    # Trade Fri 2026-05-08 USD/CAD.
    # spot: T+1 candidate Sat reject -> Sun reject -> Mon 5-11 = spot.
    # ON:   near=Fri, far = T+1 = Sat reject -> Sun reject -> Mon 5-11.
    # TN:   near=T+1 = Mon 5-11, far=near+1 = Tue 5-12.
    # SN:   near=spot=Mon 5-11, far=spot+1 = Tue 5-12.
    cals = {"USD": _empty("USD"), "CAD": _empty("CAD")}
    on = calculate_swap_dates(
        trade_date=date(2026, 5, 8),
        pair=parse_pair("USD/CAD"),
        far_tenor=parse_tenor("ON"),
        ref_currency="none",
        calendars=cals,
    )
    tn = calculate_swap_dates(
        trade_date=date(2026, 5, 8),
        pair=parse_pair("USD/CAD"),
        far_tenor=parse_tenor("TN"),
        ref_currency="none",
        calendars=cals,
    )
    sn = calculate_swap_dates(
        trade_date=date(2026, 5, 8),
        pair=parse_pair("USD/CAD"),
        far_tenor=parse_tenor("SN"),
        ref_currency="none",
        calendars=cals,
    )
    assert on.near_date == date(2026, 5, 8) and on.far_date == date(2026, 5, 11)
    assert tn.near_date == date(2026, 5, 11) and tn.far_date == date(2026, 5, 12)
    assert sn.near_date == date(2026, 5, 11) and sn.far_date == date(2026, 5, 12)
    # TN and SN must agree on T+1 pair Friday-spanning trades.
    assert tn.near_date == sn.near_date
    assert tn.far_date == sn.far_date


def test_usdcad_thursday_trade_us_holiday_friday():
    # Trade Thu 2026-07-02 USD/CAD. US July 4 obs Fri 7-3.
    # Spot: T+1 = Fri 7-3 (USD closed) reject -> Sat reject -> Sun reject
    #       -> Mon 7-6 = spot.
    cals = {"USD": _hol("USD", [date(2026, 7, 3)]), "CAD": _empty("CAD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 7, 2),
        pair=parse_pair("USD/CAD"),
        far_tenor=parse_tenor("SPOT"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 7, 6)


def test_usdcad_3m_with_cad_only_holiday_at_settlement():
    # Trade Wed 5-6 USD/CAD -> spot Thu 5-7. +3M raw Fri 8-7 (good).
    # Make Fri 8-7 a CAD-only holiday (e.g., synthetic). Mod-following:
    # Fri reject -> Sat reject -> Sun reject -> Mon 8-10 good -> far 8-10.
    cals = {
        "USD": _empty("USD"),
        "CAD": _hol("CAD", [date(2026, 8, 7)]),
    }
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("USD/CAD"),
        far_tenor=parse_tenor("3M"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 5, 7)
    assert r.far_date == date(2026, 8, 10)


def test_usdcad_spot_is_unaffected_by_jpy_holiday_when_ref_none():
    # Sanity: USD/CAD with ref=none must NOT consult any third calendar
    # even if one is provided. Pass a JPY calendar with a holiday at T+1
    # that would push spot if consulted; spot must NOT move.
    cals = {
        "USD": _empty("USD"),
        "CAD": _empty("CAD"),
        # JPY calendar present but unused for USD/CAD with ref=none.
        "JPY": _hol("JPY", [date(2026, 5, 7)]),
    }
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("USD/CAD"),
        far_tenor=parse_tenor("SPOT"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 5, 7)


def test_usdcad_forward_far_anchored_on_spot_not_trade():
    # Confirm that PERIOD tenor is anchored on spot, not on trade date —
    # the engine uses `spot + N` for the raw far date.
    #   Trade Wed 5-6 USD/CAD -> spot Thu 5-7. +1M raw = Sun 6-7 -> mod-
    #   following Mon 6-8.
    # If anchored on trade date instead, +1M from 5-6 would be Sat 6-6 ->
    # mod-following Mon 6-8 — same answer here. Use a longer tenor where
    # the difference manifests: spot = Thu 5-7, +6M raw = Mon 11-9 (good).
    # vs trade-anchored: 5-6 +6M = Fri 11-6 (good). Different dates.
    cals = {"USD": _empty("USD"), "CAD": _empty("CAD")}
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("USD/CAD"),
        far_tenor=parse_tenor("6M"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 5, 7)
    assert r.far_date == date(2026, 11, 9)  # spot-anchored, not trade-anchored


def test_usdcad_ffs_with_usd_holiday_at_near_leg():
    # USD/CAD FFS 1M vs 3M with a USD-only holiday on the raw near date.
    # Trade Wed 5-6 -> spot Thu 5-7. Near raw = +1M = Sun 6-7 -> mod-
    # following Mon 6-8. Make Mon 6-8 a USD holiday -> further roll to
    # Tue 6-9 (good).
    cals = {
        "USD": _hol("USD", [date(2026, 6, 8)]),
        "CAD": _empty("CAD"),
    }
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("USD/CAD"),
        near_tenor=parse_tenor("1M"),
        far_tenor=parse_tenor("3M"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date == date(2026, 5, 7)
    assert r.near_date == date(2026, 6, 9)
    # Far is +3M raw = Fri 8-7, no holiday -> Fri 8-7.
    assert r.far_date == date(2026, 8, 7)
