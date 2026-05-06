from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

SourceOrigin = Literal["bundled", "cache", "live", "library"]

LiquidityFlag = Literal["normal", "thin", "halted"]


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
    is_closure: bool = True            # True = real RTGS closure; False = informational only
    liquidity: LiquidityFlag | None = None


@dataclass(frozen=True)
class CalendarStatus:
    is_good: bool
    holiday_name: str | None
    source: SourceRef | None
    source_origin: SourceOrigin | None
    liquidity: LiquidityFlag | None = None     # set even when is_good=True
