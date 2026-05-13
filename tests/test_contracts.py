from datetime import date, datetime, timezone

from fx_holiday_calculator.calendars.contracts import ContractCalendar
from fx_holiday_calculator.calendars.types import ContractEntry, SourceRef


def _src(fetcher: str = "scripts/sources/cme_contracts.py@v1") -> SourceRef:
    return SourceRef(
        url="https://example.test/specs",
        doc_title="Test contract specs",
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        fetcher=fetcher,
    )


def _entry(
    code: str,
    pair: str = "EUR/USD",
    ltd: date = date(2026, 6, 15),
    settle: date = date(2026, 6, 17),
    mode: str = "scrape",
) -> ContractEntry:
    return ContractEntry(
        venue="CME",
        code=code,
        pair=pair,
        product_name="Euro FX Futures",
        contract_month=f"{ltd.year}-{ltd.month:02d}",
        last_trading_day=ltd,
        settlement_date=settle,
        first_notice_day=None,
        derivation_mode=mode,  # type: ignore[arg-type]
        source=_src(),
        source_origin="bundled",
        note=None,
    )


def test_get_returns_entry_by_code_case_insensitive():
    cal = ContractCalendar(venue="CME", entries=(_entry("6EM6"),))
    assert cal.get("6EM6").settlement_date == date(2026, 6, 17)
    assert cal.get("6em6").settlement_date == date(2026, 6, 17)
    assert cal.get("MISSING") is None


def test_iter_listing_hides_expired_by_default():
    asof = date(2026, 7, 1)
    cal = ContractCalendar(
        venue="CME",
        entries=(
            _entry("6EM6", ltd=date(2026, 6, 15)),  # expired vs asof
            _entry("6EU6", ltd=date(2026, 9, 14)),  # live
        ),
    )
    live = cal.iter_listing(asof=asof)
    assert [e.code for e in live] == ["6EU6"]
    with_expired = cal.iter_listing(asof=asof, include_expired=True)
    assert [e.code for e in with_expired] == ["6EM6", "6EU6"]


def test_iter_listing_pair_filter_is_direction_agnostic():
    cal = ContractCalendar(
        venue="SGX",
        entries=(
            _entry("UCM6", pair="USD/CNH", ltd=date(2026, 6, 29)),
            _entry("EUR6", pair="EUR/USD", ltd=date(2026, 6, 15)),
        ),
    )
    # Stored as USD/CNH; query as CNH/USD must still match.
    found = cal.iter_listing(pair="CNH/USD", include_expired=True)
    assert [e.code for e in found] == ["UCM6"]
    # Stored as EUR/USD; query as USD/EUR must still match.
    found2 = cal.iter_listing(pair="USD/EUR", include_expired=True)
    assert [e.code for e in found2] == ["EUR6"]


def test_has_derived_rows_and_default_flag():
    cal = ContractCalendar(
        venue="CME",
        entries=(
            _entry("6EM6", mode="scrape"),
            _entry("6EU6", mode="derived", ltd=date(2026, 9, 14)),
        ),
        default_derivation_mode_is_derived=False,
    )
    assert cal.has_derived_rows() is True
    assert cal.default_derivation_mode_is_derived is False


def test_iter_listing_sorted_by_ltd_then_code():
    cal = ContractCalendar(
        venue="CME",
        entries=(
            _entry("BBB", ltd=date(2026, 9, 14)),
            _entry("AAA", ltd=date(2026, 6, 15)),
            _entry("AAB", ltd=date(2026, 6, 15)),
        ),
    )
    out = cal.iter_listing(include_expired=True)
    assert [e.code for e in out] == ["AAA", "AAB", "BBB"]
