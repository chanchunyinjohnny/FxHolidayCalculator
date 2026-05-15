# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

FX Holiday Calculator is an open-source Python tool for double-checking FX swap dates and per-pair holiday calendars. The project's defining feature is **explicit data provenance**: every holiday returned by the tool is paired with the URL of the official document it came from.

The tool is consumed via a Streamlit UI (no CLI in v1). The engine is also importable as a Python library.

The project is MIT licensed; the author's name is Chan Chun Yin Johnny. The project must not contain any proprietary or confidential information.

## Reference docs

- Design spec: `docs/superpowers/specs/2026-05-06-fx-holiday-calculator-design.md`
- Sources registry: `docs/data-sources.md` (the most important doc — per-source upstream URLs and parser strategies)
- Implementation plan: `docs/superpowers/plans/2026-05-06-fx-holiday-calculator.md`

## User Preferences

- **Never commit on behalf of the user.** Always let the user review changes before committing. Do not run `git commit` unless explicitly asked.

## Development environment

The project targets two profiles. Treat the **constrained profile** as the default unless the user says otherwise — it has the stricter rules.

### Constrained profile (locked-down corporate env)

- **Python version:** 3.10 / 3.11 only. Not 3.13.
- **Streamlit pinned to 1.30**. Test UI changes against this exact version.
- **No ruff, no pytest-cov.** Use `flake8`, `black`, `isort` for linting.
- Use the provided corporate conda environment to run and test code; do not use a local Python.
- Do not install pip dependencies outside the corporate allow-list. In particular, only the packages listed under `[project] dependencies` and `[project.optional-dependencies] test` in `pyproject.toml` are guaranteed installable.

### Unconstrained profile (personal / open-source use)

- Same Python and Streamlit pins (kept for cross-env parity).
- Additionally, the packages under `[project.optional-dependencies] extras` may be installed. Today that is `exchange_calendars` (used by `scripts/sources/library_exchange.py` to populate SGX / HKEX / CME calendars). Without it, those library-sourced exchange calendars cannot be refreshed live — bundled `data/fx_exchange/*.json` still loads, so engine calculations continue to work.
- Install with: `pip install -e ".[extras]"` (add `test` for the dev toolchain).

## Streamlit 1.30 compatibility

- `st.dataframe(width="stretch")` does NOT work — use `use_container_width=True` instead.
- `st.column_config.*Column(width="small"/"medium"/"large")` not supported — omit the width param.
- Always test UI against pinned Streamlit version when making UI changes.

## Provenance contract (load-bearing)

Every holiday returned by this tool MUST be paired with:
- A non-null `source_url`
- A non-null `source_doc_title`
- A non-null `source_fetched_at` timestamp

National (public) holidays sourced from `python-holidays` are tagged with `source_origin="library"`, `is_reference_only=True`, and never drive any calculation.

The data-integrity test (`tests/test_data_integrity.py`) enforces this contract at CI time. Do not weaken it.

## Proprietary / dev-only files

- The `proprietary/` folder is dev-only reference material — it will NOT exist in production deployments and is gitignored.
- Never add proprietary files to git.
