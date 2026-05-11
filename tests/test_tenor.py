from datetime import date as _date

import pytest

from fx_holiday_calculator.tenor import InvalidTenorError, Tenor, parse_tenor


@pytest.mark.parametrize(
    "raw, expected_kind",
    [
        ("ON", "ON"),
        ("on", "ON"),
        (" TN ", "TN"),
        ("sn", "SN"),
        ("SPOT", "SPOT"),
        ("Spot", "SPOT"),
    ],
)
def test_parses_named_tenors(raw: str, expected_kind: str):
    t = parse_tenor(raw)
    assert isinstance(t, Tenor)
    assert t.kind == expected_kind
    assert t.period_unit is None
    assert t.period_n is None
    assert t.imm_index is None
    assert t.target_date is None


def test_rejects_garbage_input():
    with pytest.raises(InvalidTenorError):
        parse_tenor("not a tenor")


@pytest.mark.parametrize(
    "raw, unit, n",
    [
        ("1W", "W", 1),
        ("3W", "W", 3),
        ("1M", "M", 1),
        ("12M", "M", 12),
        ("1Y", "Y", 1),
        ("2Y", "Y", 2),
        ("5D", "D", 5),
        ("45D", "D", 45),
        (" 6m ", "M", 6),
    ],
)
def test_parses_period_tenors(raw: str, unit: str, n: int):
    t = parse_tenor(raw)
    assert t.kind == "PERIOD"
    assert t.period_unit == unit
    assert t.period_n == n


@pytest.mark.parametrize("bad", ["0M", "-1M", "1Q", "M1", "1.5Y", "100Y"])
def test_rejects_bad_period(bad: str):
    with pytest.raises(InvalidTenorError):
        parse_tenor(bad)


@pytest.mark.parametrize("raw, idx", [("IMM1", 1), ("imm2", 2), ("IMM3", 3), ("Imm4", 4)])
def test_parses_imm(raw: str, idx: int):
    t = parse_tenor(raw)
    assert t.kind == "IMM"
    assert t.imm_index == idx


@pytest.mark.parametrize("bad", ["IMM0", "IMM5", "IMM", "IMMA"])
def test_rejects_bad_imm(bad: str):
    with pytest.raises(InvalidTenorError):
        parse_tenor(bad)


def test_parses_broken_date():
    t = parse_tenor("2026-08-15")
    assert t.kind == "BROKEN"
    assert t.target_date == _date(2026, 8, 15)


@pytest.mark.parametrize("bad", ["2026-13-01", "2026-02-30", "26-08-15", "2026/08/15"])
def test_rejects_bad_broken_date(bad: str):
    with pytest.raises(InvalidTenorError):
        parse_tenor(bad)
