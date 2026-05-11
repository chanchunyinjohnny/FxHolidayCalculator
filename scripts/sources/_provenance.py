"""Common helpers for fetchers — no business logic, only schema scaffolding."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_calendar_json(out_path: Path, payload: dict) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def write_raw(raw_dir: Path, name: str, content: bytes) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / name).write_bytes(content)
