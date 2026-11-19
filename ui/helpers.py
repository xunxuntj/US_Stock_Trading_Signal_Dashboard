"""Reusable UI helper utilities (account privacy masking, secret resolution)."""

import os
import re
import pandas as pd


def clean_account_label(val) -> str:
    """Strip sensitive brokerage account numbers from display labels."""
    if val is None or (not isinstance(val, str) and pd.isna(val)):
        return ""
    s = str(val)
    # Strip generic numeric (5+ digits) or U-prefixed (U + 6+ digits) brokerage account IDs
    s = re.sub(r"\s*\(?(?:U[0-9]{6,}|[0-9]{5,})\)?", "", s)
    s = re.sub(r"\s*\(\s*\)", "", s)
    s = re.sub(r"\s*-\s*$", "", s).strip()
    return s


def get_app_secret(st_module, key_name: str, default: str = "") -> str:
    """Safely read a secret from environment variables first, then st.secrets."""
    val = os.getenv(key_name, "").strip()
    if val:
        return val
    try:
        return str(st_module.secrets.get(key_name, default) or "").strip()
    except Exception:
        return default
