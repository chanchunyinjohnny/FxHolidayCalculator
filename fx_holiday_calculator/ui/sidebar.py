import json
from pathlib import Path

import streamlit as st

from fx_holiday_calculator.refresh import _EXCHANGE_VENUES, _SOURCES, refresh_all, refresh_one

CACHE_DIR = Path.home() / ".fx_holiday_calculator" / "cache"
BUNDLED_DIR = Path(__file__).resolve().parents[2] / "data"

# (label, codes, subdir, library-marker-substring). library_marker=None means
# the group is never library-sourced (primary-source-driven).
_GROUPS: tuple[tuple[str, tuple[str, ...], str, str | None], ...] = (
    (
        "Settlement holidays (RTGS)",
        tuple(c for c, (_m, sub, _f) in _SOURCES.items() if sub == "fx_rtgs"),
        "fx_rtgs",
        None,
    ),
    (
        "Exchange holidays",
        _EXCHANGE_VENUES,
        "fx_exchange",
        "library_exchange",
    ),
    (
        "NDF fixing calendars",
        tuple(c for c, (_m, sub, _f) in _SOURCES.items() if sub == "fx_fixing"),
        "fx_fixing",
        "library_fixing",
    ),
)


def _group_library_sourced(codes: tuple[str, ...], subdir: str, marker: str | None) -> bool:
    if marker is None:
        return False
    for code in codes:
        path = BUNDLED_DIR / subdir / f"{code}.json"
        if not path.exists():
            continue
        try:
            blob = json.loads(path.read_text())
            fetcher = blob.get("default_source", {}).get("fetcher", "")
            if marker in fetcher:
                return True
        except Exception:
            continue
    return False


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
    for label, codes, subdir, marker in _GROUPS:
        if not codes:
            continue
        sb.markdown(f"**{label}**")
        if _group_library_sourced(codes, subdir, marker):
            sb.caption("⚠ Library-sourced — see caveats in main panel.")
        for code in codes:
            cols = sb.columns([3, 1])
            cols[0].write(code)
            if cols[1].button("↻", key=f"refresh_{code}"):
                r = refresh_one(code, CACHE_DIR)
                if r.error:
                    sb.error(f"{code}: {r.error}")
                else:
                    sb.success(f"{code}: refreshed")

    sb.markdown("---")
    sb.caption(
        "v1.1 covers 4 primary-sourced RTGS calendars + 3 library-sourced fixing "
        "calendars (CNY / KRW / TWD; primary sources CFETS / KFTC / Taipei Forex "
        "deferred). Exchange calendars are library-sourced; additional sources deferred."
    )
