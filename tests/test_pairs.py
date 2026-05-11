import pytest

from fx_holiday_calculator.pairs import (
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


def test_pair_dataclass_has_ndf_field_default_false():
    p = parse_pair("EUR/USD")
    assert p.ndf is False
    assert p.fixing_currency is None


def test_pair_dataclass_supports_ndf_fields():
    from fx_holiday_calculator.pairs import Pair
    p = Pair(
        base="USD",
        quote="CNY",
        spot_offset_days=2,
        listed_on=(),
        ndf=True,
        fixing_currency="CNY",
    )
    assert p.ndf is True
    assert p.fixing_currency == "CNY"


def test_usd_cny_is_ndf_pair():
    p = parse_pair("USD/CNY")
    assert p.ndf is True
    assert p.fixing_currency == "CNY"
    assert p.spot_offset_days == 2
    assert p.listed_on == ()


def test_usd_krw_is_ndf_pair():
    p = parse_pair("USD/KRW")
    assert p.ndf is True
    assert p.fixing_currency == "KRW"


def test_usd_twd_is_ndf_pair():
    p = parse_pair("USD/TWD")
    assert p.ndf is True
    assert p.fixing_currency == "TWD"


def test_krw_usd_remains_deliverable_sgx_listed():
    # Distinct from USD/KRW (the NDF) — KRW/USD is the SGX-listed deliverable contract.
    p = parse_pair("KRW/USD")
    assert p.ndf is False
    assert "SGX" in p.listed_on
