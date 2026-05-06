import json
from datetime import date, datetime
from pathlib import Path

from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import HolidayEntry, SourceRef


def _parse_source(raw: dict) -> SourceRef:
    fetched = datetime.fromisoformat(raw["fetched_at"].replace("Z", "+00:00"))
    return SourceRef(
        url=raw["url"],
        doc_title=raw["doc_title"],
        fetched_at=fetched,
        fetcher=raw["fetcher"],
    )


def _load_calendar_blob(
    name: str, root: Path, cache_root: Path | None
) -> tuple[dict, str]:
    if cache_root is not None:
        cache_path = cache_root / f"{name}.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text()), "cache"
    return json.loads((root / f"{name}.json").read_text()), "bundled"


def _build_entries(blob: dict, origin: str) -> dict[date, HolidayEntry]:
    default_src = _parse_source(blob["default_source"])
    entries: dict[date, HolidayEntry] = {}
    for raw in blob.get("holidays", []):
        src = _parse_source(raw["source"]) if raw.get("source") else default_src
        d = date.fromisoformat(raw["date"])
        entries[d] = HolidayEntry(
            date=d,
            name=raw["name"],
            note=raw.get("note"),
            source=src,
            source_origin=origin,  # type: ignore[arg-type]
            is_closure=True,
            liquidity=raw.get("liquidity"),
        )
    for raw in blob.get("informational_dates", []):
        src = _parse_source(raw["source"]) if raw.get("source") else default_src
        d = date.fromisoformat(raw["date"])
        # Don't overwrite a closure entry if the same date is in both arrays.
        if d in entries:
            continue
        entries[d] = HolidayEntry(
            date=d,
            name=raw["name"],
            note=raw.get("note"),
            source=src,
            source_origin=origin,  # type: ignore[arg-type]
            is_closure=False,
            liquidity=raw.get("liquidity"),
        )
    return entries


def load_rtgs_calendar(
    currency: str, root: Path, cache_root: Path | None = None
) -> RtgsCalendar:
    blob, origin = _load_calendar_blob(currency, root, cache_root)
    if blob.get("calendar_kind") != "RTGS":
        raise ValueError(f"{currency}.json is not an RTGS calendar")
    if blob.get("currency") != currency:
        raise ValueError(f"{currency}.json currency mismatch")
    return RtgsCalendar(
        currency=blob["currency"],
        calendar_name=blob["calendar_name"],
        operator=blob["operator"],
        entries_by_date=_build_entries(blob, origin),
    )


def load_exchange_calendar(
    venue: str, root: Path, cache_root: Path | None = None
) -> ExchangeCalendar:
    blob, origin = _load_calendar_blob(venue, root, cache_root)
    if blob.get("calendar_kind") != "EXCHANGE":
        raise ValueError(f"{venue}.json is not an EXCHANGE calendar")
    if blob.get("venue") != venue:
        raise ValueError(f"{venue}.json venue mismatch")
    return ExchangeCalendar(
        venue=blob["venue"],
        products=tuple(blob.get("products", [])),
        entries_by_date=_build_entries(blob, origin),
    )
