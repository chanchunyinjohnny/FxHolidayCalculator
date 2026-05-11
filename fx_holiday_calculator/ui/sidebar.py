import json
from pathlib import Path

import streamlit as st

from fx_holiday_calculator.refresh import _SOURCES, refresh_all, refresh_one

CACHE_DIR = Path.home() / ".fx_holiday_calculator" / "cache"
BUNDLED_DIR = Path(__file__).resolve().parents[2] / "data"


def _bundled_fetched_at() -> str:
    earliest = None
    for sub in ("fx_rtgs", "fx_exchange", "fx_fixing"):
        d = BUNDLED_DIR / sub
        if not d.exists():
            continue
        for p in d.glob("*.json"):
            try:
                blob = json.loads(p.read_text())
                stamp = blob["default_source"]["fetched_at"]
                if earliest is None or stamp < earliest:
                    earliest = stamp
            except Exception:
                continue
    return earliest or "(no data)"


def _cache_status() -> str:
    if not CACHE_DIR.exists() or not any(CACHE_DIR.rglob("*.json")):
        return "(empty)"
    return "live cache present"


def render() -> None:
    sb = st.sidebar
    sb.header("Data origin")
    sb.write(f"Bundled fetched: **{_bundled_fetched_at()}**")
    sb.write(f"Cache: **{_cache_status()}**")

    if sb.button("↻ Refresh all sources"):
        with sb.status("Refreshing all sources…", expanded=True) as status:
            results = refresh_all(CACHE_DIR)
            for r in results:
                if r.error:
                    sb.error(f"{r.source}: {r.error}")
                else:
                    sb.success(f"{r.source}: refreshed")
            status.update(label="Refresh complete", state="complete")

    if sb.button("✗ Clear refresh cache"):
        if CACHE_DIR.exists():
            for p in CACHE_DIR.rglob("*.json"):
                p.unlink()
        sb.success("Cache cleared")

    sb.markdown("---")
    sb.subheader("Per-source refresh")
    for code in _SOURCES.keys():
        cols = sb.columns([3, 1])
        cols[0].write(f"**{code}**")
        if cols[1].button("↻", key=f"refresh_{code}"):
            r = refresh_one(code, CACHE_DIR)
            if r.error:
                sb.error(f"{code}: {r.error}")
            else:
                sb.success(f"{code}: refreshed")

    sb.markdown("---")
    sb.caption(
        "v1.1 covers 4 RTGS sources + 3 fixing sources (CFETS / KFTC / Taipei Forex). "
        "Exchange and additional sources deferred."
    )
