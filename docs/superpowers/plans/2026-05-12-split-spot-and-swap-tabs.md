# Split Spot and Swap into separate product tabs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the combined "Spot / Swap" sub-tab with two sibling sub-tabs — "Spot" and "Swap" — so that the Calculator's product taxonomy is consistent with the other product tabs (Forward, NDF, Option, Futures) and a user pricing a pure spot date is not confronted with swap-only controls.

**Architecture:** Pure UI restructuring. The engine layer (`calculate_swap_dates`) already supports a SPOT-only call via an early return at `fx_holiday_calculator/swap.py:156`, so no engine code changes. We add a new `product_spot.py` sub-tab that calls the engine with `far_tenor=SPOT` and renders trade+spot only; we rename `product_spot_swap.py` to `product_swap.py` and strip its spot-only inputs; we update `tab_calculator.py` to register both. Docs and the prior plan's product map are updated to reflect the new tab list.

**Tech Stack:** Streamlit 1.30 (pinned), Python 3.10/3.11, flake8 / black / isort, pytest (no pytest-cov, no ruff). Existing engine modules `fx_holiday_calculator.swap`, `fx_holiday_calculator.tenor`, `fx_holiday_calculator.pairs`.

---

## Scope Check

This is a single subsystem (the Streamlit Calculator tab). No sub-projects needed.

## File Structure

- **Create:** `fx_holiday_calculator/ui/product_spot.py` — new Spot sub-tab. Renders trade date + pair selector + reference-currency picker only; calls `calculate_swap_dates(..., far_tenor=parse_tenor("SPOT"))`; shows trade, spot, spot trace, reasoning, reference status, pair conventions. ~110 lines, mirrors `product_forward.py` shape.
- **Rename:** `fx_holiday_calculator/ui/product_spot_swap.py` → `fx_holiday_calculator/ui/product_swap.py`. Module docstring is rewritten to drop the standalone-spot framing. Hard-block `SPOT` as a far tenor on this tab (with an inline hint pointing to the Spot tab) so users land on the right tab for that use case; ON/TN/SN/forward/FFS unchanged.
- **Modify:** `fx_holiday_calculator/ui/tab_calculator.py` — replace the single "Spot / Swap" entry in `st.tabs([...])` with "Spot" and "Swap" entries (6 sub-tabs total), update the lazy import block.
- **Modify:** `docs/conventions.md` — short note in the tab-map section that Spot is now its own sub-tab.
- **Modify:** `docs/superpowers/specs/2026-05-11-fx-products-ui-engine-design.md` — update the product-tab list to show Spot and Swap as siblings.
- **Modify:** `docs/superpowers/plans/2026-05-11-fx-products-ui-engine.md` — note in the file structure section that `product_spot_swap.py` was split (link this plan).
- **Tests:** `tests/test_ui_smoke.py` (create if absent) — import-smoke test for the new and renamed modules. There are no existing UI-behavior tests; we don't add Streamlit interaction tests here. Engine behavior is already covered by `tests/test_swap.py` and `tests/test_spot_offset.py`.

## Self-Review Notes

- Spec coverage: the user's stated requirement is "Spot and Swap feel like different products; separate the tabs." Tasks 1–3 deliver that. Tasks 4–5 keep docs in sync (per the post-change workflow memory). Task 6 is the regression suite per the same memory.
- No placeholders: every code block is the actual code to paste.
- Type consistency: all module-level constants and helper signatures match the existing `product_forward.py` / `product_spot_swap.py` patterns.

---

## Task 0: Fix Today button vertical alignment in `date_input_with_today`

The Today shortcut button currently renders at the level of the date-input *label* (e.g. "Trade date") rather than the input *box*. The existing spacer `btn_col.write("")` at `fx_holiday_calculator/ui/_widgets.py:34` collapses to ~zero height in Streamlit 1.30, so the button does not get pushed down to the input row. We fix the spacer so the button sits horizontally aligned with the input box.

This is a shared widget — fixing it once corrects every product tab that uses `date_input_with_today` (Spot, Swap, Forward, NDF, Option, Futures).

**Files:**
- Modify: `fx_holiday_calculator/ui/_widgets.py:34`

- [ ] **Step 1: Replace the empty-string spacer**

Old (`_widgets.py:32-35`):

```python
    input_col, btn_col = container.columns([3, 1])
    value = input_col.date_input(label, value=default, key=key)
    btn_col.write("")  # spacer so the button aligns below the label, not with it
    btn_col.button("Today", key=f"{key}__today", on_click=_make_today_setter(key))
```

New:

```python
    input_col, btn_col = container.columns([3, 1])
    value = input_col.date_input(label, value=default, key=key)
    # Streamlit 1.30: an empty `write("")` collapses to ~0px, so the button
    # ends up next to the label. A non-breaking space inside a sized markdown
    # reserves a label-row's worth of height so the button lines up with the
    # input box on the same row.
    btn_col.markdown("<div style='height: 1.85em'>&nbsp;</div>", unsafe_allow_html=True)
    btn_col.button("Today", key=f"{key}__today", on_click=_make_today_setter(key))
```

The `1.85em` value matches the rendered height of a Streamlit 1.30 label row (label text + bottom padding) — verified by manual smoke-test on the Calculator tab.

- [ ] **Step 2: Black/isort/flake8**

Run: `black fx_holiday_calculator/ui/_widgets.py && isort fx_holiday_calculator/ui/_widgets.py && flake8 fx_holiday_calculator/ui/_widgets.py`
Expected: no output.

- [ ] **Step 3: Streamlit 1.30 smoke run (manual)**

Run: `streamlit run fx_holiday_calculator/ui/app.py` and confirm: on the Calculator tab, in any sub-tab that exposes a Trade date, the Today button now sits horizontally aligned with the date-input box (not floating up at the label-row level).

- [ ] **Step 4: Pause for user review**

Do not commit. Surface the diff so the user can eyeball it before proceeding.

---

## Task 1: Create the Spot sub-tab

**Files:**
- Create: `fx_holiday_calculator/ui/product_spot.py`

- [ ] **Step 1: Write the new module**

```python
"""Spot product sub-tab.

A single-date calculator: trade date → spot date, on RTGS settlement
calendars. EOM and tenor projection do not apply at spot — spot is just
T+N business days from the trade date. For two-leg products (swap, FFS,
ON/TN/SN) use the Swap tab.
"""

from pathlib import Path

import streamlit as st

from fx_holiday_calculator.calendars.loader import load_rtgs_calendar
from fx_holiday_calculator.calendars.types import CalendarRangeError
from fx_holiday_calculator.pairs import list_supported_pairs, parse_pair
from fx_holiday_calculator.swap import (
    InvalidTradeDateError,
    calculate_swap_dates,
)
from fx_holiday_calculator.tenor import parse_tenor
from fx_holiday_calculator.ui._widgets import (
    REF_CURRENCY_HELP,
    date_input_with_today,
    render_pair_conventions,
    render_reasoning,
    render_reference_status,
    render_trace,
)

BUNDLED = Path(__file__).resolve().parents[2] / "data"
CACHE = Path.home() / ".fx_holiday_calculator" / "cache"

AVAILABLE_RTGS = {"EUR", "USD", "GBP", "JPY"}


def _available_pair_codes() -> list[str]:
    return [
        f"{p.base}/{p.quote}"
        for p in list_supported_pairs()
        if p.base in AVAILABLE_RTGS and p.quote in AVAILABLE_RTGS
    ]


def render() -> None:
    st.subheader("FX Spot Date Calculator")
    st.caption(
        "Single-date: trade date → spot date on RTGS settlement calendars. "
        "T+N from trade date, where N is the pair's spot offset (e.g. 2 for "
        "EUR/USD, 1 for USD/CAD). For swap / ON / TN / SN / forward / FFS, "
        "use the Swap tab."
    )

    pair_codes = _available_pair_codes()
    if not pair_codes:
        st.warning("No supported pairs available.")
        return

    col1, col2 = st.columns(2)
    default_idx = pair_codes.index("EUR/USD") if "EUR/USD" in pair_codes else 0
    pair_code = col1.selectbox("Currency pair", pair_codes, index=default_idx, key="spot_pair")
    trade_date = date_input_with_today(col2, "Trade date", key="spot_trade_date")

    pair = parse_pair(pair_code)

    leg_ccys = {pair.base, pair.quote}
    pair_default = pair.default_ref_currency
    if pair_default is None or pair_default in leg_ccys:
        ref = "none"
    else:
        ref_options = ["none"]
        for c in (pair_default, "USD", "EUR"):
            if c not in ref_options and c not in leg_ccys:
                ref_options.append(c)
        ref = st.radio(
            f"Reference currency (pair default: {pair_default})",
            ref_options,
            index=ref_options.index(pair_default),
            horizontal=True,
            help=REF_CURRENCY_HELP,
            key="spot_ref",
        )

    needed = {pair.base, pair.quote}
    if ref != "none":
        needed.add(ref)

    try:
        cals = {
            c: load_rtgs_calendar(c, root=BUNDLED / "fx_rtgs", cache_root=CACHE / "fx_rtgs")
            for c in sorted(needed)
        }
    except FileNotFoundError as exc:
        st.error(f"Calendar file missing: {exc}")
        return

    cal_caption = "RTGS: " + " · ".join(f"{c} ({cals[c].calendar_name})" for c in sorted(needed))
    st.caption("Calendars to be used: " + cal_caption)

    if st.button("Calculate", key="spot_calc"):
        try:
            result = calculate_swap_dates(
                trade_date=trade_date,
                pair=pair,
                far_tenor=parse_tenor("SPOT"),
                near_tenor=None,
                ref_currency=ref,  # type: ignore[arg-type]
                calendars=cals,
            )
        except InvalidTradeDateError as exc:
            st.error(f"Invalid input: {exc}")
            return
        except CalendarRangeError as exc:
            st.error(
                f"Calculation lands outside bundled calendar window: {exc} "
                "Refresh the calendar data or pick an earlier trade date."
            )
            return

        if result.warnings:
            st.warning("\n\n".join(f"• {w}" for w in result.warnings))

        st.markdown("### Result")
        st.write(f"**Trade date:** {result.trade_date} ({result.trade_date.strftime('%a')})")
        st.write(f"**Spot date:**  {result.spot_date} ({result.spot_date.strftime('%a')})")

        render_reasoning(result.reasoning)

        st.markdown("### Adjustment trace")
        render_trace(result.spot_trace, "Spot offset")

        render_reference_status(
            pair=pair,
            selected_ref=ref,
            named_traces=[("Spot offset", result.spot_trace)],
        )
        render_pair_conventions(pair)
```

- [ ] **Step 2: Black/isort/flake8 the new file**

Run: `black fx_holiday_calculator/ui/product_spot.py && isort fx_holiday_calculator/ui/product_spot.py && flake8 fx_holiday_calculator/ui/product_spot.py`
Expected: no output (clean).

- [ ] **Step 3: Stop and ask the user to review before commit**

Per user preference (CLAUDE.md): never commit on behalf of the user. Show `git status` / `git diff` and pause for review.

---

## Task 2: Rename product_spot_swap.py to product_swap.py and drop spot-only framing

**Files:**
- Rename: `fx_holiday_calculator/ui/product_spot_swap.py` → `fx_holiday_calculator/ui/product_swap.py`
- Modify: the docstring, subheader, caption, and the SPOT-tenor branch.

- [ ] **Step 1: Rename the file**

```bash
git mv fx_holiday_calculator/ui/product_spot_swap.py fx_holiday_calculator/ui/product_swap.py
```

If the repo is not a git workspace, fall back to plain `mv`.

- [ ] **Step 2: Replace the module docstring**

Old (`product_swap.py` lines 1-8 after rename):

```python
"""Spot / Swap product sub-tab.

Renders the existing engine surface (calculate_swap_dates) under a
product-aware label. Covers spot, cross-spot, ON/TN/SN, forward outright,
standard swap, and forward-forward swap — all rolling on RTGS settlement
calendars. Exchange calendars are not consulted: OTC swap/forward
settlement is bilateral and venue-independent.
"""
```

New:

```python
"""FX Swap product sub-tab.

Covers ON / TN / SN short-dated swaps, standard (single-tenor) swaps,
and forward-forward swaps (two tenors). All legs roll on RTGS settlement
calendars; exchange calendars are not consulted because OTC swap
settlement is bilateral and venue-independent.

Pure spot date calculations live in the Spot tab.
"""
```

- [ ] **Step 3: Update the subheader and caption**

Old (`product_swap.py:60-63`):

```python
    st.subheader("Spot & Swap Date Calculator")
    st.caption(
        "Covers spot, cross-spot, ON/TN/SN, forward outright, standard swap, "
        "and forward-forward swap. All rolling on RTGS settlement calendars."
    )
```

New:

```python
    st.subheader("FX Swap Date Calculator")
    st.caption(
        "Covers ON / TN / SN short-dated swaps, standard (single-tenor) swaps, "
        "and forward-forward swaps. All legs roll on RTGS settlement calendars. "
        "For a pure spot date, use the Spot tab."
    )
```

- [ ] **Step 4: Update the Standard-mode tenor input placeholder/value to drop SPOT**

Old (`product_swap.py:86-90`):

```python
        far_tenor_str = st.text_input(
            "Tenor (e.g. SPOT, ON, 3M, IMM1, 2026-08-15)",
            value="3M",
            key="swap_far_tenor_std",
        )
```

New:

```python
        far_tenor_str = st.text_input(
            "Tenor (e.g. ON, TN, SN, 3M, IMM1, 2026-08-15)",
            value="3M",
            key="swap_far_tenor_std",
        )
```

- [ ] **Step 5: Block SPOT as a far tenor on this tab**

Locate the parse/calculate block (around `product_swap.py:134-145` after rename). Insert a SPOT-tenor guard immediately after `far_tenor = parse_tenor(far_tenor_str)`:

Old:

```python
        try:
            far_tenor = parse_tenor(far_tenor_str)
            near_tenor = parse_tenor(near_tenor_str) if near_tenor_str else None
            result = calculate_swap_dates(
```

New:

```python
        try:
            far_tenor = parse_tenor(far_tenor_str)
            near_tenor = parse_tenor(near_tenor_str) if near_tenor_str else None
            if far_tenor.kind == "SPOT" and near_tenor is None:
                st.info(
                    "SPOT is a single-date product — please use the **Spot** tab. "
                    "The Swap tab is for two-leg products (ON/TN/SN, standard swap, "
                    "forward-forward swap)."
                )
                return
            result = calculate_swap_dates(
```

- [ ] **Step 6: Black/isort/flake8 the renamed file**

Run: `black fx_holiday_calculator/ui/product_swap.py && isort fx_holiday_calculator/ui/product_swap.py && flake8 fx_holiday_calculator/ui/product_swap.py`
Expected: no output.

- [ ] **Step 7: Pause for user review**

Show `git status` and the diff. Wait for user approval before continuing.

---

## Task 3: Wire both tabs into tab_calculator.py

**Files:**
- Modify: `fx_holiday_calculator/ui/tab_calculator.py`

- [ ] **Step 1: Replace the lazy-import block and the tabs list**

Old (`tab_calculator.py:13-32`):

```python
    # Lazy imports so any one sub-tab's import failure doesn't break the others.
    from fx_holiday_calculator.ui import (
        product_forward,
        product_futures,
        product_ndf,
        product_option,
        product_spot_swap,
    )

    sub = st.tabs(["Spot / Swap", "Forward", "NDF", "Option", "Futures"])
    with sub[0]:
        product_spot_swap.render()
    with sub[1]:
        product_forward.render()
    with sub[2]:
        product_ndf.render()
    with sub[3]:
        product_option.render()
    with sub[4]:
        product_futures.render()
```

New:

```python
    # Lazy imports so any one sub-tab's import failure doesn't break the others.
    from fx_holiday_calculator.ui import (
        product_forward,
        product_futures,
        product_ndf,
        product_option,
        product_spot,
        product_swap,
    )

    sub = st.tabs(["Spot", "Swap", "Forward", "NDF", "Option", "Futures"])
    with sub[0]:
        product_spot.render()
    with sub[1]:
        product_swap.render()
    with sub[2]:
        product_forward.render()
    with sub[3]:
        product_ndf.render()
    with sub[4]:
        product_option.render()
    with sub[5]:
        product_futures.render()
```

- [ ] **Step 2: Black/isort/flake8**

Run: `black fx_holiday_calculator/ui/tab_calculator.py && isort fx_holiday_calculator/ui/tab_calculator.py && flake8 fx_holiday_calculator/ui/tab_calculator.py`
Expected: no output.

---

## Task 4: Add an import-smoke test for the UI sub-tabs

**Files:**
- Create: `tests/test_ui_smoke.py` (if it doesn't already exist; if it does, append the test instead)

- [ ] **Step 1: Write the import-smoke test**

```python
"""Smoke test: every product sub-tab module imports cleanly.

Streamlit 1.30 import-time errors (missing attributes, removed APIs)
would otherwise only surface at runtime when a user clicks the tab.
This test catches them at CI time.
"""

import importlib

import pytest

PRODUCT_MODULES = [
    "fx_holiday_calculator.ui.product_spot",
    "fx_holiday_calculator.ui.product_swap",
    "fx_holiday_calculator.ui.product_forward",
    "fx_holiday_calculator.ui.product_ndf",
    "fx_holiday_calculator.ui.product_option",
    "fx_holiday_calculator.ui.product_futures",
    "fx_holiday_calculator.ui.tab_calculator",
]


@pytest.mark.parametrize("mod", PRODUCT_MODULES)
def test_product_module_imports_and_exposes_render(mod):
    m = importlib.import_module(mod)
    assert hasattr(m, "render"), f"{mod} must expose a render() function"


def test_old_combined_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("fx_holiday_calculator.ui.product_spot_swap")
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/test_ui_smoke.py -v`
Expected: all parametrized cases PASS; `test_old_combined_module_is_gone` PASS.

If `test_old_combined_module_is_gone` fails, it means the rename in Task 2 was incomplete (stale `.pyc` in `__pycache__`); clear `__pycache__` and rerun.

---

## Task 5: Update reference docs

**Files:**
- Modify: `docs/conventions.md`
- Modify: `docs/superpowers/specs/2026-05-11-fx-products-ui-engine-design.md`
- Modify: `docs/superpowers/plans/2026-05-11-fx-products-ui-engine.md`

- [ ] **Step 1: Find the product-tab list in `docs/conventions.md` and update it**

Run: `grep -n "Spot / Swap\|Spot/Swap\|product_spot_swap\|sub-tab" docs/conventions.md`
For each hit that references "Spot / Swap" as a single tab, replace with "Spot" and "Swap" as two siblings. Keep wording style consistent with the rest of the doc.

- [ ] **Step 2: Update the design spec's tab list**

Run: `grep -n "Spot / Swap\|product_spot_swap" docs/superpowers/specs/2026-05-11-fx-products-ui-engine-design.md`
Replace any "Spot / Swap" tab name with two entries: "Spot" and "Swap". Add a short note (≤2 sentences) under the Spot entry: pure single-date product, calls `calculate_swap_dates` with `far_tenor=SPOT`; under the Swap entry: two-leg products only (ON/TN/SN, standard swap, FFS).

- [ ] **Step 3: Update the prior implementation plan's file map**

Run: `grep -n "product_spot_swap" docs/superpowers/plans/2026-05-11-fx-products-ui-engine.md`
For each hit, change `product_spot_swap.py` to `product_swap.py` and add a parenthetical: `(spot extracted into product_spot.py — see 2026-05-12-split-spot-and-swap-tabs.md)`.

- [ ] **Step 4: Re-run the doc greps to confirm no stale "Spot / Swap" string remains**

Run: `grep -rn "Spot / Swap\|product_spot_swap" docs/ fx_holiday_calculator/`
Expected: only the new plan file (`2026-05-12-split-spot-and-swap-tabs.md`) and the cross-reference parenthetical from Step 3 may contain those strings; no live code or current spec wording should still reference them.

---

## Task 6: Run the full regression suite

Per the user's post-change-workflow memory: after any change in this project, run the test suite as a regression check before reporting done.

- [ ] **Step 1: Run the lint trio across all changed files**

Run: `black --check fx_holiday_calculator/ tests/ && isort --check-only fx_holiday_calculator/ tests/ && flake8 fx_holiday_calculator/ tests/`
Expected: no diffs from black/isort; flake8 prints nothing.

- [ ] **Step 2: Run the full pytest suite**

Run: `pytest -q`
Expected: all tests pass, including the new `test_ui_smoke.py`. The data-integrity test (`tests/test_data_integrity.py`) must still pass — provenance contract is untouched by this change but verify.

- [ ] **Step 3: Streamlit 1.30 smoke run (manual)**

Run: `streamlit run fx_holiday_calculator/ui/app.py` and visually confirm:
1. The Calculator tab now shows 6 sub-tabs: **Spot**, **Swap**, Forward, NDF, Option, Futures.
2. The Spot sub-tab renders only pair + trade date inputs, and produces a single spot date plus trace.
3. The Swap sub-tab still calculates ON/TN/SN/3M-standard/FFS correctly.
4. Typing `SPOT` as the Swap tab's standard far tenor produces the redirect `st.info` message and does not run a calculation.

UI verification is a manual step — engine behavior is covered by the unit suite, but Streamlit rendering is not.

- [ ] **Step 4: Hand off to user for review and commit**

Per user preference, do not commit. Summarize the changes (new file, renamed file, modified tabs/docs/tests) and let the user commit when ready.
