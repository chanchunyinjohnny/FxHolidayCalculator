"""Tests for the library-backed exchange calendar generator (hybrid v1 floor)."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

# exchange_calendars is an optional runtime extra (see pyproject.toml's
# `[project.optional-dependencies] extras`). Skip this module cleanly when
# it isn't installed so the rest of the test suite still runs under the
# constrained-corporate profile.
pytest.importorskip("exchange_calendars")

from fx_holiday_calculator.calendars.loader import load_exchange_calendar  # noqa: E402
from scripts.sources.library_exchange import build_payload, fetch_all  # noqa: E402


def test_build_payload_has_schema_v3_and_library_provenance():
    payload = build_payload("SGX", (2026, 2026))
    assert payload["schema_version"] == 3
    assert payload["venue"] == "SGX"
    assert payload["calendar_kind"] == "EXCHANGE"
    src = payload["default_source"]
    assert src["url"].startswith("https://pypi.org/project/exchange-calendars")
    assert "exchange_calendars" in src["doc_title"]
    assert "XSES" in src["doc_title"]
    assert "library_exchange" in src["fetcher"]
    # fetched_at is ISO-8601
    datetime.fromisoformat(src["fetched_at"].replace("Z", "+00:00"))


def test_build_payload_clamps_to_library_coverage():
    # User asks for 2030 but library covers SGX only through 2026.
    payload = build_payload("SGX", (2026, 2030))
    vu = date.fromisoformat(payload["valid_until"])
    assert vu.year == 2026, f"valid_until should clamp to library coverage, got {vu}"


def test_build_payload_has_caveat_note_on_entries():
    payload = build_payload("SGX", (2026, 2026))
    assert payload["holidays"], "expected at least one holiday"
    for h in payload["holidays"]:
        assert "library-sourced" in h["note"]
        assert "FX-product" in h["note"]


def test_sgx_2026_includes_known_dates():
    payload = build_payload("SGX", (2026, 2026))
    dates = {h["date"] for h in payload["holidays"]}
    # SGX holidays that should always appear (full-venue closures):
    assert "2026-01-01" in dates  # New Year's Day
    assert "2026-05-01" in dates  # Labour Day
    assert "2026-12-25" in dates  # Christmas


def test_hkex_2026_includes_lunar_new_year_block():
    payload = build_payload("HKEX", (2026, 2026))
    dates = {h["date"] for h in payload["holidays"]}
    assert "2026-02-17" in dates  # Lunar NY Day 1
    assert "2026-02-18" in dates  # Day 2
    assert "2026-02-19" in dates  # Day 3
    assert "2026-10-01" in dates  # National Day


def test_cme_2026_is_sparse_equity_only():
    # CME equity-session calendar is famously sparse for FX-trading purposes.
    # The thin coverage IS the caveat — assert that fact so a future change
    # in library scope doesn't silently improve this without us noticing.
    payload = build_payload("CME", (2026, 2026))
    dates = sorted({h["date"] for h in payload["holidays"]})
    assert dates == ["2026-01-01", "2026-04-03", "2026-12-25"]


def test_fetch_all_writes_three_files(tmp_path):
    paths = fetch_all((2026, 2026), tmp_path)
    assert sorted(p.name for p in paths) == ["CME.json", "HKEX.json", "SGX.json"]
    for p in paths:
        blob = json.loads(p.read_text())
        assert blob["schema_version"] == 3
        assert blob["calendar_kind"] == "EXCHANGE"


def test_loader_marks_library_sourced(tmp_path):
    fetch_all((2026, 2026), tmp_path)
    cal = load_exchange_calendar("SGX", root=tmp_path / "fx_exchange")
    assert cal.library_sourced is True


def test_loader_does_not_mark_primary_sourced(tmp_path):
    # Hand-craft a JSON with a fetcher that does NOT mention library_exchange.
    blob = {
        "schema_version": 3,
        "venue": "SGX",
        "calendar_kind": "EXCHANGE",
        "products": ["USD/CNH Futures"],
        "valid_from": "2026-01-01",
        "valid_until": "2026-12-31",
        "default_source": {
            "url": "https://www.sgx.com/...",
            "doc_title": "SGX Calendar 2026 (PDF)",
            "fetched_at": "2026-05-06T00:00:00Z",
            "fetcher": "scripts/sources/sgx_fx.py@v1",
        },
        "holidays": [],
    }
    p = tmp_path / "SGX.json"
    p.write_text(json.dumps(blob))
    cal = load_exchange_calendar("SGX", root=tmp_path)
    assert cal.library_sourced is False


def test_fetch_preserves_primary_sourced_file(tmp_path):
    # If a primary-sourced JSON already exists, the library generator must
    # not overwrite it.
    out_dir = tmp_path / "fx_exchange"
    out_dir.mkdir()
    primary = out_dir / "SGX.json"
    primary_blob = {
        "schema_version": 3,
        "venue": "SGX",
        "calendar_kind": "EXCHANGE",
        "products": [],
        "valid_from": "2026-01-01",
        "valid_until": "2026-12-31",
        "default_source": {
            "url": "https://www.sgx.com/...",
            "doc_title": "SGX official PDF",
            "fetched_at": "2026-05-06T00:00:00Z",
            "fetcher": "scripts/sources/sgx_fx.py@v1",
        },
        "holidays": [],
    }
    primary.write_text(json.dumps(primary_blob))
    fetch_all((2026, 2026), tmp_path)
    after = json.loads(primary.read_text())
    assert after["default_source"]["doc_title"] == "SGX official PDF"


@pytest.mark.parametrize("venue", ["SGX", "HKEX", "CME"])
def test_data_integrity_for_bundled_library_files(venue):
    # The actual bundled file (committed to repo) must satisfy the provenance
    # contract and validity-window constraints.
    bundled = Path(__file__).parents[1] / "data" / "fx_exchange" / f"{venue}.json"
    if not bundled.exists():
        pytest.skip(f"{venue}.json not bundled yet")
    blob = json.loads(bundled.read_text())
    assert blob["schema_version"] == 3
    assert "valid_from" in blob and "valid_until" in blob
    vf = date.fromisoformat(blob["valid_from"])
    vu = date.fromisoformat(blob["valid_until"])
    for h in blob["holidays"]:
        d = date.fromisoformat(h["date"])
        assert vf <= d <= vu, f"{venue}: {d} outside [{vf} .. {vu}]"
