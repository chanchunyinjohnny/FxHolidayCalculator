"""Calculator parent tab — hosts the four product sub-tabs.

Sub-tabs are loaded lazily so an exception in one product doesn't kill
the others.
"""

import streamlit as st


def render() -> None:
    st.write("")  # spacing under the top-level tab bar

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
