import pytest

from fx_holiday_calculator.pairs import (
    Pair,
    PairNotFoundError,
    list_supported_pairs,
    parse_pair,
)


def test_parse_eurusd():
    p = parse_pair("EUR/USD")
    assert p.base == "EUR"
    assert p.quote == "USD"
    assert p.spot_offset_days == 2


def test_parse_usdcad_is_t_plus_1():
    p = parse_pair("USD/CAD")
    assert p.spot_offset_days == 1


def test_parse_accepts_no_separator():
    p = parse_pair("USDJPY")
    assert p.base == "USD"
    assert p.quote == "JPY"


def test_parse_case_insensitive():
    p = parse_pair("eur/jpy")
    assert (p.base, p.quote) == ("EUR", "JPY")


def test_unknown_pair_raises():
    with pytest.raises(PairNotFoundError):
        parse_pair("USD/ZZZ")


def test_usdcnh_is_listed_on_three_venues():
    p = parse_pair("USD/CNH")
    assert set(p.listed_on) >= {"CME", "HKEX", "SGX"}


def test_supported_pairs_includes_majors():
    pairs = list_supported_pairs()
    codes = {f"{p.base}/{p.quote}" for p in pairs}
    assert "EUR/USD" in codes
    assert "USD/JPY" in codes
    assert "EUR/JPY" in codes
    assert "USD/CNH" in codes
    assert "HKD/CNH" in codes
