"""Reusable UI helper utilities (account privacy masking, secret resolution)."""

import os
import re
import pandas as pd


def clean_account_label(val) -> str:
    """Strip sensitive brokerage account numbers from display labels."""
    if val is None or (not isinstance(val, str) and pd.isna(val)):
        return ""
    s = str(val)
    for raw_num in ("(638812)", "638812", "(U9959007)", "U9959007", "(56169533)", "56169533"):
        s = s.replace(raw_num, "")
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
