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
