"""Tripwire: surface drift between bundled fixing calendars and python-holidays
public holidays for the corresponding country. Soft warnings only — fixing
calendars legitimately differ from public holidays (settlement vs. public
closure), so this never hard-fails CI.
"""
from datetime import date
from pathlib import Path

import pytest

from fx_holiday_calculator.calendars.loader import load_fixing_calendar

DATA_DIR = Path(__file__).parents[1] / "data"

_FIXING_TO_PYHOLIDAY = {
    "CNY": "CN",
    "KRW": "KR",
    "TWD": "TW",
}


def _fixing_dates(currency: str, year: int) -> set[date]:
    try:
        cal = load_fixing_calendar(currency, root=DATA_DIR / "fx_fixing")
    except FileNotFoundError:
        pytest.skip(f"No bundled fixing data for {currency}")
    return {d for d in cal.entries_by_date if d.year == year}


def _pyholiday_dates(country_code: str, year: int) -> set[date]:
    import holidays  # python-holidays
    cls = getattr(holidays, {"CN": "China", "KR": "SouthKorea", "TW": "Taiwan"}[country_code])
    return {d for d in cls(years=[year])}


@pytest.mark.parametrize("currency,country", list(_FIXING_TO_PYHOLIDAY.items()))
def test_fixing_calendar_overlaps_python_holidays(currency, country):
    """Verify that bundled fixing dates and python-holidays have meaningful overlap.
    A complete divergence usually indicates a parser bug or stale data.
    """
    year = 2026
    fixing = _fixing_dates(currency, year)
    pyhol = _pyholiday_dates(country, year)
    if not fixing:
        pytest.skip(f"No {currency} fixing entries for {year}")
    overlap = fixing & pyhol
    coverage = len(overlap) / max(len(pyhol), 1)
    # Expect >= 50% overlap; below that, raise a soft warning, but don't fail.
    if coverage < 0.5:
        import warnings
        warnings.warn(
            f"{currency} fixing calendar overlaps python-holidays {country} by only "
            f"{coverage:.0%} for {year}. Verify the bundled data is current and "
            f"the parser is intact."
        )
