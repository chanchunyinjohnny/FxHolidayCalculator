"""On-demand refresh of bundled or cached holiday data.

Usage:
    python -m fx_holiday_calculator.refresh                  # all sources, write to user cache (default)
    python -m fx_holiday_calculator.refresh --write-bundled  # write to repo data/ (maintainers)
    python -m fx_holiday_calculator.refresh --source EUR     # single source
    python -m fx_holiday_calculator.refresh --source EUR --source USD
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import urllib.error
from dataclasses import dataclass
from pathlib import Path

# Mapping of source key → (fetcher_module, output_subdir, output_filename).
# v1 RTGS sources are primary-source-driven (one fetcher → one JSON).
# Exchange sources are library-sourced via scripts.sources.library_exchange
# (one fetcher → multiple venue JSONs); see _EXCHANGE_VENUES below.
_SOURCES: dict[str, tuple[str, str, str]] = {
    "EUR": ("scripts.sources.ecb_target2", "fx_rtgs", "EUR.json"),
    "USD": ("scripts.sources.federal_reserve", "fx_rtgs", "USD.json"),
    "GBP": ("scripts.sources.boe_chaps", "fx_rtgs", "GBP.json"),
    "JPY": ("scripts.sources.boj", "fx_rtgs", "JPY.json"),
    "HKD": ("scripts.sources.hkgov_general_holidays", "fx_rtgs", "HKD.json"),
    "CNH": ("scripts.sources.hkma_chats_cnh", "fx_rtgs", "CNH.json"),
    "CAD": ("scripts.sources.payments_canada_lynx", "fx_rtgs", "CAD.json"),
    "CNY": ("scripts.sources.cfets_cny", "fx_fixing", "CNY.json"),
    "KRW": ("scripts.sources.kftc_krw", "fx_fixing", "KRW.json"),
    "TWD": ("scripts.sources.taifx_twd", "fx_fixing", "TWD.json"),
}

# Library-sourced exchange venues. Refreshed via a single generator that
# reads exchange_calendars. Primary-source overrides (when added) are
# preserved by the generator's overwrite guard.
_EXCHANGE_VENUES: tuple[str, ...] = ("SGX", "HKEX", "CME")
_LIBRARY_EXCHANGE_MODULE = "scripts.sources.library_exchange"


@dataclass
class RefreshResult:
    source: str
    changed: bool
    error: str | None
    output_path: Path | None
    # A "soft" error is environmental/transient (upstream unreachable, optional
    # dependency missing) rather than a genuine breakage. Bundled data still
    # loads, so soft errors are reported as warnings and do NOT fail the run.
    soft: bool = False


def _user_cache_dir() -> Path:
    return Path.home() / ".fx_holiday_calculator" / "cache"


# requests exception class names treated as transient network failures.
# Matched by name to avoid importing requests in this lightweight module.
_TRANSIENT_REQUESTS_ERRORS = {
    "ConnectionError",
    "Timeout",
    "ConnectTimeout",
    "ReadTimeout",
    "ChunkedEncodingError",
}


def _is_transient_network_error(exc: BaseException) -> bool:
    """True for transient/environmental network failures (any HTTP client)."""
    if isinstance(exc, (urllib.error.URLError, ConnectionError, TimeoutError)):
        return True
    module = type(exc).__module__ or ""
    if module.startswith("requests") and type(exc).__name__ in _TRANSIENT_REQUESTS_ERRORS:
        return True
    return False


def _refresh_library_exchange(
    venue: str, target: Path, year_range: tuple[int, int]
) -> RefreshResult:
    try:
        mod = importlib.import_module(_LIBRARY_EXCHANGE_MODULE)
    except ModuleNotFoundError as exc:
        missing = exc.name or "exchange_calendars"
        msg = (
            f"{missing!r} not installed — exchange-calendar refresh requires the "
            "optional 'extras' dep group (pip install -e \".[extras]\"). "
            "Bundled data continues to load."
        )
        return RefreshResult(source=venue, changed=False, error=msg, output_path=None, soft=True)
    try:
        out = mod.fetch(year_range, target, venue)
        return RefreshResult(source=venue, changed=True, error=None, output_path=out)
    except Exception as exc:
        return RefreshResult(source=venue, changed=False, error=str(exc), output_path=None)


def refresh_one(
    source: str, target: Path, year_range: tuple[int, int] = (2026, 2030)
) -> RefreshResult:
    if source in _EXCHANGE_VENUES:
        return _refresh_library_exchange(source, target, year_range)
    if source not in _SOURCES:
        known = sorted(list(_SOURCES) + list(_EXCHANGE_VENUES))
        return RefreshResult(
            source=source,
            changed=False,
            error=f"unknown source {source}; known: {known}",
            output_path=None,
        )
    mod_name, subdir, filename = _SOURCES[source]
    try:
        mod = importlib.import_module(mod_name)
        # Some fetchers expose `fetch(year_range, data_root)` (network)
        # and a build_payload(year_range, raw)/(year_range) (offline).
        # For refresh, we always try to fetch live; if that fails callers handle it.
        if hasattr(mod, "fetch"):
            out = mod.fetch(year_range, target)
        else:
            payload = mod.build_payload(year_range)  # type: ignore[call-arg]
            out = target / subdir / filename
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return RefreshResult(source=source, changed=True, error=None, output_path=out)
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        detail = getattr(reason, "strerror", None) or str(reason)
        msg = f"upstream unreachable: {detail}. Bundled data continues to load."
        return RefreshResult(source=source, changed=False, error=msg, output_path=None, soft=True)
    except Exception as exc:
        if _is_transient_network_error(exc):
            msg = f"upstream unreachable: {exc}. Bundled data continues to load."
            return RefreshResult(
                source=source, changed=False, error=msg, output_path=None, soft=True
            )
        return RefreshResult(source=source, changed=False, error=str(exc), output_path=None)


def refresh_all(target: Path, year_range: tuple[int, int] = (2026, 2030)) -> list[RefreshResult]:
    results = [refresh_one(s, target, year_range) for s in _SOURCES]
    results += [refresh_one(v, target, year_range) for v in _EXCHANGE_VENUES]
    return results


def _cli() -> int:
    p = argparse.ArgumentParser(prog="fx_holiday_calculator.refresh")
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--cache", action="store_true", default=True, help="Write to user cache (default)"
    )
    g.add_argument("--write-bundled", action="store_true", help="Write to repo data/ (maintainers)")
    p.add_argument(
        "--source", action="append", help="Specific source key (e.g. EUR). Repeat for multiple."
    )
    p.add_argument("--year-from", type=int, default=2026)
    p.add_argument("--year-to", type=int, default=2030)
    args = p.parse_args()

    if args.write_bundled:
        target = Path(__file__).resolve().parents[1] / "data"
    else:
        target = _user_cache_dir()

    keys = args.source if args.source else list(_SOURCES.keys()) + list(_EXCHANGE_VENUES)
    results = [refresh_one(k, target, (args.year_from, args.year_to)) for k in keys]
    hard_error = False
    for r in results:
        if r.error:
            level = "WARN" if r.soft else "ERROR"
            print(f"  [{level}] {r.source}: {r.error}", file=sys.stderr)
            hard_error = hard_error or not r.soft
        elif r.changed:
            print(f"  [OK]    {r.source} → {r.output_path}")
    # Soft errors (transient upstream / missing optional dep) are warnings only:
    # bundled data still loads, so they must not fail an unattended refresh.
    return 1 if hard_error else 0


if __name__ == "__main__":
    sys.exit(_cli())
