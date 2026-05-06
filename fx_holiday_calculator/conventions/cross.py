from typing import Literal

from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.conventions.business_day import CalendarSet
from fx_holiday_calculator.pairs import Pair, PairNotFoundError, parse_pair

RefCurrency = Literal["none", "USD", "EUR", "HKD", "CNH"]


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
