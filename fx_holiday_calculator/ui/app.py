import streamlit as st


def main() -> None:
    st.set_page_config(page_title="FX Holiday Calculator", layout="wide")
    st.title("FX Holiday Calculator")
    st.caption("Sources cited per holiday")

    # Lazy imports so module import doesn't fail if individual tab breaks
    from fx_holiday_calculator.ui import sidebar, tab_about, tab_holidays, tab_swap

    sidebar.render()
    t1, t2, t3 = st.tabs([
        "Swap Date Calculator", "Holiday Calendar", "About / Sources",
    ])
    with t1:
        tab_swap.render()
    with t2:
        tab_holidays.render()
    with t3:
        tab_about.render()
