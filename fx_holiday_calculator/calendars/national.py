from dataclasses import dataclass
from datetime import date, datetime, timezone
from importlib.metadata import version

import holidays as _holidays_lib

from fx_holiday_calculator.calendars.types import HolidayEntry, SourceRef

_NATIONAL_URL = "https://pypi.org/project/holidays/"
_LOAD_TIME = datetime.now(timezone.utc)
_LIB_VERSION = version("holidays")


@dataclass
class NationalCalendar:
    country_code: str
    _impl: object  # python-holidays HolidayBase

    def is_holiday(self, d: date) -> bool:
        return d in self._impl  # type: ignore[operator]

    def get_holiday(self, d: date) -> HolidayEntry | None:
        name = self._impl.get(d)  # type: ignore[attr-defined]
        if name is None:
            return None
        src = SourceRef(
            url=_NATIONAL_URL,
            doc_title=f"python-holidays v{_LIB_VERSION}, calendar={self.country_code}",
            fetched_at=_LOAD_TIME,
            fetcher="library",
        )
        return HolidayEntry(
            date=d,
            name=name,
            note=None,
            source=src,
            source_origin="library",
        )


def get_national_calendar(country_code: str) -> NationalCalendar:
    impl = _holidays_lib.country_holidays(country_code)
    return NationalCalendar(country_code=country_code, _impl=impl)
