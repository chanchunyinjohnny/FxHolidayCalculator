from dataclasses import dataclass
from datetime import date

from fx_holiday_calculator.calendars.types import HolidayEntry


@dataclass
class ExchangeCalendar:
    venue: str
    products: tuple[str, ...]
    entries_by_date: dict[date, HolidayEntry]

    def is_holiday(self, d: date) -> bool:
        return d in self.entries_by_date

    def get_holiday(self, d: date) -> HolidayEntry | None:
        return self.entries_by_date.get(d)
