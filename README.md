# fx-holiday-calculator

A Streamlit tool for double-checking FX swap dates and per-pair holiday
calendars, with primary-source provenance for every date returned.

- **FX swap date calculator** — Standard swap (one tenor) and Forward-forward
  (two tenors). Spot, ON, TN, SN, nD/nW/nM/nY, IMM1..IMM4, broken-date.
- **Holiday calendar** — FX-RTGS holidays for any supported currency pair,
  with optional reference-currency calendar union and an optional
  national-holiday reference layer.
- **Provenance contract** — every holiday returned is paired with the URL of
  the official document it was sourced from and the timestamp it was fetched
  at. There are no unsourced dates.

## Run

```bash
pip install -e .
streamlit run run_ui.py
```

Then open the displayed local URL in a browser.

## v1 scope

This release ships with four RTGS settlement calendars: **EUR (TARGET2)**,
**USD (Fedwire)**, **GBP (CHAPS)**, **JPY (BoJ-NET)**. Supported currency
pairs are the EUR/USD/GBP/JPY combinations.

Additional RTGS sources (HKD, CNH, CHF, CAD, AUD, SGD) and FX-listed venues
(CME, HKEX, SGX) are scaffolded but deferred — their fetcher code is not
yet shipped, pending direct access to the upstream documents.

## Data sources

See `docs/data-sources.md` for the per-source registry — every fetcher's
upstream URL, parser strategy, schema mapping, and known quirks.

Bundled data lives in `data/fx_rtgs/`. To refresh into your user cache
without modifying the package, use the sidebar's "Refresh holiday data"
button or:

```bash
python -m fx_holiday_calculator.refresh
```

## Development

```bash
pip install -e ".[test]"
pytest
flake8 fx_holiday_calculator scripts tests --max-line-length=120
black --check fx_holiday_calculator scripts tests
isort --check fx_holiday_calculator scripts tests
```

All tests run offline. The data-integrity test enforces the provenance
contract on every committed JSON entry.

## License

MIT — see `LICENSE`.

## Support

If you find this tool useful, consider supporting its development:

- [GitHub Sponsors](https://github.com/sponsors/chanchunyinjohnny)
- [Buy Me a Coffee](https://www.buymeacoffee.com/chanchunyinjohnny)
- [Ko-fi](https://ko-fi.com/chanchunyinjohnny)
