from typing import Literal

from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.conventions.business_day import CalendarSet
from fx_holiday_calculator.pairs import Pair, PairNotFoundError, parse_pair

RefCurrency = Literal["none", "USD", "EUR", "HKD", "CNH"]


class MissingExchangeCalendarError(KeyError):
    """Raised when a swap calculation requires exchange calendars but they are
    not provided (or the relevant venue's calendar is missing from the dict).
    """

    def __init__(self, venue: str):
        self.venue = venue
        super().__init__(f"Exchange calendar not provided for venue {venue!r}")


def rtgs_calendar_set(
    pair: Pair, ref: RefCurrency, calendars: dict[str, RtgsCalendar]
) -> CalendarSet:
    needed = [pair.base, pair.quote]
    if ref != "none" and ref not in needed:
        needed.append(ref)
    members: dict[str, RtgsCalendar] = {}
    for c in needed:
        if c not in calendars:
            raise KeyError(f"Calendar for {c} not provided")
        members[c] = calendars[c]
    return CalendarSet(members=members)  # type: ignore[arg-type]


def relevant_venues(pair: Pair, ref: RefCurrency) -> list[str]:
    venues = set(pair.listed_on)
    if ref != "none" and ref not in {pair.base, pair.quote}:
        for a, b in [(pair.base, ref), (ref, pair.quote)]:
            try:
                leg = parse_pair(f"{a}{b}")
            except PairNotFoundError:
                try:
                    leg = parse_pair(f"{b}{a}")
                except PairNotFoundError:
                    continue
            venues.update(leg.listed_on)
    return sorted(venues)


def exchange_calendar_set(
    pair: Pair, ref: RefCurrency, exchange_calendars: dict[str, ExchangeCalendar]
) -> CalendarSet:
    venues = relevant_venues(pair, ref)
    if not venues:
        raise ValueError(f"No exchange venues relevant for {pair.base}/{pair.quote} (ref={ref!r})")
    members: dict[str, ExchangeCalendar] = {}
    for v in venues:
        if v not in exchange_calendars:
            raise MissingExchangeCalendarError(v)
        members[v] = exchange_calendars[v]
    return CalendarSet(members=members)  # type: ignore[arg-type]


def combine_calendar_sets(*sets: CalendarSet) -> CalendarSet:
    """Union calendar members across sets. Member labels must be unique across
    inputs (RTGS uses currency codes; exchange uses venue codes — they don't
    collide in practice). A date is good iff good in ALL combined members."""
    members: dict[str, object] = {}
    for cs in sets:
        for label, cal in cs.members.items():
            if label in members:
                raise ValueError(f"Duplicate calendar label across sets: {label!r}")
            members[label] = cal
    return CalendarSet(members=members)  # type: ignore[arg-type]
