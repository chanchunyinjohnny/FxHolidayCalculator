"""Listed-FX-futures lookup.

The user picks an exchange and then a listed contract. Dates come from the
venue's published contract calendar (`scrape`), or fall back to the venue's
documented rule (`derived`, warning surfaced), or are curated by a maintainer
(`manual`). This module does not compute LTDs or settlement dates from a
tenor — derivation lives in `future.py` and is invoked only by the contract
fetchers, not at lookup time.

Public surface (see spec §8.6):
- `list_venues()` -> [venue codes]
- `list_contracts(venue, pair=None, asof=None, include_expired=False)`
- `get_contract(venue, code)`
- `days_until(contract, asof)`
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from fx_holiday_calculator.calendars.contracts import ContractCalendar
from fx_holiday_calculator.calendars.loader import load_contract_calendar, load_rtgs_calendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import ContractEntry
from fx_holiday_calculator.conventions.business_day import CalendarSet, is_good_business_day

_BUNDLED = Path(__file__).resolve().parent.parent / "data"
_CACHE = Path.home() / ".fx_holiday_calculator" / "cache"


@dataclass
class ContractCountdown:
    asof: date
    business_days_to_ltd: int
    business_days_to_settlement: int
    calendar_days_to_ltd: int
    calendar_days_to_settlement: int
    bd_calendar_used: str  # human-readable description, e.g. "USD (Fedwire) ∪ EUR (TARGET2)"


def _exchange_dir(root: Path) -> Path:
    return root / "fx_exchange"


def _venues_under(root: Path) -> set[str]:
    d = _exchange_dir(root)
    if not d.exists():
        return set()
    return {p.name[: -len("_contracts.json")] for p in d.glob("*_contracts.json")}


def list_venues(*, root: Path | None = None, cache_root: Path | None = None) -> list[str]:
    """Venues with a bundled or cached contract-listings file. v1: CME/HKEX/SGX."""
    rt = root if root is not None else _BUNDLED
    ch = cache_root if cache_root is not None else _CACHE
    venues = _venues_under(rt) | _venues_under(ch)
    return sorted(venues)


def _load_calendar(venue: str, root: Path | None, cache_root: Path | None) -> ContractCalendar:
    rt = (root if root is not None else _BUNDLED) / "fx_exchange"
    ch = (cache_root if cache_root is not None else _CACHE) / "fx_exchange"
    return load_contract_calendar(venue, root=rt, cache_root=ch)


def list_contracts(
    venue: str,
    *,
    pair: str | None = None,
    asof: date | None = None,
    include_expired: bool = False,
    root: Path | None = None,
    cache_root: Path | None = None,
) -> list[ContractEntry]:
    cal = _load_calendar(venue, root, cache_root)
    return cal.iter_listing(pair=pair, asof=asof, include_expired=include_expired)


def get_contract(
    venue: str,
    code: str,
    *,
    root: Path | None = None,
    cache_root: Path | None = None,
) -> ContractEntry:
    cal = _load_calendar(venue, root, cache_root)
    entry = cal.get(code)
    if entry is None:
        raise KeyError(f"Contract {code!r} not found on {venue}")
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
    """Return the BD-counting calendar set for a pair, plus a human label.

    Falls back gracefully: if a leg currency is not bundled (e.g. INR for an
    SGX USD/INR contract), that leg is dropped with a note in the label. If
    neither leg is bundled, an empty CalendarSet is returned (effectively
    "weekends only") and the label flags this.
    """
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
    """Good business days between `asof` (exclusive) and `target` (inclusive).

    Negative when target precedes asof, zero when target == asof.
    """
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
    contract: ContractEntry,
    asof: date,
    *,
    root: Path | None = None,
    cache_root: Path | None = None,
) -> ContractCountdown:
    cs, label = _bd_calendar_set_for_pair(contract.pair, root, cache_root)
    bd_ltd = _count_business_days(asof, contract.last_trading_day, cs)
    bd_settle = _count_business_days(asof, contract.settlement_date, cs)
    cd_ltd = (contract.last_trading_day - asof).days
    cd_settle = (contract.settlement_date - asof).days
    return ContractCountdown(
        asof=asof,
        business_days_to_ltd=bd_ltd,
        business_days_to_settlement=bd_settle,
        calendar_days_to_ltd=cd_ltd,
        calendar_days_to_settlement=cd_settle,
        bd_calendar_used=label,
    )
