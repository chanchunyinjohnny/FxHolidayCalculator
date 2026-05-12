"""CNH composite fetcher tests.

The CNH calendar is the union of the HK general-holidays page (Cap. 149)
and the CFETS PRC FX-market closure list. These tests reuse the existing
fixtures from the HK and CFETS fetcher test suites — the CNH fetcher is
glue code over those two parsers, so there's no separate raw artifact to
record.
"""

from datetime import datetime
from pathlib import Path

from scripts.sources.hkma_chats_cnh import build_payload

HK_FIXTURE = Path(__file__).parent / "fixtures" / "sources" / "hkgov_general_holidays" / "2026.html"
CN_FIXTURE = Path(__file__).parent / "fixtures" / "sources" / "cfets_cny" / "sample.json"


def _payload_2026() -> dict:
    hk = HK_FIXTURE.read_bytes()
    cn = CN_FIXTURE.read_bytes()
    return build_payload((2026, 2030), {2026: hk}, [cn])


def _by_date(holidays):
    return {h["date"]: h for h in holidays}


def test_metadata():
    p = _payload_2026()
    assert p["currency"] == "CNH"
    assert p["calendar_kind"] == "RTGS"
    assert "CNH" in p["calendar_name"]
    src = p["default_source"]
    assert src["url"].startswith("https://www.hkma.gov.hk/")
    datetime.fromisoformat(src["fetched_at"].replace("Z", "+00:00"))


def test_validity_clamped_to_intersection():
    """HK fixture only covers 2026; CFETS fixture covers 2025-2027. CNH
    coverage must be clamped to the intersection (2026 only)."""
    p = _payload_2026()
    assert p["valid_from"] == "2026-01-01"
    assert p["valid_until"] == "2026-12-31"
    years = {h["date"][:4] for h in p["holidays"]}
    assert years == {"2026"}


def test_union_includes_both_hk_only_and_prc_only_dates():
    by_date = _by_date(_payload_2026()["holidays"])
    # HK-only: Good Friday is a HK statutory holiday but not a PRC market
    # closure (the PRC observes Tomb-Sweeping/Ching Ming around the same
    # period, but Good Friday itself is not a PRC holiday).
    assert "2026-04-03" in by_date
    assert by_date["2026-04-03"]["source"]["url"].startswith("https://www.gov.hk/")
    # PRC-only: May 5 is part of mainland Labour Day Golden Week but not
    # a HK statutory holiday.
    assert "2026-05-05" in by_date
    assert "chinamoney.com.cn" in by_date["2026-05-05"]["source"]["url"]


def test_overlap_dates_resolve_to_hk_source_with_note():
    """When a date is in both legs (e.g. Lunar New Year Day 1), the HK
    source wins and the PRC co-closure is flagged in the note."""
    by_date = _by_date(_payload_2026()["holidays"])
    lny1 = by_date["2026-02-17"]
    assert "gov.hk" in lny1["source"]["url"]
    assert "mainland" in (lny1["note"] or "").lower()


def test_prc_only_entries_have_note():
    by_date = _by_date(_payload_2026()["holidays"])
    may5 = by_date["2026-05-05"]
    assert "PRC" in (may5["note"] or "")


def test_every_entry_has_resolvable_per_entry_source():
    """Data-integrity contract: each entry's source has url/doc_title/
    fetched_at populated (no reliance on default)."""
    p = _payload_2026()
    for h in p["holidays"]:
        src = h["source"]
        assert src is not None
        assert src["url"]
        assert src["doc_title"]
        datetime.fromisoformat(src["fetched_at"].replace("Z", "+00:00"))


def test_holidays_within_validity_window():
    """No holiday entries may fall outside the declared validity window."""
    p = _payload_2026()
    vf = p["valid_from"]
    vu = p["valid_until"]
    for h in p["holidays"]:
        assert vf <= h["date"] <= vu
