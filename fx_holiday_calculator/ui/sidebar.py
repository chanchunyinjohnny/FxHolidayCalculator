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


def _earliest_fetched_at(root: Path, *, recursive: bool) -> str | None:
    earliest = None
    if not root.exists():
        return None
    paths = root.rglob("*.json") if recursive else root.glob("*.json")
    for p in paths:
        try:
            blob = json.loads(p.read_text())
            stamp = blob["default_source"]["fetched_at"]
            if earliest is None or stamp < earliest:
                earliest = stamp
        except Exception:
            continue
    return earliest


def _bundled_fetched_at() -> str:
    earliest = None
    for sub in ("fx_rtgs", "fx_exchange", "fx_fixing"):
        stamp = _earliest_fetched_at(BUNDLED_DIR / sub, recursive=False)
        if stamp and (earliest is None or stamp < earliest):
            earliest = stamp
    return earliest or "(no data)"


def _cache_fetched_at() -> str | None:
    return _earliest_fetched_at(CACHE_DIR, recursive=True)


def _is_benign_refresh_error(msg: str) -> bool:
    """True for failures where bundled/cached data continues to load unchanged.

    These are expected outcomes (missing optional dep, documented network
    egress restrictions to a known-flaky source) and shouldn't render as
    red errors in the UI.
    """
    return "upstream unreachable" in msg or "not installed" in msg


def render() -> None:
    sb = st.sidebar
    sb.header("Data origin")
    sb.write(f"Bundled fetched: **{_bundled_fetched_at()}**")
    cache_stamp = _cache_fetched_at()
    if cache_stamp:
        sb.write(f"Cache fetched: **{cache_stamp}**")
    else:
        sb.write("Cache: **(empty)**")

    if sb.button("↻ Refresh all sources"):
        with sb.status("Refreshing all sources…", expanded=True) as status:
            results = refresh_all(CACHE_DIR)
            for r in results:
                if r.error:
                    if _is_benign_refresh_error(r.error):
                        sb.warning(f"{r.source}: {r.error}")
                    else:
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
                    if _is_benign_refresh_error(r.error):
                        sb.warning(f"{code}: {r.error}")
                    else:
                        sb.error(f"{code}: {r.error}")
                else:
                    sb.success(f"{code}: refreshed")

    sb.markdown("---")
    sb.caption(
        "v1.1 covers 4 primary-sourced RTGS calendars + 3 library-sourced fixing "
        "calendars (CNY / KRW / TWD; primary sources CFETS / KFTC / Taipei Forex "
        "deferred). Exchange calendars are library-sourced; additional sources deferred."
    )
