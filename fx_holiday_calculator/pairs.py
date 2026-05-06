from dataclasses import dataclass


class PairNotFoundError(KeyError):
    pass


@dataclass(frozen=True)
class Pair:
    base: str
    quote: str
    spot_offset_days: int
    listed_on: tuple[str, ...]


_PAIRS: dict[tuple[str, str], Pair] = {}


def _add(base: str, quote: str, *, t: int = 2, listed_on: tuple[str, ...] = ()) -> None:
    _PAIRS[(base, quote)] = Pair(base=base, quote=quote, spot_offset_days=t, listed_on=listed_on)


# G10 majors and crosses (T+2 unless noted)
_add("EUR", "USD", listed_on=("CME",))
_add("GBP", "USD", listed_on=("CME",))
_add("USD", "JPY", listed_on=("CME",))
_add("USD", "CHF", listed_on=("CME",))
_add("AUD", "USD", listed_on=("CME",))
_add("NZD", "USD", listed_on=("CME",))
_add("USD", "CAD", t=1, listed_on=("CME",))    # T+1

# EUR crosses
_add("EUR", "GBP", listed_on=("CME",))
_add("EUR", "JPY", listed_on=("CME",))
_add("EUR", "CHF", listed_on=("CME",))
_add("EUR", "AUD", listed_on=("CME",))
_add("EUR", "CAD", listed_on=("CME",))

# Other crosses
_add("GBP", "JPY", listed_on=("CME",))
_add("AUD", "JPY", listed_on=("CME",))
_add("CAD", "JPY")

# CNH / HKD / SGD pairs
_add("USD", "CNH", listed_on=("CME", "HKEX", "SGX"))
_add("USD", "HKD", listed_on=("HKEX",))
_add("HKD", "CNH", listed_on=("HKEX",))
_add("EUR", "CNH", listed_on=("HKEX",))
_add("JPY", "CNH", listed_on=("HKEX",))
_add("AUD", "CNH", listed_on=("HKEX",))
_add("USD", "SGD", listed_on=("SGX",))
_add("USD", "INR", listed_on=("SGX",))
_add("KRW", "USD", listed_on=("SGX",))


def parse_pair(raw: str) -> Pair:
    if not isinstance(raw, str) or not raw:
        raise PairNotFoundError(f"Empty pair: {raw!r}")
    s = raw.strip().upper().replace("/", "")
    if len(s) != 6:
        raise PairNotFoundError(f"Pair must be 6 letters or BBB/QQQ: {raw!r}")
    base, quote = s[:3], s[3:]
    p = _PAIRS.get((base, quote))
    if p is None:
        raise PairNotFoundError(f"Unsupported pair: {base}/{quote}")
    return p


def list_supported_pairs() -> list[Pair]:
    return sorted(_PAIRS.values(), key=lambda p: (p.base, p.quote))
