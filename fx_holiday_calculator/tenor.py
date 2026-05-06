import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

TenorKind = Literal["ON", "TN", "SN", "SPOT", "PERIOD", "IMM", "BROKEN"]
PeriodUnit = Literal["D", "W", "M", "Y"]


class InvalidTenorError(ValueError):
    pass


@dataclass(frozen=True)
class Tenor:
    kind: TenorKind
    period_unit: PeriodUnit | None = None
    period_n: int | None = None
    imm_index: int | None = None
    target_date: date | None = None


_NAMED = {"ON", "TN", "SN", "SPOT"}

_PERIOD_RE = re.compile(r"^(\d+)([DWMY])$")
_IMM_RE = re.compile(r"^IMM([1-4])$")
_BROKEN_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_PERIOD = {"D": 365, "W": 104, "M": 60, "Y": 30}


def parse_tenor(raw: str) -> Tenor:
    if not raw or not isinstance(raw, str):
        raise InvalidTenorError(f"Cannot parse empty/non-string tenor: {raw!r}")
    s = raw.strip().upper()
    if s in _NAMED:
        return Tenor(kind=s)  # type: ignore[arg-type]
    m = _PERIOD_RE.match(s)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if n <= 0 or n > _MAX_PERIOD[unit]:
            raise InvalidTenorError(f"Period out of range: {raw!r}")
        return Tenor(kind="PERIOD", period_unit=unit, period_n=n)  # type: ignore[arg-type]
    m = _IMM_RE.match(s)
    if m:
        return Tenor(kind="IMM", imm_index=int(m.group(1)))
    if _BROKEN_RE.match(s):
        try:
            d = date.fromisoformat(s)
        except ValueError as exc:
            raise InvalidTenorError(f"Invalid broken date: {raw!r}") from exc
        return Tenor(kind="BROKEN", target_date=d)
    raise InvalidTenorError(f"Unrecognised tenor: {raw!r}")
