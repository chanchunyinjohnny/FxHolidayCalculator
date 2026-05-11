from datetime import date

from scripts.sources.ecb_target2 import build_payload


def test_target2_2026_holidays():
    payload = build_payload(year_range=(2026, 2026))
    assert payload["currency"] == "EUR"
    assert payload["calendar_kind"] == "RTGS"
    src = payload["default_source"]
    assert src["url"].startswith("https://www.ecb.europa.eu")
    assert src["doc_title"]
    assert src["fetched_at"]
    dates = {h["date"]: h["name"] for h in payload["holidays"]}
    # Six fixed/movable holidays for TARGET2 in 2026:
    assert dates["2026-01-01"] == "New Year's Day"
    assert dates["2026-04-03"] == "Good Friday"  # 2026 Easter is Apr 5
    assert dates["2026-04-06"] == "Easter Monday"
    assert dates["2026-05-01"] == "Labour Day"
    assert dates["2026-12-25"] == "Christmas Day"
    assert dates["2026-12-26"] == "Christmas Holiday"
    assert len(dates) == 6


def test_target2_multi_year():
    payload = build_payload(year_range=(2026, 2027))
    years = {date.fromisoformat(h["date"]).year for h in payload["holidays"]}
    assert years == {2026, 2027}
    assert len(payload["holidays"]) == 12  # 6 per year
