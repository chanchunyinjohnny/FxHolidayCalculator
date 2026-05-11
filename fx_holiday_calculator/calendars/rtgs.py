from dataclasses import dataclass
from datetime import date

from fx_holiday_calculator.calendars.types import CalendarRangeError, HolidayEntry


@dataclass
class RtgsCalendar:
    currency: str
    calendar_name: str
    operator: str
    entries_by_date: dict[date, HolidayEntry]
    valid_from: date
    valid_until: date

    def _label(self) -> str:
        return f"{self.currency} ({self.calendar_name})"

    def _check_range(self, d: date) -> None:
        if d < self.valid_from or d > self.valid_until:
            raise CalendarRangeError(self._label(), d, self.valid_from, self.valid_until)

    def is_holiday(self, d: date) -> bool:
        self._check_range(d)
        e = self.entries_by_date.get(d)
        return e is not None and e.is_closure

    def get_holiday(self, d: date) -> HolidayEntry | None:
        self._check_range(d)
        return self.entries_by_date.get(d)
