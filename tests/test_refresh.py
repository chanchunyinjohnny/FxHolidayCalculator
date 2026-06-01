import urllib.error
from pathlib import Path

from fx_holiday_calculator.refresh import (
    _SOURCES,
    RefreshResult,
    _is_transient_network_error,
    refresh_one,
)


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


def test_refresh_sources_include_fixing_currencies():
    assert "CNY" in _SOURCES
    assert "KRW" in _SOURCES
    assert "TWD" in _SOURCES


def test_refresh_fixing_sources_target_fx_fixing_subdir():
    _, subdir_cny, file_cny = _SOURCES["CNY"]
    assert subdir_cny == "fx_fixing"
    assert file_cny == "CNY.json"
    _, subdir_krw, file_krw = _SOURCES["KRW"]
    assert subdir_krw == "fx_fixing"
    assert file_krw == "KRW.json"
    _, subdir_twd, file_twd = _SOURCES["TWD"]
    assert subdir_twd == "fx_fixing"
    assert file_twd == "TWD.json"


def test_refresh_one_urlerror_yields_friendly_message(tmp_path: Path, monkeypatch):
    from scripts.sources import kftc_krw

    def boom(year_range, data_root):
        raise urllib.error.URLError(ConnectionResetError(104, "Connection reset by peer"))

    monkeypatch.setattr(kftc_krw, "fetch", boom)

    result = refresh_one("KRW", target=tmp_path)
    assert result.changed is False
    assert result.error is not None
    assert "<urlopen error" not in result.error
    assert "upstream unreachable" in result.error
    assert "Connection reset by peer" in result.error
    assert "Bundled data continues to load" in result.error
    # Transient upstream failures are soft: they must not fail an unattended run.
    assert result.soft is True


def test_refresh_one_requests_connection_error_is_soft(tmp_path: Path, monkeypatch):
    from scripts.sources import boe_chaps

    class _FakeRequestsConnectionError(Exception):
        pass

    # Mimic requests.exceptions.ConnectionError by module + class name.
    _FakeRequestsConnectionError.__module__ = "requests.exceptions"
    _FakeRequestsConnectionError.__name__ = "ConnectionError"

    def boom(year_range, data_root):
        raise _FakeRequestsConnectionError("Max retries exceeded")

    monkeypatch.setattr(boe_chaps, "fetch", boom)

    result = refresh_one("GBP", target=tmp_path)
    assert result.changed is False
    assert result.soft is True
    assert "upstream unreachable" in result.error


def test_refresh_one_parse_error_is_hard(tmp_path: Path, monkeypatch):
    from scripts.sources import ecb_target2

    def boom(year_range):
        raise ValueError("unexpected document layout")

    monkeypatch.setattr(ecb_target2, "build_payload", boom)

    result = refresh_one("EUR", target=tmp_path)
    assert result.changed is False
    assert result.error is not None
    # Genuine breakage (not network) stays a hard error so CI surfaces it.
    assert result.soft is False


def test_is_transient_network_error_classification():
    assert _is_transient_network_error(urllib.error.URLError("boom")) is True
    assert _is_transient_network_error(ConnectionResetError(104, "reset")) is True
    assert _is_transient_network_error(TimeoutError()) is True
    assert _is_transient_network_error(ValueError("bad parse")) is False
