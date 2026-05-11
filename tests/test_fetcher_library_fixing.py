from scripts.sources.library_fixing import _CURRENCIES, build_payload


def test_library_fixing_produces_all_three_currencies():
    for ccy in ("CNY", "KRW", "TWD"):
        assert ccy in _CURRENCIES


def test_library_fixing_payload_for_cny():
    payload = build_payload((2026, 2030), "CNY")
    assert payload["currency"] == "CNY"
    assert payload["calendar_kind"] == "FIXING"
    assert "library-sourced" in payload["calendar_name"]
    assert payload["default_source"]["fetcher"] == "scripts/sources/library_fixing.py@v1"
    # python-holidays.China should yield >=8 holidays per year for 5 years.
    assert len(payload["holidays"]) > 40


def test_library_fixing_dates_in_range_for_cny():
    payload = build_payload((2026, 2026), "CNY")
    for h in payload["holidays"]:
        assert h["date"].startswith("2026-")
        assert h["note"].startswith("python-holidays China")
