"""
HK IPO & Kids Wealth Matrix Integration Package (core/ipo)
Provides:
1. Tiger Brokerage real HK IPO order & fee reconciliation
2. Historical kids wealth matrix backward compatibility guarantee
3. Automated post-exit profit and kid settlement calculation engine
"""

from .tracker import (
    reconcile_tiger_hk_ipo_trades,
    calculate_kid_ipo_settlement,
    get_dynamic_kids_available_capital
)

__all__ = [
    "reconcile_tiger_hk_ipo_trades",
    "calculate_kid_ipo_settlement",
    "get_dynamic_kids_available_capital"
]
