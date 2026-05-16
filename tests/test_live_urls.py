"""Opt-in liveness check for every ``default_source.url`` in the bundled
calendars.

This test is **disabled by default** to keep CI offline-friendly and
deterministic. It is meant to be run on a refresh cadence (e.g. in a
maintainer-only GitHub Action or a manual local sweep) to catch URL rot
of the kind that bit the HKEX currency-derivatives landing page.

Run with::

    FX_HOLIDAY_CALC_LIVE=1 python -m pytest tests/test_live_urls.py -v

A non-2xx response is reported as a test failure; a network error is
reported as a skip for that URL (so a single offline host doesn't fail
the run when most URLs are fine). 403 responses are tolerated when the
host is known to gate on User-Agent (the corresponding fetcher already
advertises a browser UA in production).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).parents[1] / "data"

# Hosts that systematically return 403 to non-browser User-Agents. The
# corresponding fetchers already paper over this with a browser UA at
# refresh time; for the liveness probe we accept 403 from these as "URL
# exists" rather than "URL broken".
_UA_GATED_HOSTS = {"www.payments.ca", "www.sgx.com", "www.tpefx.com.tw"}

_LIVE = os.environ.get("FX_HOLIDAY_CALC_LIVE", "").strip() in ("1", "true", "yes")

pytestmark = pytest.mark.skipif(
    not _LIVE,
    reason="liveness check is opt-in — set FX_HOLIDAY_CALC_LIVE=1 to enable",
)


def _all_calendar_files() -> list[Path]:
    out: list[Path] = []
    for sub in ("fx_rtgs", "fx_exchange", "fx_fixing"):
        d = DATA_DIR / sub
        if d.exists():
            out += sorted(p for p in d.glob("*.json") if not p.name.startswith("_"))
    return out


def _collect_urls() -> list[tuple[str, str]]:
    """Return ``[(label, url), ...]`` deduplicated by url."""
    seen: dict[str, str] = {}
    for path in _all_calendar_files():
        blob = json.loads(path.read_text())
        ds = blob.get("default_source") or {}
        url = ds.get("url")
        if url and url not in seen:
            seen[url] = f"{path.name}::default_source"
        for entry in blob.get("holidays", []) + blob.get("contracts", []):
            src = entry.get("source") or {}
            u = src.get("url")
            if u and u not in seen:
                seen[u] = f"{path.name}::{entry.get('date') or entry.get('code')}"
    return sorted((label, url) for url, label in seen.items())


@pytest.mark.parametrize(
    "label,url", _collect_urls(), ids=lambda x: x if isinstance(x, str) else ""
)
def test_url_is_live(label: str, url: str):
    """HEAD (falling back to GET) the URL; require a 2xx (or 3xx) response.

    Network errors are reported as skips, not failures, so a transient
    outage on one host doesn't poison the whole run.
    """
    import urllib.error
    from urllib.parse import urlparse
    from urllib.request import Request, urlopen

    host = urlparse(url).hostname or ""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/json,*/*",
    }

    def _try(method: str) -> int:
        req = Request(url, headers=headers, method=method)
        with urlopen(req, timeout=15) as resp:  # noqa: S310 — controlled URL list
            return resp.getcode()

    try:
        code = _try("HEAD")
    except urllib.error.HTTPError as exc:
        # Some hosts return 405 for HEAD; retry with GET.
        if exc.code in (403, 405):
            try:
                code = _try("GET")
            except urllib.error.HTTPError as exc2:
                code = exc2.code
            except Exception as exc2:  # noqa: BLE001
                pytest.skip(f"{label}: network error on GET: {exc2}")
        else:
            code = exc.code
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"{label}: network error on HEAD: {exc}")

    # 2xx / 3xx are fine. 403 is tolerated on UA-gated hosts.
    if code is not None and 200 <= code < 400:
        return
    if code == 403 and host in _UA_GATED_HOSTS:
        return
    pytest.fail(f"{label}: {url} returned HTTP {code}")
