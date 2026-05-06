"""End-to-end smoke test against bundled data.

Skips if data files are not yet generated.
"""
from datetime import date
from pathlib import Path

import pytest

from fx_holiday_calculator.calendars.loader import load_rtgs_calendar
from fx_holiday_calculator.pairs import parse_pair
from fx_holiday_calculator.swap import calculate_swap_dates
from fx_holiday_calculator.tenor import parse_tenor

DATA = Path(__file__).parents[1] / "data" / "fx_rtgs"


def _have(*ccy: str) -> bool:
    return all((DATA / f"{c}.json").exists() for c in ccy)


@pytest.mark.skipif(not _have("EUR", "USD"), reason="EUR.json or USD.json not generated")
def test_eurusd_3m_with_real_data():
    cals = {
        "EUR": load_rtgs_calendar("EUR", root=DATA),
        "USD": load_rtgs_calendar("USD", root=DATA),
    }
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("EUR/USD"),
        far_tenor=parse_tenor("3M"),
        ref_currency="none",
        calendars=cals,
    )
    assert r.spot_date.weekday() < 5
    assert r.far_date is not None
    assert r.far_date.weekday() < 5


@pytest.mark.skipif(not _have("USD", "JPY"), reason="USD.json or JPY.json not generated")
def test_usdjpy_imm1_with_real_data():
    cals = {
        "USD": load_rtgs_calendar("USD", root=DATA),
        "JPY": load_rtgs_calendar("JPY", root=DATA),
    }
    r = calculate_swap_dates(
        trade_date=date(2026, 5, 6),
        pair=parse_pair("USD/JPY"),
        far_tenor=parse_tenor("IMM1"),
        ref_currency="none",
        calendars=cals,
    )
    # 2026-05-06 spot is 5/8; next IMM month from spot = Jun → 3rd Wed = Jun 17 (then mod-following).
    assert r.far_date is not None
    assert r.far_date.weekday() < 5
