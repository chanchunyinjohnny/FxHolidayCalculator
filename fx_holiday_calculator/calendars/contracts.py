"""Listed-FX-futures contract calendar.

A per-venue collection of `ContractEntry` rows, parallel to `ExchangeCalendar`
(which carries venue holidays). Each row carries a `derivation_mode` flag —
scrape / derived / manual — that the UI surfaces so the user can tell at a
glance whether a date was pulled from the venue's official publication, fell
back to the venue's documented rule, or was curated by a maintainer.
"""

from dataclasses import dataclass
from datetime import date

from fx_holiday_calculator.calendars.types import ContractEntry, OptionContractEntry


def _pair_keys(p: str) -> set[str]:
    """Pair direction is a venue-specific convention and is not load-bearing
    for the lookup. Return both `BASE/QUOTE` and the reversed form so callers
    that pass either orientation will match."""
    parts = p.upper().replace(" ", "").split("/")
    if len(parts) != 2:
        return {p.upper()}
    a, b = parts
    return {f"{a}/{b}", f"{b}/{a}"}


@dataclass
class ContractCalendar:
    venue: str
    entries: tuple[ContractEntry, ...]
    # True iff the file's `default_source.default_derivation_mode == "derived"`
    # (i.e. the most recent fetch fell through to the venue rule for at least
    # the default). The UI uses this for a top-of-tab banner.
    default_derivation_mode_is_derived: bool = False

    def get(self, code: str) -> ContractEntry | None:
        c = code.upper()
        for e in self.entries:
            if e.code.upper() == c:
                return e
        return None

    def has_derived_rows(self) -> bool:
        return any(e.derivation_mode == "derived" for e in self.entries)

    def iter_listing(
        self,
        *,
        pair: str | None = None,
        asof: date | None = None,
        include_expired: bool = False,
    ) -> list[ContractEntry]:
        wanted_pair_keys = _pair_keys(pair) if pair else None
        out: list[ContractEntry] = []
        for e in self.entries:
            if wanted_pair_keys is not None and e.pair.upper() not in wanted_pair_keys:
                continue
            if not include_expired and asof is not None and e.last_trading_day < asof:
                continue
            out.append(e)
        # Sort chronologically by last trading day; ties broken by code so the
        # ordering is stable regardless of JSON insertion order.
        out.sort(key=lambda e: (e.last_trading_day, e.code))
        return out


@dataclass
class OptionsContractCalendar:
    """Per-venue collection of `OptionContractEntry` rows. Parallels
    `ContractCalendar` for listed-option contracts. Field names match
    option-native vocabulary (expiry / delivery) rather than the
    futures-native LTD / settlement."""

    venue: str
    entries: tuple[OptionContractEntry, ...]
    default_derivation_mode_is_derived: bool = False

    def get(self, code: str) -> OptionContractEntry | None:
        c = code.upper()
        for e in self.entries:
            if e.code.upper() == c:
                return e
        return None

    def has_derived_rows(self) -> bool:
        return any(e.derivation_mode == "derived" for e in self.entries)

    def iter_listing(
        self,
        *,
        pair: str | None = None,
        asof: date | None = None,
        include_expired: bool = False,
    ) -> list[OptionContractEntry]:
        wanted_pair_keys = _pair_keys(pair) if pair else None
        out: list[OptionContractEntry] = []
        for e in self.entries:
            if wanted_pair_keys is not None and e.pair.upper() not in wanted_pair_keys:
                continue
            if not include_expired and asof is not None and e.expiry_date < asof:
                continue
            out.append(e)
        out.sort(key=lambda e: (e.expiry_date, e.code))
        return out
