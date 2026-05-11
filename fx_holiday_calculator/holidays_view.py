from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from fx_holiday_calculator.calendars.exchange import ExchangeCalendar
from fx_holiday_calculator.calendars.national import NationalCalendar
from fx_holiday_calculator.calendars.rtgs import RtgsCalendar
from fx_holiday_calculator.calendars.types import LiquidityFlag, SourceOrigin
from fx_holiday_calculator.conventions.cross import RefCurrency, relevant_venues
from fx_holiday_calculator.pairs import Pair

CalendarMode = Literal["FX", "EXCHANGE", "BOTH"]
HolidayType = Literal["FX_RTGS", "EXCHANGE", "NATIONAL"]


@dataclass(frozen=True)
class HolidayRow:
    date: date
    weekday: str
    type: HolidayType
    calendar: str
    holiday_name: str
    source_url: str
    source_doc_title: str
    source_fetched_at: datetime
    source_origin: SourceOrigin
    is_reference_only: bool
    is_closure: bool = True
    liquidity: LiquidityFlag | None = None


def _daterange(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur = cur + timedelta(days=1)


def _rtgs_rows(
    cals: dict[str, RtgsCalendar],
    selected: set[str] | None,
    start: date,
    end: date,
) -> list[HolidayRow]:
    out: list[HolidayRow] = []
    keys = list(cals.keys()) if selected is None else [c for c in cals if c in selected]
    for c in keys:
        cal = cals[c]
        label = f"{c} ({cal.calendar_name})"
        for d in _daterange(start, end):
            entry = cal.get_holiday(d)
            if entry is None:
                continue
            out.append(
                HolidayRow(
                    date=d,
                    weekday=d.strftime("%a"),
                    type="FX_RTGS",
                    calendar=label,
                    holiday_name=entry.name,
                    source_url=entry.source.url,
                    source_doc_title=entry.source.doc_title,
                    source_fetched_at=entry.source.fetched_at,
                    source_origin=entry.source_origin,
                    is_reference_only=False,
                    is_closure=entry.is_closure,
                    liquidity=entry.liquidity,
                )
            )
    return out


def _exchange_rows(
    cals: dict[str, ExchangeCalendar],
    selected: set[str] | None,
    start: date,
    end: date,
) -> list[HolidayRow]:
    out: list[HolidayRow] = []
    keys = list(cals.keys()) if selected is None else [v for v in cals if v in selected]
    for v in keys:
        cal = cals[v]
        for d in _daterange(start, end):
            entry = cal.get_holiday(d)
            if entry is None:
                continue
            out.append(
                HolidayRow(
                    date=d,
                    weekday=d.strftime("%a"),
                    type="EXCHANGE",
                    calendar=v,
                    holiday_name=entry.name,
                    source_url=entry.source.url,
                    source_doc_title=entry.source.doc_title,
                    source_fetched_at=entry.source.fetched_at,
                    source_origin=entry.source_origin,
                    is_reference_only=False,
                    is_closure=entry.is_closure,
                    liquidity=entry.liquidity,
                )
            )
    return out


def _national_rows(
    cals: dict[str, NationalCalendar],
    start: date,
    end: date,
) -> list[HolidayRow]:
    out: list[HolidayRow] = []
    for code, cal in cals.items():
        for d in _daterange(start, end):
            entry = cal.get_holiday(d)
            if entry is None:
                continue
            out.append(
                HolidayRow(
                    date=d,
                    weekday=d.strftime("%a"),
                    type="NATIONAL",
                    calendar=f"{code} (national, ref)",
                    holiday_name=entry.name,
                    source_url=entry.source.url,
                    source_doc_title=entry.source.doc_title,
                    source_fetched_at=entry.source.fetched_at,
                    source_origin=entry.source_origin,
                    is_reference_only=True,
                )
            )
    return out


def _auto_rtgs_scope(pair: Pair, ref_currency: RefCurrency) -> set[str]:
    needed = {pair.base, pair.quote}
    if ref_currency != "none":
        needed.add(ref_currency)
    return needed


def list_holidays(
    *,
    pair: Pair,
    ref_currency: RefCurrency,
    start: date,
    end: date,
    calendar_mode: CalendarMode = "BOTH",
    include_national: bool = False,
    selected_venues: set[str] | None = None,
    selected_rtgs: set[str] | None = None,
    rtgs_calendars: dict[str, RtgsCalendar],
    exchange_calendars: dict[str, ExchangeCalendar],
    national_calendars: dict[str, NationalCalendar] | None = None,
) -> list[HolidayRow]:
    rows: list[HolidayRow] = []
    if calendar_mode in {"FX", "BOTH"}:
        rtgs_scope = (
            _auto_rtgs_scope(pair, ref_currency) if selected_rtgs is None else selected_rtgs
        )
        rows += _rtgs_rows(rtgs_calendars, rtgs_scope, start, end)
    if calendar_mode in {"EXCHANGE", "BOTH"}:
        if selected_venues is None:
            allowed = set(relevant_venues(pair, ref_currency))
        else:
            allowed = selected_venues
        rows += _exchange_rows(exchange_calendars, allowed, start, end)
    if include_national and national_calendars:
        rows += _national_rows(national_calendars, start, end)
    return sorted(rows, key=lambda r: (r.date, r.type, r.calendar))
