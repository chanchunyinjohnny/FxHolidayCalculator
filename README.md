# fx-holiday-calculator

A Streamlit tool for double-checking FX swap dates and per-pair holiday
calendars, with primary-source provenance for every date returned.

**Try it now:** <https://fx-holiday-calculator.streamlit.app/>

- **FX swap date calculator** — Standard swap (one tenor) and Forward-forward
  (two tenors). Spot, ON, TN, SN, nD/nW/nM/nY, IMM1..IMM4, broken-date.
- **Holiday calendar** — FX-RTGS holidays for any supported currency pair,
  with optional reference-currency calendar union and an optional
  national-holiday reference layer.
- **Provenance contract** — every holiday returned is paired with the URL of
  the official document it was sourced from and the timestamp it was fetched
  at. There are no unsourced dates.

## Run locally

The hosted app at <https://fx-holiday-calculator.streamlit.app/> is the
easiest way to try the tool. To run your own copy:

```bash
pip install -e .
streamlit run run_ui.py
```

Then open the displayed local URL in a browser.

### Optional: refresh SGX / HKEX / CME exchange calendars

The library-sourced exchange-calendar refresh pulls dates from the optional
[`exchange_calendars`](https://pypi.org/project/exchange-calendars/) package.
Bundled data in `data/fx_exchange/*.json` loads without it; only on-demand
refresh of those three venues requires it.

```bash
pip install -e ".[extras]"
```

The `extras` group is separate from the project's base dependencies because
some deployment environments restrict allowable third-party packages — leave
it uninstalled and the tool still works against bundled data.

## v1 scope

This release ships with primary-source RTGS settlement calendars for
**EUR (TARGET2)**, **USD (Fedwire)**, **GBP (CHAPS)**, **JPY (BoJ-NET)**,
**HKD (CHATS)**, **CNH (offshore CNY clearing in Hong Kong)**, and
**CAD (Lynx)**. Supported currency pairs are any combination of those
seven currencies that is registered in `fx_holiday_calculator/pairs.py`.

Three FX-listed exchange venues ship in **library-sourced** form:
**SGX (XSES)**, **HKEX (XHKG)**, **CME (CMES)** — data is generated from
the open-source [`exchange_calendars`](https://pypi.org/project/exchange-calendars/)
package rather than scraped from venue documents. Read the caveat below
before relying on these for real settlement decisions.

Additional RTGS sources (CHF, AUD, SGD) are deferred — see the About
tab for the current deferred list.

### ⚠ Exchange calendar caveat

Library-sourced exchange calendars are an **equity-session approximation**
of FX-futures holidays. They are useful as a sanity check but they are not
authoritative. Three things to know:

1. **Equity ≠ FX-futures.** The library encodes each venue's equity session.
   CME's equity calendar contains only ~3 closed weekdays per year (NYD,
   Good Friday, Christmas); CME Globex FX futures additionally observe US
   bank holidays (MLK Day, Memorial Day, Independence Day, Labor Day,
   Thanksgiving, etc.) that the library does **not** include.
2. **Exchange holidays are per-product, not per-venue.** A given date may
   close USD/INR futures (Indian holiday) without closing USD/CNH futures
   on the same venue. The library returns a single calendar per venue
   regardless of which FX product you actually trade.
3. **Coverage horizon lags real-world publication.** Lunar/Islamic dates
   are hand-typed into the library; year-ahead dates often appear months
   after the venue publishes them. SGX coverage currently ends 2026-12-31;
   HKEX and CME end 2027-05-11. Beyond those dates the calculator raises a
   clear range error rather than silently returning wrong results.

**For high-stakes decisions, always cross-check against the venue's primary
holiday document.** When a primary-source fetcher is added for a venue, the
loader prefers it automatically — see `docs/data-sources.md`.

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
