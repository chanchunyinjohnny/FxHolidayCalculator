from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

SourceOrigin = Literal["bundled", "cache", "live", "library"]

LiquidityFlag = Literal["normal", "thin", "halted"]

DerivationMode = Literal["scrape", "derived", "manual"]


class CalendarRangeError(LookupError):
    """Raised when a calendar is queried outside its bundled validity window.

    Silent fallthrough (treating an out-of-range date as a non-holiday) would
    make this tool quietly return wrong results, which breaks its core promise.
    Callers must refresh data, narrow the query, or extend coverage.
    """

    def __init__(self, calendar_label: str, queried: date, valid_from: date, valid_until: date):
        self.calendar_label = calendar_label
        self.queried = queried
        self.valid_from = valid_from
        self.valid_until = valid_until
        super().__init__(
            f"{calendar_label}: queried {queried.isoformat()} is outside the bundled "
            f"validity window [{valid_from.isoformat()} .. {valid_until.isoformat()}]. "
            f"Refresh the data or narrow the query range."
        )


@dataclass(frozen=True)
class SourceRef:
    url: str
    doc_title: str
    fetched_at: datetime
    fetcher: str


@dataclass(frozen=True)
class HolidayEntry:
    date: date
    name: str
    note: str | None
    source: SourceRef
    source_origin: SourceOrigin
    is_closure: bool = True  # True = real RTGS closure; False = informational only
    liquidity: LiquidityFlag | None = None


@dataclass(frozen=True)
class CalendarStatus:
    is_good: bool
    holiday_name: str | None
    source: SourceRef | None
    source_origin: SourceOrigin | None
    liquidity: LiquidityFlag | None = None  # set even when is_good=True


@dataclass(frozen=True)
class ContractEntry:
    venue: str
    code: str
    pair: str
    product_name: str
    contract_month: str  # "YYYY-MM"
    last_trading_day: date
    settlement_date: date
    first_notice_day: date | None
    derivation_mode: DerivationMode
    source: SourceRef
    source_origin: SourceOrigin
    note: str | None = None


@dataclass(frozen=True)
class OptionContractEntry:
    venue: str
    code: str
    pair: str
    product_name: str
    contract_month: str  # "YYYY-MM"
    expiry_date: date
    delivery_date: date
    derivation_mode: DerivationMode
    source: SourceRef
    source_origin: SourceOrigin
    note: str | None = None
