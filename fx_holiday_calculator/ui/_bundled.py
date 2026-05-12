"""Helpers that introspect bundled calendar data so the UI reflects whatever
is currently shipped under ``data/`` without each tab hard-coding a list.
"""

from __future__ import annotations

from pathlib import Path

_BUNDLED = Path(__file__).resolve().parents[2] / "data"


def available_rtgs_currencies(root: Path | None = None) -> set[str]:
    """Return the set of RTGS currency codes that have a bundled JSON file.

    Used by the product tabs to filter the pair selector to only pairs whose
    legs (and any reference currency they'd consult) have a bundled RTGS
    calendar. The set grows automatically when a new JSON file is added.
    """
    base = (root if root is not None else _BUNDLED) / "fx_rtgs"
    if not base.exists():
        return set()
    return {p.stem for p in base.glob("*.json") if not p.name.startswith("_")}


def available_exchange_venues(root: Path | None = None) -> set[str]:
    base = (root if root is not None else _BUNDLED) / "fx_exchange"
    if not base.exists():
        return set()
    return {p.stem for p in base.glob("*.json") if not p.name.startswith("_")}
