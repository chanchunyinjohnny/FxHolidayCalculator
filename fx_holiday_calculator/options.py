"""Listed-FX-options lookup.

The user picks a venue and then a listed option contract. Dates come from
the venue's published contract calendar (`scrape`), or fall back to the
venue's documented rule (`derived`, warning surfaced), or are curated by
a maintainer (`manual`). This module does not compute expiry or delivery
dates — derivation lives in `option_listed.py` and is invoked only by the
refresher scripts, not at lookup time.

Public surface (see spec §4.1):
- `list_venues()` -> [venue codes]
- `list_contracts(venue, pair=None, asof=None, include_expired=False)`
- `get_contract(venue, code)`
- `days_until(contract, asof)`
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from fx_holiday_calculator.calendars.contracts import OptionsContractCalendar
from fx_holiday_calculator.calendars.loader import (
    load_options_contract_calendar,
    load_rtgs_calendar,
)
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import OptionContractEntry
from fx_holiday_calculator.conventions.business_day import CalendarSet, is_good_business_day

_BUNDLED = Path(__file__).resolve().parent.parent / "data"
_CACHE = Path.home() / ".fx_holiday_calculator" / "cache"


class ContractNotFoundError(KeyError):
    """Raised by `get_contract` when (venue, code) does not exist."""


@dataclass
class OptionContractCountdown:
    asof: date
    business_days_to_expiry: int
    business_days_to_delivery: int
    calendar_days_to_expiry: int
    calendar_days_to_delivery: int
    bd_calendar_used: str


def _exchange_dir(root: Path) -> Path:
    return root / "fx_exchange"


def _venues_under(root: Path) -> set[str]:
    d = _exchange_dir(root)
    if not d.exists():
        return set()
    suffix = "_options_contracts.json"
    return {p.name[: -len(suffix)] for p in d.glob(f"*{suffix}")}


def list_venues(*, root: Path | None = None, cache_root: Path | None = None) -> list[str]:
    rt = root if root is not None else _BUNDLED
    ch = cache_root if cache_root is not None else _CACHE
    return sorted(_venues_under(rt) | _venues_under(ch))


def _load_calendar(
    venue: str, root: Path | None, cache_root: Path | None
) -> OptionsContractCalendar:
    rt = (root if root is not None else _BUNDLED) / "fx_exchange"
    ch = (cache_root if cache_root is not None else _CACHE) / "fx_exchange"
    return load_options_contract_calendar(venue, root=rt, cache_root=ch)


def list_contracts(
    venue: str,
    *,
    pair: str | None = None,
    asof: date | None = None,
    include_expired: bool = False,
    root: Path | None = None,
    cache_root: Path | None = None,
) -> list[OptionContractEntry]:
    cal = _load_calendar(venue, root, cache_root)
    return cal.iter_listing(pair=pair, asof=asof, include_expired=include_expired)


def get_contract(
    venue: str,
    code: str,
    *,
    root: Path | None = None,
    cache_root: Path | None = None,
) -> OptionContractEntry:
    cal = _load_calendar(venue, root, cache_root)
    entry = cal.get(code)
    if entry is None:
        raise ContractNotFoundError(f"Option contract {code!r} not found on {venue}")
    return entry


def _legs(pair: str) -> tuple[str, str] | None:
    parts = pair.upper().replace(" ", "").split("/")
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


def _try_load_rtgs(
    currency: str, root: Path | None, cache_root: Path | None
) -> RtgsCalendar | None:
    rt = (root if root is not None else _BUNDLED) / "fx_rtgs"
    ch = (cache_root if cache_root is not None else _CACHE) / "fx_rtgs"
    try:
        return load_rtgs_calendar(currency, root=rt, cache_root=ch)
    except (FileNotFoundError, ValueError):
        return None


def _bd_calendar_set_for_pair(
    pair: str, root: Path | None, cache_root: Path | None
) -> tuple[CalendarSet, str]:
    legs = _legs(pair)
    if legs is None:
        return CalendarSet(members={}), f"weekends only (unparseable pair {pair!r})"
    base, quote = legs
    members: dict[str, object] = {}
    missing: list[str] = []
    for c in (base, quote):
        cal = _try_load_rtgs(c, root, cache_root)
        if cal is None:
            missing.append(c)
        else:
            members[c] = cal
    if not members:
        return (
            CalendarSet(members=members),  # type: ignore[arg-type]
            f"weekends only ({base}+{quote} not bundled)",
        )
    label_parts = [f"{c} ({members[c].calendar_name})" for c in members]  # type: ignore[union-attr]
    label = " ∪ ".join(label_parts)
    if missing:
        label += f"  (no calendar bundled for {'/'.join(missing)})"
    return CalendarSet(members=members), label  # type: ignore[arg-type]


def _count_business_days(asof: date, target: date, cs: CalendarSet) -> int:
    if target == asof:
        return 0
    direction = 1 if target > asof else -1
    cur = asof
    count = 0
    while cur != target:
        cur = cur + timedelta(days=direction)
        if is_good_business_day(cur, cs):
            count += direction
    return count


def days_until(
    contract: OptionContractEntry,
    asof: date,
    *,
    root: Path | None = None,
    cache_root: Path | None = None,
) -> OptionContractCountdown:
    cs, label = _bd_calendar_set_for_pair(contract.pair, root, cache_root)
    bd_exp = _count_business_days(asof, contract.expiry_date, cs)
    bd_del = _count_business_days(asof, contract.delivery_date, cs)
    cd_exp = (contract.expiry_date - asof).days
    cd_del = (contract.delivery_date - asof).days
    return OptionContractCountdown(
        asof=asof,
        business_days_to_expiry=bd_exp,
        business_days_to_delivery=bd_del,
        calendar_days_to_expiry=cd_exp,
        calendar_days_to_delivery=cd_del,
        bd_calendar_used=label,
    )
