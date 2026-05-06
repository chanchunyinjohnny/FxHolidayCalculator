from datetime import date, timedelta

from dateutil.relativedelta import relativedelta


def add_period(d: date, unit: str, n: int) -> date:
    if unit == "D":
        return d + timedelta(days=n)
    if unit == "W":
        return d + timedelta(weeks=n)
    if unit == "M":
        return d + relativedelta(months=n)
    if unit == "Y":
        return d + relativedelta(years=n)
    raise ValueError(f"bad unit: {unit}")


_IMM_MONTHS = (3, 6, 9, 12)


def imm_third_wednesday(year: int, month: int) -> date:
    first = date(year, month, 1)
    offset_to_first_wed = (2 - first.weekday()) % 7
    return first + timedelta(days=offset_to_first_wed + 14)


def next_imm_date(after: date, index: int) -> date:
    """index 1..4: 1=next IMM, 2=2nd-next, etc."""
    candidates: list[date] = []
    year = after.year
    while len(candidates) < index + 4:
        for m in _IMM_MONTHS:
            d = imm_third_wednesday(year, m)
            if d > after:
                candidates.append(d)
        year += 1
    return candidates[index - 1]
