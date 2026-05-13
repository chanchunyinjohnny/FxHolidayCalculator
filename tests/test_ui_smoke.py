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
    "fx_holiday_calculator.ui.product_otc_option",
    "fx_holiday_calculator.ui.product_listed_option",
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
