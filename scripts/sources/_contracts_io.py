"""I/O helpers for `<VENUE>_contracts.json` files.

The load-bearing function is `merge_preserving_manual`: when a fetcher writes
a fresh contract-listing payload, any pre-existing rows tagged
`derivation_mode == "manual"` must survive verbatim. Manual rows are the
user's release-valve when neither scrape nor derivation produces an
authoritative value, and they always win on `(code, contract_month)` key
collisions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _row_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("code", "")).upper(), str(row.get("contract_month", "")))


def merge_preserving_manual(existing_path: Path, new_payload: dict[str, Any]) -> dict[str, Any]:
    """Return `new_payload` with any manual rows from `existing_path` re-inserted.

    - Reads `existing_path` if it exists; otherwise returns `new_payload` unchanged.
    - Identifies manual rows by `derivation_mode == "manual"` at the entry level.
    - Manual rows take precedence over any scrape/derive row sharing the same
      `(code, contract_month)` key.
    - Preserves the contracts ordering: manual rows from the existing file are
      placed first (their curated order honoured), then the remaining
      scrape/derive rows from the new payload in their original order, with any
      colliding-key rows from the new payload dropped.
    """
    if not existing_path.exists():
        return new_payload

    try:
        existing = json.loads(existing_path.read_text())
    except (OSError, json.JSONDecodeError):
        # Corrupt or unreadable existing file — fail safe by returning new payload.
        return new_payload

    manual_rows = [
        row for row in existing.get("contracts", []) if row.get("derivation_mode") == "manual"
    ]
    if not manual_rows:
        return new_payload

    manual_keys = {_row_key(row) for row in manual_rows}
    new_rows = [row for row in new_payload.get("contracts", []) if _row_key(row) not in manual_keys]
    merged = dict(new_payload)
    merged["contracts"] = manual_rows + new_rows
    return merged
