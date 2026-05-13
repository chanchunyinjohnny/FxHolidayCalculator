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
        product_listed_option,
        product_ndf,
        product_otc_option,
        product_spot,
        product_swap,
    )

    sub = st.tabs(
        [
            "Spot",
            "Swap",
            "Forward",
            "NDF",
            "FX OTC Option",
            "FX Futures",
            "FX Listed Option",
        ]
    )
    with sub[0]:
        product_spot.render()
    with sub[1]:
        product_swap.render()
    with sub[2]:
        product_forward.render()
    with sub[3]:
        product_ndf.render()
    with sub[4]:
        product_otc_option.render()
    with sub[5]:
        product_futures.render()
    with sub[6]:
        product_listed_option.render()
