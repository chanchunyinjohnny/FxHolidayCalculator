from dataclasses import dataclass, field
from datetime import datetime, timezone


class PairNotFoundError(KeyError):
    pass


@dataclass(frozen=True)
class ConventionSource:
    """Provenance for a per-pair market convention.

    Distinct from `SourceRef` (which is bundled-data provenance) because
    pair conventions are documented market practice, not parsed data.
    """

    url: str
    doc_title: str
    documented_at: datetime  # when this convention was last verified by the project


@dataclass(frozen=True)
class PairConvention:
    """A documented pair-specific convention (e.g. T+1 spot lag,
    split-settlement carve-out). Each entry carries its own source so the
    UI can surface it next to the derived dates."""

    rule: str
    description: str
    source: ConventionSource


# Documented at project creation (v1). Update `documented_at` when the
# project re-verifies the cited source.
_DOC_TIME = datetime(2026, 5, 6, tzinfo=timezone.utc)

# Default reference currency for non-USD cross pairs.
# Per market practice, USD's settlement calendar is consulted as a third
# calendar for crosses where neither leg is USD.
_REF_USD_SOURCE = ConventionSource(
    url="https://www.globalfxc.org/docs/fx_global.pdf",
    doc_title="FX Global Code (July 2021)",
    documented_at=_DOC_TIME,
)

# Per-pair convention entries (T+1 spot lags, split-settlement carve-outs).
_USDCAD_T1 = PairConvention(
    rule="T+1 spot lag",
    description=(
        "USD/CAD spot settles T+1 (not T+2) because NY and Toronto operate "
        "on overlapping clearing windows. Applies to spot only; forwards "
        "still chain off the T+1 spot date."
    ),
    source=ConventionSource(
        url="https://www.cfec.ca/files/conventions.pdf",
        doc_title="Canadian Foreign Exchange Committee — Canadian FX Market Practices",
        documented_at=_DOC_TIME,
    ),
)
_EURUSD_SPLIT_SETTLEMENT = PairConvention(
    rule="Split-settlement on US-only holidays",
    description=(
        "EUR/USD spot is not shifted when only the USD leg is closed "
        "(e.g. US Independence Day): USD cash settles on the next USD "
        "business day while EUR settles on the original spot date. This "
        "exempts EUR/USD spot from the otherwise-standard USD-also rule."
    ),
    source=ConventionSource(
        url="https://www.cls-group.com/products/settlement/cls-settlement/",
        doc_title="CLS Settlement — Currency Operating Hours & Holiday Treatment",
        documented_at=_DOC_TIME,
    ),
)


@dataclass(frozen=True)
class Pair:
    base: str
    quote: str
    spot_offset_days: int
    listed_on: tuple[str, ...]
    ndf: bool = False
    fixing_currency: str | None = None
    # Default reference currency consulted for settlement per market
    # convention. None when the pair has no third-currency rule (e.g.,
    # both legs are USD-eligible or no convention applies).
    default_ref_currency: str | None = None
    ref_currency_source: ConventionSource | None = None
    # Pair-specific convention entries (T+1 lags, split-settlement carve-outs).
    conventions: tuple[PairConvention, ...] = field(default_factory=tuple)


_PAIRS: dict[tuple[str, str], Pair] = {}


def _add(
    base: str,
    quote: str,
    *,
    t: int = 2,
    listed_on: tuple[str, ...] = (),
    ndf: bool = False,
    fixing_currency: str | None = None,
    default_ref_currency: str | None = None,
    ref_currency_source: ConventionSource | None = None,
    conventions: tuple[PairConvention, ...] = (),
) -> None:
    # Default rule: non-USD crosses use USD as reference; pairs where USD
    # is already a leg get no reference (USD's calendar is in by construction).
    if default_ref_currency is None and "USD" not in (base, quote) and not ndf:
        default_ref_currency = "USD"
        ref_currency_source = _REF_USD_SOURCE
    _PAIRS[(base, quote)] = Pair(
        base=base,
        quote=quote,
        spot_offset_days=t,
        listed_on=listed_on,
        ndf=ndf,
        fixing_currency=fixing_currency,
        default_ref_currency=default_ref_currency,
        ref_currency_source=ref_currency_source,
        conventions=conventions,
    )


# G10 majors and crosses (T+2 unless noted)
_add("EUR", "USD", listed_on=("CME",), conventions=(_EURUSD_SPLIT_SETTLEMENT,))
_add("GBP", "USD", listed_on=("CME",))
_add("USD", "JPY", listed_on=("CME",))
_add("USD", "CHF", listed_on=("CME",))
_add("AUD", "USD", listed_on=("CME",))
_add("NZD", "USD", listed_on=("CME",))
_add("USD", "CAD", t=1, listed_on=("CME",), conventions=(_USDCAD_T1,))

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

# NDF pairs (East-Asia). Non-deliverable; USD-settled; fixing on local primary source.
_add("USD", "CNY", t=2, listed_on=(), ndf=True, fixing_currency="CNY")
_add("USD", "KRW", t=2, listed_on=(), ndf=True, fixing_currency="KRW")
_add("USD", "TWD", t=2, listed_on=(), ndf=True, fixing_currency="TWD")


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
