from pathlib import Path

from fx_holiday_calculator.refresh import RefreshResult, refresh_one


def test_refresh_one_writes_to_cache(tmp_path: Path, monkeypatch):
    cache_root = tmp_path / "cache"

    # Patch the ECB fetcher's build_payload to return a deterministic blob.
    from scripts.sources import ecb_target2

    def fake_build(year_range):
        return {
            "schema_version": 1,
            "currency": "EUR",
            "calendar_kind": "RTGS",
            "calendar_name": "TARGET2",
            "operator": "Eurosystem",
            "default_source": {
                "url": "https://x",
                "doc_title": "x",
                "fetched_at": "2026-05-06T00:00:00Z",
                "fetcher": "test",
            },
            "holidays": [{"date": "2026-01-01", "name": "NYD", "source": None, "note": None}],
        }

    monkeypatch.setattr(ecb_target2, "build_payload", fake_build)

    result = refresh_one("EUR", target=cache_root)
    assert isinstance(result, RefreshResult)
    assert result.changed is True
    assert (cache_root / "fx_rtgs" / "EUR.json").exists()


def test_refresh_unknown_source_returns_error():
    from pathlib import Path as P

    result = refresh_one("XXX", target=P("/tmp/nonexistent"))
    assert result.changed is False
    assert result.error is not None
