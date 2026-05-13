import json
import logging
from datetime import date, datetime
from pathlib import Path

from fx_holiday_calculator.calendars.contracts import ContractCalendar
from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.fixing import FixingCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import ContractEntry, HolidayEntry, SourceRef

_log = logging.getLogger(__name__)


def _parse_source(raw: dict) -> SourceRef:
    fetched = datetime.fromisoformat(raw["fetched_at"].replace("Z", "+00:00"))
    return SourceRef(
        url=raw["url"],
        doc_title=raw["doc_title"],
        fetched_at=fetched,
        fetcher=raw["fetcher"],
    )


def _is_v3_blob(blob: dict) -> bool:
    """Schema 3 added required valid_from/valid_until. A cache file from an
    older version of this tool predates that and must be skipped."""
    return "valid_from" in blob and "valid_until" in blob


def _load_calendar_blob(name: str, root: Path, cache_root: Path | None) -> tuple[dict, str]:
    if cache_root is not None:
        cache_path = cache_root / f"{name}.json"
        if cache_path.exists():
            try:
                blob = json.loads(cache_path.read_text())
            except json.JSONDecodeError as exc:
                _log.warning(
                    "Cache file %s is corrupt (%s); falling back to bundled.",
                    cache_path,
                    exc,
                )
            else:
                if _is_v3_blob(blob):
                    return blob, "cache"
                _log.warning(
                    "Cache file %s predates schema_version 3 (no valid_from/"
                    "valid_until); falling back to bundled. Run `python -m "
                    "fx_holiday_calculator.refresh` to regenerate the cache.",
                    cache_path,
                )
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


def _parse_window(blob: dict, label: str) -> tuple[date, date]:
    try:
        vf = date.fromisoformat(blob["valid_from"])
        vu = date.fromisoformat(blob["valid_until"])
    except KeyError as exc:
        raise ValueError(
            f"{label}: calendar JSON missing required field {exc.args[0]!r} "
            f"(valid_from/valid_until are required from schema_version 2)"
        ) from None
    if vu < vf:
        raise ValueError(f"{label}: valid_until ({vu}) precedes valid_from ({vf})")
    return vf, vu


def load_rtgs_calendar(currency: str, root: Path, cache_root: Path | None = None) -> RtgsCalendar:
    blob, origin = _load_calendar_blob(currency, root, cache_root)
    if blob.get("calendar_kind") != "RTGS":
        raise ValueError(f"{currency}.json is not an RTGS calendar")
    if blob.get("currency") != currency:
        raise ValueError(f"{currency}.json currency mismatch")
    vf, vu = _parse_window(blob, f"{currency}.json")
    return RtgsCalendar(
        currency=blob["currency"],
        calendar_name=blob["calendar_name"],
        operator=blob["operator"],
        entries_by_date=_build_entries(blob, origin),
        valid_from=vf,
        valid_until=vu,
    )


def load_exchange_calendar(
    venue: str, root: Path, cache_root: Path | None = None
) -> ExchangeCalendar:
    blob, origin = _load_calendar_blob(venue, root, cache_root)
    if blob.get("calendar_kind") != "EXCHANGE":
        raise ValueError(f"{venue}.json is not an EXCHANGE calendar")
    if blob.get("venue") != venue:
        raise ValueError(f"{venue}.json venue mismatch")
    vf, vu = _parse_window(blob, f"{venue}.json")
    fetcher = blob.get("default_source", {}).get("fetcher", "")
    library_sourced = "library_exchange" in fetcher
    return ExchangeCalendar(
        venue=blob["venue"],
        products=tuple(blob.get("products", [])),
        entries_by_date=_build_entries(blob, origin),
        valid_from=vf,
        valid_until=vu,
        library_sourced=library_sourced,
    )


def _allowed_modes() -> set[str]:
    return {"scrape", "derived", "manual"}


def load_contract_calendar(
    venue: str, root: Path, cache_root: Path | None = None
) -> ContractCalendar:
    """Load `<venue>_contracts.json` (cache > bundled) into a `ContractCalendar`.

    Per-entry `source` overrides win over `default_source`; per-entry
    `derivation_mode` overrides win over `default_source.default_derivation_mode`.
    Manual entries without their own `source` override fall back to the file
    default, which is intentional — the data-integrity test is the gate that
    flags missing manual-row provenance, not this loader.
    """
    name = f"{venue}_contracts"
    blob, origin = _load_calendar_blob(name, root, cache_root)
    if blob.get("calendar_kind") != "EXCHANGE_CONTRACTS":
        raise ValueError(f"{name}.json is not an EXCHANGE_CONTRACTS file")
    if blob.get("venue") != venue:
        raise ValueError(f"{name}.json venue mismatch")
    default_src_raw = blob["default_source"]
    default_src = _parse_source(default_src_raw)
    default_mode = default_src_raw.get("default_derivation_mode")
    if default_mode not in _allowed_modes():
        raise ValueError(
            f"{name}.json default_derivation_mode={default_mode!r}; expected one of "
            f"{sorted(_allowed_modes())}"
        )

    entries: list[ContractEntry] = []
    for raw in blob.get("contracts", []):
        mode = raw.get("derivation_mode") or default_mode
        if mode not in _allowed_modes():
            raise ValueError(
                f"{name}.json contract {raw.get('code')!r}: invalid derivation_mode={mode!r}"
            )
        src = _parse_source(raw["source"]) if raw.get("source") else default_src
        ltd = date.fromisoformat(raw["last_trading_day"])
        settle = date.fromisoformat(raw["settlement_date"])
        fnd_raw = raw.get("first_notice_day")
        fnd = date.fromisoformat(fnd_raw) if fnd_raw else None
        entries.append(
            ContractEntry(
                venue=venue,
                code=raw["code"],
                pair=raw["pair"],
                product_name=raw["product_name"],
                contract_month=raw["contract_month"],
                last_trading_day=ltd,
                settlement_date=settle,
                first_notice_day=fnd,
                derivation_mode=mode,  # type: ignore[arg-type]
                source=src,
                source_origin=origin,  # type: ignore[arg-type]
                note=raw.get("note"),
            )
        )
    return ContractCalendar(
        venue=venue,
        entries=tuple(entries),
        default_derivation_mode_is_derived=(default_mode == "derived"),
    )


def load_fixing_calendar(
    currency: str, root: Path, cache_root: Path | None = None
) -> FixingCalendar:
    blob, origin = _load_calendar_blob(currency, root, cache_root)
    if blob.get("calendar_kind") != "FIXING":
        raise ValueError(f"{currency}.json is not a FIXING calendar")
    if blob.get("currency") != currency:
        raise ValueError(f"{currency}.json currency mismatch")
    vf, vu = _parse_window(blob, f"{currency}.json")
    fetcher = blob.get("default_source", {}).get("fetcher", "")
    library_sourced = "library_fixing" in fetcher
    return FixingCalendar(
        currency=blob["currency"],
        calendar_name=blob["calendar_name"],
        operator=blob["operator"],
        entries_by_date=_build_entries(blob, origin),
        valid_from=vf,
        valid_until=vu,
        library_sourced=library_sourced,
    )
