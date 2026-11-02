"""
Technical Data Guard (core/sanity/data_guard.py)
Provides data freshness, trading calendar, and dirty data / anomaly validation
to prevent missing signals or erroneous signals caused by bad market data.
"""

import os
import datetime
import pandas as pd
from typing import Dict, List, Optional, Tuple


# Known US Market Holidays (fixed / major observed holidays)
US_HOLIDAYS_FIXED = [
    # New Year's Day, MLK Day, Washington's Birthday, Good Friday, Memorial Day, Juneteenth, Independence Day, Labor Day, Thanksgiving, Christmas
]


def is_us_market_open_now() -> bool:
    """Returns True if current time is within regular US equity trading hours (09:30 - 16:00 ET on weekday)."""
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    try:
        import zoneinfo
        et_tz = zoneinfo.ZoneInfo("America/New_York")
        now_et = now_utc.astimezone(et_tz)
    except Exception:
        now_et = now_utc - datetime.timedelta(hours=4)
        
    if now_et.weekday() >= 5:  # Saturday or Sunday
        return False
        
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_et < market_close

def is_us_trading_day(dt: Optional[datetime.date] = None) -> bool:
    """Check if date is a weekday (Monday-Friday)."""
    if dt is None:
        dt = datetime.date.today()
    # 0 = Monday, 4 = Friday, 5 = Saturday, 6 = Sunday
    return dt.weekday() < 5


class DataSanityReport:
    def __init__(self):
        self.is_valid: bool = True
        self.warnings: List[str] = []
        self.errors: List[str] = []
        self.stale_tickers: List[str] = []
        self.dirty_tickers: List[str] = []

    def add_error(self, ticker: str, msg: str):
        self.is_valid = False
        self.errors.append(f"[{ticker}] {msg}")
        self.dirty_tickers.append(ticker)

    def add_warning(self, ticker: str, msg: str):
        self.warnings.append(f"[{ticker}] {msg}")

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "stale_tickers": self.stale_tickers,
            "dirty_tickers": self.dirty_tickers,
        }


def validate_dataframe_integrity(ticker: str, df: pd.DataFrame, max_allowed_staleness_days: int = 4) -> Tuple[bool, List[str]]:
    """
    Validate that dataframe has no corrupted rows, NaN values, zero prices,
    or unreasonable price spikes in the recent bars.
    """
    issues = []
    if df is None or df.empty:
        return False, [f"{ticker}: DataFrame is empty or None"]

    if len(df) < 50:
        issues.append(f"{ticker}: Data length too short ({len(df)} < 50), indicators cannot be computed reliably")

    # Check required columns
    required_cols = ['Close']
    for col in required_cols:
        if col not in df.columns:
            issues.append(f"{ticker}: Missing required column '{col}'")

    if issues:
        return False, issues

    # Inspect recent 10 bars
    recent_df = df.tail(10)
    for idx, row in recent_df.iterrows():
        val = row['Close']
        if pd.isna(val) or val <= 0:
            issues.append(f"{ticker}: Invalid close price {val} at index {idx}")

    # Inspect price jump (> 45% single-day jump in non-leveraged ETF indicates bad unadjusted split)
    if len(df) >= 2 and ticker not in ["QLD", "TQQQ", "BITO"]:
        last_close = float(df['Close'].iloc[-1])
        prev_close = float(df['Close'].iloc[-2])
        if prev_close > 0:
            daily_change = abs(last_close - prev_close) / prev_close
            if daily_change > 0.45:
                issues.append(f"{ticker}: Abnormal single-day price movement {daily_change*100:.1f}% (${prev_close:.2f} -> ${last_close:.2f}), suspected unadjusted split or dirty data")

    return len(issues) == 0, issues


def check_universe_data_health(data_dict: Dict[str, pd.DataFrame], tickers: List[str]) -> DataSanityReport:
    """
    Comprehensive health check of all required tickers in universe.
    Prevents silent failure where missing data leads to missing signals.
    """
    report = DataSanityReport()
    today = datetime.date.today()

    for ticker in tickers:
        if ticker not in data_dict:
            report.add_error(ticker, "Ticker completely missing from market data directory")
            continue

        df = data_dict[ticker]
        valid, issues = validate_dataframe_integrity(ticker, df)
        if not valid:
            for issue in issues:
                report.add_error(ticker, issue)

        # Check freshness
        if not df.empty:
            last_dt = df.index[-1]
            if isinstance(last_dt, pd.Timestamp):
                last_date = last_dt.date()
                delta_days = (today - last_date).days
                # If weekday and gap > 4 days (accounting for 3-day weekend), flag warning
                if delta_days > 4 and is_us_trading_day(today):
                    report.add_warning(ticker, f"Data may be stale. Latest date is {last_date} ({delta_days} days old)")
                    report.stale_tickers.append(ticker)

    return report
