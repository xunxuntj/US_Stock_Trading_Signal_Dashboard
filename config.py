import os

# v2.29 Strategy Configuration Parameters
INITIAL_CAPITAL = 100000.0

# Base Allocation Targets
JEPQ_TARGET_PCT = 0.60    # 60% JEPQ Base (DRIP enabled)
QUAL_TARGET_PCT = 0.00    # 0% QUAL
SGOV_TARGET_PCT = 0.40    # 40% Initial SGOV Cash Pool

# Trend Layer Parameters
MAX_TREND_CAPACITY_PCT = 0.55  # 55% Max NAV Trend Layer Cap
SINGLE_POSITION_CAP_PCT = 0.10  # 10% NAV per L1 / Non-Equity position
L2_POSITION_CAP_PCT = 0.08      # 8% NAV per L2 position

# Breadth Gate Thresholds
S5FI_L1_THRESHOLD = 45.0
S5FI_L2_THRESHOLD = 55.0

# Tickers Universe
EQUITY_L1_TICKERS = ["SPY", "QQQ", "SOXX"]
EQUITY_L2_WHITELIST = {
    "SPY": ["QQQ"],
    "QQQ": ["SOXX", "QLD"],
    "SOXX": []
}
NON_EQUITY_TICKERS = ["GLD", "TLT", "DBC", "BITO"]
BASE_TICKERS = ["JEPQ", "SGOV"]

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(BASE_DIR, "portfolio.db")
