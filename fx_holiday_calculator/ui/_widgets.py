"""Small Streamlit widget helpers shared across product sub-tabs."""

from __future__ import annotations

from datetime import date

import streamlit as st


def _make_today_setter(key: str):
    def _setter():
        st.session_state[key] = date.today()

    return _setter


def date_input_with_today(container, label: str, key: str, *, default: date | None = None) -> date:
    """Render a date_input with a 'Today' shortcut button beside it.

    Clicking Today resets the widget value to today's date via an on_click
    callback (which fires before the next rerun, so the widget picks up the
    new session_state value cleanly).
    """
    if default is None:
        default = date.today()
    input_col, btn_col = container.columns([3, 1])
    value = input_col.date_input(label, value=default, key=key)
    btn_col.write("")  # spacer so the button aligns below the label, not with it
    btn_col.button("Today", key=f"{key}__today", on_click=_make_today_setter(key))
    return value


def render_reasoning(steps: list[str]) -> None:
    """Render an engine-emitted plain-English reasoning summary.

    Each entry is a self-contained markdown bullet that explains one step of
    the date derivation — anchor used, rule applied, raw vs adjusted, etc.
    Renders nothing if the list is empty.
    """
    if not steps:
        return
    st.markdown("### Reasoning")
    for s in steps:
        st.markdown(f"- {s}")


def render_trace(steps, label: str) -> None:
    """Render an adjustment trace expander.

    Each step shows the candidate date, weekday, per-calendar status with
    holiday names, and the engine's decision (accepted / reject_holiday /
    reject_weekend / rolled_eom). Source citations appear as captions when
    the underlying holiday entry carries provenance.
    """
    if not steps:
        st.write(f"_{label}: no adjustment steps_")
        return
    with st.expander(f"{label} — {len(steps)} candidate(s)", expanded=True):
        for s in steps:
            cols = st.columns([1.4, 0.5, 4, 1])
            cols[0].write(s.candidate_date.isoformat())
            cols[1].write(s.weekday)
            cells = []
            for cal_label, status in s.statuses.items():
                if status.is_good:
                    cells.append(f"{cal_label}: ✓")
                else:
                    cells.append(f"{cal_label}: ✘ {status.holiday_name}")
            cols[2].write("  ·  ".join(cells))
            cols[3].write(s.decision)
            for cal_label, status in s.statuses.items():
                if status.source is not None:
                    st.caption(
                        f"{cal_label}: [{status.source.doc_title}]({status.source.url}) · "
                        f"fetched {status.source.fetched_at.isoformat()} · "
                        f"{status.source_origin}"
                    )
