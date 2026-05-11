import streamlit as st


def main() -> None:
    st.set_page_config(page_title="FX Holiday Calculator", layout="wide")
    st.title("FX Holiday Calculator")
    st.caption("Sources cited per holiday")

    # Lazy imports so any one tab's import failure doesn't kill the others.
    from fx_holiday_calculator.ui import sidebar, tab_about, tab_calculator, tab_holidays

    sidebar.render()
    t1, t2, t3 = st.tabs(
        [
            "Calculator",
            "Holiday Calendar",
            "About / Sources",
        ]
    )
    with t1:
        tab_calculator.render()
    with t2:
        tab_holidays.render()
    with t3:
        tab_about.render()
