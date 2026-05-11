import json
from pathlib import Path

import streamlit as st

BUNDLED = Path(__file__).resolve().parents[2] / "data"

_DEFERRED = [
    ("HKD", "RTGS", "HKMA CHATS (PDF)"),
    ("CNH", "RTGS", "HKMA CNY clearing in HK (PDF)"),
    ("CHF", "RTGS", "SIX SIC"),
    ("CAD", "RTGS", "Payments Canada Lynx"),
    ("AUD", "RTGS", "RBA RITS"),
    ("SGD", "RTGS", "MAS MEPS+ (PDF)"),
    ("CME", "EXCHANGE", "CME FX futures"),
    ("HKEX", "EXCHANGE", "HKEX FX futures"),
    ("SGX", "EXCHANGE", "SGX FX futures"),
]


def _summary_rows() -> list[dict]:
    rows: list[dict] = []
    for kind, label in [("fx_rtgs", "RTGS"), ("fx_exchange", "EXCHANGE")]:
        d = BUNDLED / kind
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json")):
            try:
                blob = json.loads(p.read_text())
            except Exception:
                continue
            src = blob["default_source"]
            rows.append(
                {
                    "Kind": label,
                    "Code": blob.get("currency") or blob.get("venue"),
                    "Calendar": blob.get("calendar_name") or blob.get("venue"),
                    "Operator": blob.get("operator", "-"),
                    "Source URL": src["url"],
                    "Document": src["doc_title"],
                    "Fetched": src["fetched_at"],
                    "Fetcher": src["fetcher"],
                }
            )
    return rows


def render() -> None:
    st.subheader("About / Sources")
    st.markdown(
        """
**Methodology.** This tool draws settlement (RTGS) and exchange holiday data
exclusively from primary-source documents — central bank publications and
exchange operator notices. National (public) holidays are sourced from the
`python-holidays` library at runtime and shown for reference only; they
never drive any calculation.

**Cross-currency rule.** When a reference currency is selected, the spot date
must be a good business day in *all three* of base, quote, and reference.

**Date adjustment.** Modified-following business-day adjustment with
end-of-month rule. USD/CAD spot is T+1; all other in-scope pairs are T+2.

**Provenance contract.** Every holiday returned by this tool is paired with
the URL of the document it came from and the timestamp it was fetched at.
There are no unsourced dates.
        """
    )

    st.markdown("### Sources currently loaded (bundled)")
    rows = _summary_rows()
    if rows:
        st.dataframe(rows, use_container_width=True)
    else:
        st.write("_No bundled data found._")

    st.markdown("### Deferred sources (v1.1+)")
    deferred_rows = [{"Code": c, "Kind": k, "Description": d} for (c, k, d) in _DEFERRED]
    st.dataframe(deferred_rows, use_container_width=True)
    st.caption(
        "v1 ships with EUR, USD, GBP, JPY RTGS calendars only. The deferred sources "
        "are blocked or PDF-based and require manual data sourcing in production."
    )

    st.markdown("### Refresh policy")
    st.write(
        "A monthly GitHub Actions workflow refreshes bundled data and opens "
        "an auto-PR when upstream changes. Maintainers can also run a manual "
        "refresh; users can refresh into a local cache via the sidebar."
    )

    st.markdown("---")
    st.caption("MIT License")
