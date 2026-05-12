"""CNH RTGS — offshore CNY clearing in Hong Kong.

CNH (offshore RMB) settles through HKMA's RMB RTGS in Hong Kong. The
calendar is the **union** of two primary sources:

1. **Hong Kong leg** — HKICL's Renminbi Clearing House Rules define
   "Working Day" by reference to the General Holidays Ordinance
   (Cap. 149), mirroring the HKD-CHATS rule. The HK leg is therefore
   the same statutory holiday list served at
   ``https://www.gov.hk/en/about/abouthk/holiday/<YYYY>.htm`` —
   reused here via :mod:`scripts.sources.hkgov_general_holidays`.

2. **Mainland PRC leg** — onshore CNY market closures (Spring Festival /
   Labour Day / National Day Golden Weeks, plus working-Saturday
   make-up days) drain mainland RMB liquidity and effectively close
   offshore CNH clearing for those dates. The primary source is the
   CFETS FX Trading Calendar served by chinamoney.com.cn —
   reused here via :mod:`scripts.sources.cfets_cny`.

Each holiday entry carries a per-entry ``source`` override pointing to
the actual primary source (gov.hk page for HK dates, chinamoney.com.cn
API for PRC dates). When the same date appears in both legs, the HK
source wins (HK is the operative jurisdiction for the offshore clearing
system) and the PRC origin is recorded in the ``note`` field.

Caveat: working-Saturday make-up days in the PRC calendar do **not**
make CNH settle on a Saturday — the RTGS weekend closure rule still
applies. We include Saturday entries in the JSON for transparency, but
the engine's weekend exclusion masks them.

See docs/data-sources.md#cnh--cny-clearing-in-hong-kong.
"""

from __future__ import annotations

from pathlib import Path

from scripts.sources import cfets_cny as cn_src
from scripts.sources import hkgov_general_holidays as hk_src
from scripts.sources._provenance import now_iso_utc, write_calendar_json, write_raw

_DEFAULT_URL = (
    "https://www.hkma.gov.hk/eng/key-functions/international-financial-centre/"
    "financial-market-infrastructure/payment-systems/"
)
_DEFAULT_DOC_TITLE = "HKMA — Payment Systems (RMB clearing in Hong Kong)"
_FETCHER = "scripts/sources/hkma_chats_cnh.py@v1"

_PRC_NOTE = "PRC public holiday — onshore CNY market closure affects offshore CNH clearing"
_BOTH_NOTE = "HK general holiday; mainland PRC market also closed"


def _cn_source(fetched_at: str) -> dict:
    return {
        "url": cn_src._PAGE_URL,  # noqa: SLF001 — intentional reuse
        "doc_title": cn_src._DOC_TITLE,  # noqa: SLF001
        "fetched_at": fetched_at,
        "fetcher": cn_src._FETCHER,  # noqa: SLF001
    }


def _merge(
    hk_entries: list[dict],
    cn_entries: list[dict],
    cn_source_obj: dict,
    year_range: tuple[int, int],
) -> list[dict]:
    """Union HK and PRC closure dates. HK origin wins on conflict.

    Each output entry has a per-entry ``source`` override (either the
    gov.hk year page from the HK leg, or the CFETS API URL for PRC-only
    dates). Dates in both legs carry the HK source and a note flagging
    the mainland co-closure for transparency.
    """
    hk_by_date = {h["date"]: h for h in hk_entries}
    cn_by_date = {h["date"]: h for h in cn_entries}
    merged: dict[str, dict] = {}

    for iso, hk in hk_by_date.items():
        year = int(iso[:4])
        if not (year_range[0] <= year <= year_range[1]):
            continue
        also_cn = iso in cn_by_date
        merged[iso] = {
            "date": iso,
            "name": hk["name"],
            "source": hk["source"],
            "note": _BOTH_NOTE if also_cn else None,
        }

    for iso, cn in cn_by_date.items():
        if iso in merged:
            continue
        year = int(iso[:4])
        if not (year_range[0] <= year <= year_range[1]):
            continue
        merged[iso] = {
            "date": iso,
            "name": cn["name"],
            "source": cn_source_obj,
            "note": _PRC_NOTE,
        }

    return [merged[k] for k in sorted(merged)]


def build_payload(
    year_range: tuple[int, int],
    hk_pages: dict[int, bytes],
    cn_raw: list[bytes],
) -> dict:
    """Assemble a v3 CNH payload from raw HK pages and raw CFETS responses.

    ``hk_pages``: ``{year: html_bytes}`` from :func:`hk_src.fetch_pages`.
    ``cn_raw``: list of raw CFETS API responses (one per ``selectedYear``
    call). Multiple responses are deduped by ISO date.
    """
    stamp = now_iso_utc()

    hk_entries: list[dict] = []
    hk_covered: list[int] = []
    for year in sorted(hk_pages):
        if not (year_range[0] <= year <= year_range[1]):
            continue
        hk_entries.extend(hk_src.parse_document(hk_pages[year], year, fetched_at=stamp))
        hk_covered.append(year)

    cn_entries: list[dict] = []
    cn_seen: set[str] = set()
    cn_covered: set[int] = set()
    for raw in cn_raw:
        for h in cn_src.parse_document(raw, year_range):
            if h["date"] in cn_seen:
                continue
            cn_seen.add(h["date"])
            cn_entries.append(h)
        cn_covered.update(cn_src._year_list(raw))  # noqa: SLF001

    # CNH coverage is bound by whichever leg covers fewer years — the
    # calendar is only meaningful within the intersection. The holidays
    # list is then filtered to that window so it cannot reference dates
    # outside the declared validity range.
    cn_in_range = sorted(cn_covered & set(range(year_range[0], year_range[1] + 1)))
    if hk_covered and cn_in_range:
        vf_year = max(min(hk_covered), min(cn_in_range))
        vu_year = min(max(hk_covered), max(cn_in_range))
        if vu_year < vf_year:
            vf_year, vu_year = year_range
    elif hk_covered:
        vf_year, vu_year = min(hk_covered), max(hk_covered)
    elif cn_in_range:
        vf_year, vu_year = min(cn_in_range), max(cn_in_range)
    else:
        vf_year, vu_year = year_range

    cn_source_obj = _cn_source(stamp)
    holidays = _merge(hk_entries, cn_entries, cn_source_obj, (vf_year, vu_year))

    return {
        "schema_version": 3,
        "currency": "CNH",
        "calendar_kind": "RTGS",
        "calendar_name": "Offshore CNY clearing in Hong Kong (CNH RTGS)",
        "operator": "HKMA-appointed RMB Clearing Bank (under HKICL rules)",
        "valid_from": f"{vf_year}-01-01",
        "valid_until": f"{vu_year}-12-31",
        "default_source": {
            "url": _DEFAULT_URL,
            "doc_title": _DEFAULT_DOC_TITLE,
            "fetched_at": stamp,
            "fetcher": _FETCHER,
        },
        "holidays": holidays,
    }


def _fetch_cn_responses(year_range: tuple[int, int], raw_dir: Path | None) -> list[bytes]:
    """Walk CFETS by selectedYear the same way scripts.sources.cfets_cny.fetch does."""
    out: list[bytes] = []
    next_year = year_range[0]
    seen_max = -1
    while next_year <= year_range[1]:
        try:
            raw = cn_src._fetch_year(next_year)  # noqa: SLF001
        except Exception:
            break
        out.append(raw)
        if raw_dir is not None:
            write_raw(raw_dir, f"CNH-cfets-{next_year}.json", raw)
        api_years = cn_src._year_list(raw)  # noqa: SLF001
        api_max = max(api_years, default=-1)
        if api_max <= seen_max:
            break
        seen_max = api_max
        next_year = api_max + 1
    return out


def fetch(year_range: tuple[int, int], data_root: Path) -> Path:
    raw_dir = data_root / "fx_rtgs" / "_raw"
    hk_pages = hk_src.fetch_pages(year_range, raw_dir)
    cn_raw = _fetch_cn_responses(year_range, raw_dir)
    if not hk_pages and not cn_raw:
        raise RuntimeError(
            "Neither gov.hk nor CFETS returned data for " f"{year_range[0]}..{year_range[1]}"
        )
    payload = build_payload(year_range, hk_pages, cn_raw)
    out = data_root / "fx_rtgs" / "CNH.json"
    write_calendar_json(out, payload)
    return out


if __name__ == "__main__":
    import sys

    fetch((2026, 2030), Path(__file__).parents[2] / "data")
    sys.exit(0)
