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


def _user_cache_dir() -> Path:
    return Path.home() / ".fx_holiday_calculator" / "cache"


def _refresh_library_exchange(
    venue: str, target: Path, year_range: tuple[int, int]
) -> RefreshResult:
    try:
        mod = importlib.import_module(_LIBRARY_EXCHANGE_MODULE)
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
    except Exception as exc:
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
    for r in results:
        if r.error:
            print(f"  [ERROR] {r.source}: {r.error}", file=sys.stderr)
        elif r.changed:
            print(f"  [OK]    {r.source} → {r.output_path}")
    return 0 if all(r.error is None for r in results) else 1


if __name__ == "__main__":
    sys.exit(_cli())
