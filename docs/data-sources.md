# Data sources

Authoritative registry of every holiday data source used by FX Holiday Calculator. This is the project's most important document: it defines, for each calendar, where the data comes from, how the fetcher reads it, and which quirks to be aware of.

Every JSON entry under `data/fx_rtgs/` and `data/fx_exchange/` is generated from one of the sources below. National (public) holidays are sourced from `python-holidays` at runtime and are reference-only — they are listed at the bottom for completeness.

## Contents

**FX-RTGS calendars**
- [USD — Fedwire](#usd--fedwire)
- [EUR — TARGET2](#eur--target2)
- [GBP — CHAPS](#gbp--chaps)
- [JPY — BoJ-NET](#jpy--bojnet)
- [HKD — CHATS](#hkd--chats)
- [CNH — CNY clearing in Hong Kong](#cnh--cny-clearing-in-hong-kong)
- [CHF — SIC](#chf--sic)
- [CAD — Lynx](#cad--lynx)
- [AUD — RITS](#aud--rits)
- [SGD — MEPS+](#sgd--meps)

**FX-listed venues**
- [CME — FX futures](#cme--fx-futures)
- [HKEX — FX futures](#hkex--fx-futures)
- [SGX — FX futures](#sgx--fx-futures)

**Reference-only**
- [National holidays — python-holidays](#national-holidays--pythonholidays)

---

## Schema reminder

Every source produces a JSON file conforming to the schema defined in the design spec (`docs/superpowers/specs/2026-05-06-fx-holiday-calculator-design.md`, §7.1). Each entry resolves to a non-null source URL, document title, and `fetched_at` timestamp; the data-integrity test enforces this at CI time.

A fetcher must:
1. Read the upstream document at the URL given below.
2. Persist the raw upstream document to `data/<kind>/_raw/<file>.<ext>` so `git diff` can show what the source said at fetch time.
3. Produce a JSON file at `data/<kind>/<file>.json` matching the schema.
4. Stamp `fetched_at` with current UTC and `fetcher` with `scripts/sources/<filename>.py@v1`.

---

## USD — Fedwire

**Identity:** Federal Reserve System bank holiday schedule. Settlement holidays for USD wire (Fedwire / FedNow). Banks are closed; USD cannot settle.
**Calendar kind:** `RTGS`
**File:** `data/fx_rtgs/USD.json`
**Fetcher:** `scripts/sources/federal_reserve.py`

**Upstream URL:** `https://www.federalreserve.gov/aboutthefed/k8.htm`
**Document format:** HTML table.
**Update cadence:** The Federal Reserve publishes the next calendar year's schedule in mid-year (typically June). Schedules for the following ~5 years are usually visible.

**Parser strategy:**
- Page contains one primary table; columns are years, rows are holidays.
- Each cell holds either a date (e.g. `January 1`) or a date with an observance footnote (e.g. `*July 4`).
- Footnotes describe substitute observances ("For holidays falling on Saturday, Federal Reserve Banks ... will be open the preceding Friday").
- Resolve cell text + year to ISO `YYYY-MM-DD`.

**Schema mapping:**
- `name` ← table row holiday name; append `(observed)` when the date is the observance date for a weekend holiday.
- `note` ← short text describing why the date differs from the canonical holiday date when applicable (e.g. `"July 4 falls on Saturday; preceding Friday observed"`).

**Known quirks:**
- Substitute-day rule: Saturday holidays are observed on the preceding Friday for system closure; Sunday holidays on the following Monday. The Fed page lists both the official holiday and the observance date.
- New Year's Eve early-close days are NOT system holidays — out of scope (we model full days only).
- Inauguration Day is observed every four years on January 20 only by some Reserve Banks; it is NOT a system-wide closure and must be excluded.

**Cross-check tripwire:** `python-holidays.UnitedStates(categories=("BANK",))` aligns closely with Fedwire. The CI tripwire diffs the fetched JSON against this library output for each year and fails on mismatch (after filtering Inauguration Day).

---

## EUR — TARGET2

**Identity:** Eurosystem TARGET2 / T2 closure days. Settlement holidays for EUR via TARGET2 RTGS.
**Calendar kind:** `RTGS`
**File:** `data/fx_rtgs/EUR.json`
**Fetcher:** `scripts/sources/ecb_target2.py`

**Upstream URL (citation):** `https://www.ecb.europa.eu/paym/target/target2/profuse/calendar/html/index.en.html`
**Document format:** Deterministic rule — no scraping required. The URL is recorded as the official statement of the rule for citation purposes.
**Update cadence:** Permanent rule; ECB has not changed TARGET2 closure days since the system launched. Bumping this fetcher is a deliberate decision when the ECB publishes a rule change.

**Parser strategy:**
- Pure code; no document fetched at runtime.
- For each year in the requested range, generate the six closure days:
  - `January 1` (New Year's Day)
  - Good Friday (computed via `dateutil.easter(year)` minus 2 days)
  - Easter Monday (`dateutil.easter(year)` plus 1 day)
  - `May 1` (Labour Day)
  - `December 25` (Christmas Day)
  - `December 26` (Christmas Holiday)
- TARGET2 is also closed on weekends; weekend closure is universal across all RTGS calendars and not stored as holiday entries.

**Schema mapping:**
- `name` ← canonical name from the rule (e.g. `"Good Friday"`).
- `note` ← `null` for all entries; the citation is in `default_source`.

**Known quirks:**
- The fetcher does NOT scrape the ECB page; it implements the rule directly. The rule is stable and the page can be unreliable. The `default_source.url` cites the page as the public statement of the rule; the `fetcher` field identifies the implementation that encodes it.
- For very long histories, TARGET (the predecessor) had a different rule set. We do not back-fill before TARGET2 launch (Nov 2007).

**Cross-check tripwire:** `python-holidays.financial.ECB` (or equivalent) implements the same rule. The CI tripwire diffs them; any mismatch fails CI and is investigated immediately (could indicate either the library is wrong or our rule encoding has a bug).

---

## GBP — CHAPS

**Identity:** Bank of England bank holidays. CHAPS (sterling RTGS) is closed on these days; GBP cannot settle.
**Calendar kind:** `RTGS`
**File:** `data/fx_rtgs/GBP.json`
**Fetcher:** `scripts/sources/boe_chaps.py`

**Upstream URL:** `https://www.gov.uk/bank-holidays.json`
**Document format:** Native JSON — `{ "england-and-wales": { "events": [{ "title": ..., "date": ..., "notes": ..., "bunting": ... }, ...], "division": "..." }, ... }`.
**Update cadence:** UK government publishes new years incrementally; typically the year ahead is available from late summer.

**Parser strategy:**
- HTTP GET the URL; parse JSON.
- Use the `england-and-wales` division as canonical for CHAPS (BoE is the operator; CHAPS settlement aligns with E&W bank holidays).
- For each event: `date` → ISO date; `title` → name; `notes` → `note` (often `"Substitute day"` for shifted observances).

**Schema mapping:**
- `name` ← `event.title`
- `note` ← `event.notes` if non-empty, else `null`.

**Known quirks:**
- Substitute days: when a bank holiday falls on a weekend the next available weekday becomes a holiday. The JSON lists only the actual closure date (post-substitution), not the original date.
- One-off royal/state holidays (e.g. Coronation, Royal Funeral) appear in the feed and are valid CHAPS closures.
- Scotland and Northern Ireland have separate bank holidays; we do NOT use those for CHAPS settlement (CHAPS aligns with E&W).

**Cross-check tripwire:** `python-holidays.UnitedKingdom(subdiv="ENG")` is approximately right but does not always include royal one-off holidays. The tripwire is informational only for GBP — mismatch flagged but not failing CI.

---

## JPY — BoJ-NET

**Identity:** Bank of Japan business days. BoJ-NET (yen RTGS) is closed on these days; JPY cannot settle.
**Calendar kind:** `RTGS`
**File:** `data/fx_rtgs/JPY.json`
**Fetcher:** `scripts/sources/boj.py`

**Upstream URL:** `https://www.boj.or.jp/en/about/outline/holi.htm` (English) — the canonical English-language schedule from BoJ.
**Document format:** HTML — typically a list/paragraph of dates per year, sometimes a small table.
**Update cadence:** BoJ publishes the upcoming calendar year typically in late autumn.

**Parser strategy:**
- HTML scrape; locate the schedule region; parse date tokens (Japanese date formats may also appear — prefer the English page).
- Holiday names in English where present; otherwise transliterate the Japanese name.

**Schema mapping:**
- `name` ← English holiday name (e.g. `"Coming-of-Age Day"`)
- `note` ← `"Year-end/New-Year holiday"` collective note where BoJ groups Dec 31 / Jan 2-3 as a single block.

**Known quirks:**
- Year-end / New-Year holidays: BoJ closes Dec 31, Jan 2, Jan 3 in addition to the public Jan 1. Each is a separate entry.
- Substitute holidays (振替休日 / *Furikae kyūjitsu*): when a public holiday falls on a Sunday, the following Monday is a holiday.
- Citizens' holidays (国民の休日 / *Kokumin no shukujitsu*): a weekday sandwiched between two public holidays becomes a holiday — appears in some years (notably during Golden Week).
- Imperial succession / abdication caused additional one-off closures in 2019; pattern may recur.

**Cross-check tripwire:** `python-holidays.Japan(categories=("BANK",))` if available; otherwise `python-holidays.Japan` filtered to BoJ-relevant subset. Informational tripwire only because BoJ may differ from public-holiday lists.

---

## HKD — CHATS

**Identity:** HKMA Hong Kong dollar CHATS clearing calendar. HKD CHATS is closed on these days; HKD cannot settle.
**Calendar kind:** `RTGS`
**File:** `data/fx_rtgs/HKD.json`
**Fetcher:** `scripts/sources/hkma_chats_hkd.py`

**Upstream URL (primary):** `https://www.hkma.gov.hk/eng/key-functions/international-financial-centre/infrastructure/clearing-and-settlement-systems/`
**Upstream document(s):** HKMA publishes annual CHATS calendar PDFs linked from the page above. The fetcher must locate the most recent HKD-CHATS calendar PDF (filenames vary by year).
**Document format:** PDF — typically a one-page calendar grid or a list of dates per year.
**Update cadence:** Published in late autumn of the prior year (typically Nov–Dec).

**Parser strategy:**
- Discover the active PDF link from the listing page.
- Download the PDF; extract text via `pdfplumber`.
- Parse listed holiday dates; the PDF generally includes both date and the Hong Kong public-holiday name (English).
- Persist the raw PDF to `data/fx_rtgs/_raw/HKD.pdf`.

**Schema mapping:**
- `name` ← English holiday name as printed in the PDF.
- `note` ← `"observed"` suffix when applicable (e.g. day after Christmas observed when Boxing Day falls on a Sunday).

**Known quirks:**
- HK public holidays vs. HKD CHATS holidays are usually the same set, but typhoon T8+ closures can affect a settlement day mid-day. We model these only when HKMA confirms a full-day CHATS closure (rare).
- Lunar New Year: typically 3 contiguous holidays (LNY day 1–3); the dates shift each year and require the Chinese lunisolar calendar.
- Boxing Day observance: when Christmas falls on Friday and Boxing Day on Saturday, the following Monday becomes a substitute holiday.

**Cross-check tripwire:** `python-holidays.HongKong()` aligns most years but does not always model HKMA's exact CHATS list (especially typhoon adjustments). Tripwire is informational only.

---

## CNH — CNY clearing in Hong Kong

**Identity:** HKMA's offshore CNY (CNH) clearing schedule. Operated under the CNH RTGS clearing arrangement; this is the calendar that determines whether CNH can settle in Hong Kong. Distinct from onshore CNY (mainland CIPS/CNAPS).
**Calendar kind:** `RTGS`
**File:** `data/fx_rtgs/CNH.json`
**Fetcher:** `scripts/sources/hkma_chats_cnh.py`

**Upstream URL (primary):** `https://www.hkma.gov.hk/eng/key-functions/international-financial-centre/infrastructure/clearing-and-settlement-systems/` (same listing page as HKD CHATS, separate PDF)
**Upstream document(s):** HKMA publishes the annual CNY-clearing-in-HK holiday schedule as a separate PDF, distinct from the HKD-CHATS PDF.
**Document format:** PDF.
**Update cadence:** Published in late autumn of the prior year.

**Parser strategy:**
- Discover the CNY-clearing PDF (named distinct from HKD CHATS — verify at implementation time).
- Download; extract text via `pdfplumber`.
- Parse listed holidays; the schedule is the union of HK public holidays and selected mainland China holidays (because CNY in HK is settled via the HK clearing bank, but PBoC mainland closures still affect liquidity).

**Schema mapping:**
- `name` ← English holiday name (e.g. `"National Day (China)"`, `"Labour Day (China)"`).
- `note` ← `"China public holiday — onshore market closure affects offshore clearing"` for entries that exist due to mainland PRC holidays, else `null`.

**Known quirks:**
- CNH calendar is the **union** of HK and PRC closures — both holiday sets close offshore CNH clearing.
- Mainland China holidays: Spring Festival (Lunar New Year) is typically a 7-day block; Labour Day (May 1) is typically 3–5 days; National Day (Oct 1) is typically 7 days. Exact dates published by State Council each year, usually December.
- Working-Saturdays: PRC sometimes designates a Saturday as a make-up working day adjacent to a holiday block. These do NOT make CNH settle on that Saturday — RTGS still observes weekend closure regardless.
- Typhoon T8+ closures: same caveat as HKD.

**Cross-check tripwire:** No clean library equivalent. `python-holidays.HongKong()` UNION `python-holidays.China()` is a reasonable approximation; tripwire is informational only and a mismatch produces a comment, not a failure.

---

## CHF — SIC

**Identity:** Swiss Interbank Clearing system (SIC) holidays, operated under the Swiss National Bank. CHF cannot settle on these days.
**Calendar kind:** `RTGS`
**File:** `data/fx_rtgs/CHF.json`
**Fetcher:** `scripts/sources/snb_sic.py`

**Upstream URL:** `https://www.six-group.com/en/products-services/banking-services/sic-euroSIC.html` — SIX Interbank Clearing operates SIC under SNB mandate; the calendar is published on the SIX site.
**Document format:** HTML page with embedded calendar; sometimes a downloadable PDF link.
**Update cadence:** Annual publication, typically late in the prior year.

**Parser strategy:**
- HTML scrape; locate the SIC holiday section.
- Anchor on the heading "SIC holidays" or equivalent; parse the year-grouped list of dates.
- If an embedded PDF is the canonical artifact, prefer that and parse via `pdfplumber`.

**Schema mapping:**
- `name` ← holiday name in English (e.g. `"Berchtoldstag"`, `"Ascension Day"`).
- `note` ← `null`.

**Known quirks:**
- Switzerland uses a national SIC calendar; canton-specific holidays (e.g. Genfer Bettag) are NOT SIC closures.
- Berchtoldstag (Jan 2) is a SIC closure even though it is not a federal holiday.
- May 1 (Labour Day) is observed by SIC even though it is a cantonal holiday only.

**Cross-check tripwire:** `python-holidays.Switzerland()` produces national + cantonal holidays; not a clean match for SIC. Tripwire informational only.

---

## CAD — Lynx

**Identity:** Payments Canada Lynx system holidays (replacing the legacy LVTS in 2021). CAD wholesale payments cannot settle on these days.
**Calendar kind:** `RTGS`
**File:** `data/fx_rtgs/CAD.json`
**Fetcher:** `scripts/sources/payments_canada_lynx.py`

**Upstream URL:** `https://www.payments.ca/our-systems/lynx` — operator page; calendar is typically a sub-page or a published PDF.
**Document format:** HTML or PDF — verify at implementation time.
**Update cadence:** Annual, late prior year.

**Parser strategy:**
- Fetch the holiday list from Payments Canada's published calendar.
- Lynx typically aligns with Bank of Canada / federal statutory holidays plus a few additional industry closures.

**Schema mapping:**
- `name` ← English holiday name.
- `note` ← `null` unless an observance day is listed separately.

**Known quirks:**
- Federal holidays only — provincial holidays (e.g. Civic Holiday in some provinces, Saint-Jean-Baptiste in Quebec) are NOT Lynx closures unless adopted nationally.
- Boxing Day (Dec 26) is a Lynx closure even though it is not a federal statutory holiday in all provinces.
- Family Day (third Monday of February) — confirm whether Lynx observes it; most banks do, but the source document is authoritative.

**Cross-check tripwire:** `python-holidays.Canada(subdiv="ON")` (Ontario, where most Canadian banking infrastructure sits) is the closest off-the-shelf approximation. Informational only.

---

## AUD — RITS

**Identity:** Reserve Bank of Australia's Reserve Bank Information and Transfer System (RITS) holidays. AUD wholesale settlement.
**Calendar kind:** `RTGS`
**File:** `data/fx_rtgs/AUD.json`
**Fetcher:** `scripts/sources/rba_rits.py`

**Upstream URL:** `https://www.rba.gov.au/payments-and-infrastructure/rits/calendar.html`
**Document format:** HTML page with a per-year holiday table.
**Update cadence:** Annual, published in late prior year.

**Parser strategy:**
- HTML scrape; the page typically has a table with columns `Date | Day | Holiday`.
- One row per holiday; parse all years currently displayed.

**Schema mapping:**
- `name` ← `Holiday` cell.
- `note` ← `"Sydney public holiday"` or `"national"` if the table distinguishes; otherwise `null`.

**Known quirks:**
- ANZAC Day (Apr 25) and other public holidays observed nationally by RITS.
- RITS observes NSW public holidays for cross-state operations (RITS sits in Sydney). Other state holidays (e.g. Melbourne Cup) are NOT RITS closures unless RBA explicitly lists them.
- "Substitute day" rule: when a holiday falls on a weekend the next Monday is observed.

**Cross-check tripwire:** `python-holidays.Australia(subdiv="NSW")` plus filtering for national-only. Informational tripwire.

---

## SGD — MEPS+

**Identity:** Monetary Authority of Singapore's MAS Electronic Payment System Plus (MEPS+). SGD wholesale settlement.
**Calendar kind:** `RTGS`
**File:** `data/fx_rtgs/SGD.json`
**Fetcher:** `scripts/sources/mas_meps.py`

**Upstream URL:** `https://www.mas.gov.sg/-/media/MAS-Media-Library/regulation/payment/MEPS-Plus-Operating-Calendar.pdf` (path may change — verify at implementation time; canonical landing page is the MAS payments section).
**Document format:** PDF (typical) or HTML annexe.
**Update cadence:** Annual.

**Parser strategy:**
- Locate the active MEPS+ operating calendar document on MAS's payments pages.
- Download and extract; persist the raw PDF.
- Parse holiday list — typically aligns with Singapore public holidays.

**Schema mapping:**
- `name` ← English holiday name.
- `note` ← `null` typically.

**Known quirks:**
- Singapore public holidays cover Hari Raya Puasa, Hari Raya Haji, Vesak Day — these are computed lunisolar/Islamic-calendar dates and depend on official sightings; MAS publishes confirmed dates.
- Substitute Monday rule: weekend public holiday → observed Monday.

**Cross-check tripwire:** `python-holidays.Singapore()` matches most years. Informational tripwire.

---

## Exchange calendars — hybrid strategy and caveats

Unlike the FX-RTGS calendars above (each driven by a single authoritative
upstream document), the v1 exchange calendars use a **hybrid strategy**:

1. **Library floor.** `scripts/sources/library_exchange.py` reads the
   open-source [`exchange_calendars`](https://pypi.org/project/exchange-calendars/)
   package and emits `data/fx_exchange/{SGX,HKEX,CME}.json` with provenance
   pointing to that library. This is the default v1 data source.
2. **Primary-source overrides (future).** When a venue-specific fetcher
   under `scripts/sources/<venue>_fx.py` is added, it writes a JSON with
   `fetcher` field pointing to itself. The loader detects this (the
   `library_sourced` flag is `False`) and that file becomes authoritative;
   the library generator will not overwrite it (`fetch()` guards against
   that).

### Why hybrid, not primary-source-only

The original design (HTML-scrape each venue's holiday page) ran into the
following at implementation time:

- **SGX** rearchitected the trading-and-clearing-hours page into a JavaScript
  SPA — the static HTML is an empty shell. The PDF SGX publishes at
  [api2.sgx.com/sites/default/files/.../SGX Calendar 2026_2.pdf](https://api2.sgx.com/sites/default/files/2026-01/SGX%20Calendar%202026_2.pdf)
  is a per-product calendar (each day lists product codes closed that day,
  e.g. "GIN, GINB, AJ, UC, UCO, …"); there is no single "venue is closed
  today" signal, only per-product information.
- **HKEX** holiday page returns a JS-rendered shell similar to SGX.
- **CME** master holiday calendar is an interactive HTML widget; the
  underlying data is loaded via XHR.

Plain-HTTP scraping (the only path available under the BOCHK runtime
constraints — no Playwright, no headless browser) cannot reach the holiday
data on any of these venues. The hybrid strategy ships working v1 data via
the library while leaving the door open for primary-source fetchers as
they become viable (PDF parsing for SGX, ICS feed if discovered, manual
curation for ad-hoc events like HKEX typhoon notices).

### ⚠ Caveats that the UI surfaces to users

Library-sourced exchange calendars are an **equity-session approximation**
of FX-futures holidays. The UI shows a banner whenever
`library_sourced=True`; the substance:

1. **Equity ≠ FX-futures.** `exchange_calendars` encodes each venue's
   equity session. The data for CME (`CMES` calendar) contains only **3**
   closed weekdays in 2026 — New Year's Day, Good Friday, Christmas Day.
   CME Globex FX futures additionally observe US bank holidays (MLK Day,
   Presidents Day, Memorial Day, Independence Day, Labor Day, Thanksgiving,
   day-after-Thanksgiving early close) that the library does **not**
   include. A trader checking "is my USD/EUR future open on Memorial Day"
   would get a wrong answer from the library data.
2. **Per-product nature.** Exchange holidays are observed per-product, not
   per-venue. SGX's published 2026 calendar lists ~50 dates where *some*
   product is closed, against ~10 that close the entire venue. The library
   returns one calendar per venue, which corresponds roughly to the
   full-venue-closure set — the most conservative subset, which omits
   product-specific observances like SGX USD/INR closing for Indian
   public holidays.
3. **Coverage-horizon lag.** `exchange_calendars` hard-codes lunar/Islamic
   dates (Chinese New Year, Hari Raya, Deepavali) in Python source. New
   years are added by community PRs, typically months after the venue
   publishes its calendar. As of `exchange_calendars` 4.13.x:
   - SGX (`XSES`): coverage through **2026-12-31**.
   - HKEX (`XHKG`): coverage through **2027-05-11**.
   - CME (`CMES`): coverage through **2027-05-11**.
   Beyond those dates, `CalendarRangeError` fires with the window in the
   message — no silent fallthrough.

### Loader precedence (hybrid runtime)

`load_exchange_calendar(venue)`:

1. Cache (`~/.fx_holiday_calculator/cache/fx_exchange/<VENUE>.json`) if present.
2. Bundled (`data/fx_exchange/<VENUE>.json`) — committed to the repo.

Both paths share the same schema (v3). The `library_sourced` attribute on
the loaded calendar is `True` when the file's `default_source.fetcher`
contains `library_exchange`. The UI uses this to decide whether to show
the caveat banner. When a venue eventually gets a primary-source fetcher,
the JSON it writes will not match that pattern and the banner disappears
for that venue.

---

## CME — FX futures

**Current source (v1):** `scripts/sources/library_exchange.py@v1` via
`exchange_calendars.CMES`. Library-sourced — banner shown in UI. Coverage
through 2027-05-11. Equity-session calendar; **does not include US bank
holidays observed by Globex FX futures**.

**Future primary source (planned):** CME Group's master holiday calendar
at `https://www.cmegroup.com/tools-information/holiday-calendar.html` —
HTML page with interactive product-filter widget. Plain-HTTP scraping is
hostile (data loads via XHR); future implementation may require a
manually-curated CSV from CME's downloadable calendar export.

**Identity:** Affects FX futures trading sessions and delivery dates on
CME Globex (USD majors, EUR/JPY, USD/CNH, USD/MXN, USD/BRL, USD/ZAR, etc.).
**Calendar kind:** `EXCHANGE`
**File:** `data/fx_exchange/CME.json`
**Products covered:** Enumerated in the JSON's `products` field.

**Known quirks (will matter when a primary fetcher is built):**
- US federal holidays observed; international holidays are NOT CME closures.
- Day-after-Thanksgiving is typically an early-close day.
- FX delivery happens via CLS for most pairs; CME-specific delivery dates
  fall on the third Wednesday of contract months and are subject to
  mod-following adjustment against the FX-RTGS calendar union (engine logic).

---

## HKEX — FX futures

**Current source (v1):** `scripts/sources/library_exchange.py@v1` via
`exchange_calendars.XHKG`. Library-sourced — banner shown in UI. Coverage
through 2027-05-11. Equity-session calendar; **does not include
typhoon T8+ ad-hoc closures or all derivative-product-specific dates**.

**Future primary source (planned):** HKEX holiday schedule at
`https://www.hkex.com.hk/Services/Trading-hours-and-Severe-Weather-Arrangements/Trading-Hours/Holiday-Schedule?sc_lang=en`.
JS-rendered SPA. Future implementation may parse HKEX's downloadable
calendar PDF or use HKEX's circulars feed for ad-hoc notices.

**Identity:** Covers USD/CNH, Mini USD/CNH, EUR/CNH, JPY/CNH, AUD/CNH, USD/HKD futures.
**Calendar kind:** `EXCHANGE`
**File:** `data/fx_exchange/HKEX.json`

**Known quirks (will matter when a primary fetcher is built):**
- Lunar New Year: typically 3 holiday days for HKEX (vs 1-2 for SGX).
- Christmas Eve / New Year's Eve: half-day for cash equities; full closures
  for some derivatives products. Library data does not distinguish.
- Typhoon T8+ ad-hoc closures: HKEX issues mid-day notices. These will
  require per-entry `source` overrides pointing to the specific HKEX
  notice URL, with `fetcher: "manual"`.

---

## SGX — FX futures

**Current source (v1):** `scripts/sources/library_exchange.py@v1` via
`exchange_calendars.XSES`. Library-sourced — banner shown in UI. Coverage
through 2026-12-31. Equity-session calendar; **does not include
per-product Indian / Korean / Japanese holidays observed by SGX FX-INR,
KRW/USD, JPY/SGD respectively**.

**Future primary source (planned):** SGX publishes an annual derivatives
calendar PDF (e.g. [SGX Calendar 2026_2.pdf](https://api2.sgx.com/sites/default/files/2026-01/SGX%20Calendar%202026_2.pdf)
via [www.sgx.com/trading-0](https://www.sgx.com/trading-0)). The PDF is
per-product: each day lists product codes closed that day, with full-venue
holidays shown as named caps headers (NEW YEAR'S DAY, CHINESE NEW YEAR,
etc.). A primary-source fetcher would `pdfplumber`-parse the named headers
to extract full-venue closures (the conservative subset that aligns with
what an FX user typically needs).

**Identity:** Covers USD/CNH, USD/INR, KRW/USD, JPY/SGD, EUR/USD, GBP/USD,
AUD/USD futures.
**Calendar kind:** `EXCHANGE`
**File:** `data/fx_exchange/SGX.json`

**Known quirks (will matter when a primary fetcher is built):**
- SGX observes Singapore public holidays plus selected international ones.
- Lunar New Year: 1-2 day closure on SG calendar (vs 3+ on HKEX).
- SGX FX-INR adds Indian holidays; FX-KRW adds Korean. We model the
  **base SGX (full-venue) schedule**; per-product augmentations are out
  of scope until a primary-source fetcher with product-code awareness ships.

---

## National holidays — python-holidays

**Identity:** National (public) holidays for reference display only. Never drives any calculation in this tool.
**Calendar kind:** `NATIONAL` (display-only)
**File:** none — sourced at runtime from the `python-holidays` library.

**Upstream:** `python-holidays` package (https://pypi.org/project/holidays/) — pinned to an exact version in `pyproject.toml`. Bumping the pinned version is a deliberate PR.

**Parser strategy:**
- At application startup, the `NationalCalendar` adapter calls `holidays.country_holidays(<code>)` for each country code corresponding to in-scope currencies (US, EU member states relevant to ECB, GB, JP, HK, CN, CH, CA, AU, SG).
- Resulting dates are exposed to the holidays-view code path with `is_reference_only=True`.

**Schema mapping (`HolidayRow` for national entries):**
- `source_url` ← `"https://pypi.org/project/holidays/"`
- `source_doc_title` ← `"python-holidays v<exact-version>, calendar=<country-code>"` — exact version read at import time
- `source_fetched_at` ← library load timestamp
- `source_origin` ← `"library"`
- `is_reference_only` ← `True`

**Known quirks:**
- The library's coverage of substitute days, regional holidays, and lunisolar dates varies by country. National holidays are intentionally non-authoritative in this tool; use the FX-RTGS or Exchange entries for any double-check workflow.

**Cross-check tripwire:** Not applicable — this IS the library; there is nothing to cross-check against.

---

## Maintenance contract

When adding a new source:
1. Add a section to this document describing identity, URL, document format, parser strategy, schema mapping, and known quirks — the same shape as the entries above.
2. Implement the fetcher under `scripts/sources/<name>.py` with the contract defined in the design spec §7.3.
3. Add a recorded fixture under `tests/fixtures/sources/<name>/` (typical-year + edge-case documents).
4. Add the test under `tests/test_fetchers.py`.
5. Add the source to the monthly refresh workflow's source list.
6. If a `python-holidays` calendar exists for cross-checking, register the tripwire rule under the cross-check workflow.

When repairing a fetcher (upstream redesign, parsing breakage):
1. Pull the current upstream document; commit the new raw fixture under `tests/fixtures/sources/<name>/`.
2. Update the parser; the test should fail then pass.
3. Update the parser strategy notes in this document if anchors changed.
4. Increment the fetcher's version tag (`@v2`, `@v3`, ...) so audit trails distinguish parser generations.
