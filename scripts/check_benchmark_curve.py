import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pandas as pd
import numpy as np
from database import get_nav_history
from config import DATA_DIR

df = get_nav_history()
df['date'] = pd.to_datetime(df['date'])
df_2026 = df[df['date'] >= '2026-01-15'].sort_values('date').reset_index(drop=True)
print(f"2026 rows: {len(df_2026)}, start date: {df_2026['date'].iloc[0]}, start equity: {df_2026['total_equity'].iloc[0]}")
print(f"Latest date: {df_2026['date'].iloc[-1]}, latest equity: {df_2026['total_equity'].iloc[-1]}")
ret_total = (df_2026['total_equity'].iloc[-1] - 99215.41) / 99215.41 * 100
ret_strat = (df_2026['strategy_equity'].iloc[-1] - 99215.41) / 99215.41 * 100
print(f"Total Return: +{ret_total:.2f}%, Strategy Return: +{ret_strat:.2f}%")

spy_f = os.path.join(DATA_DIR, 'SPY.csv')
if os.path.exists(spy_f):
    df_spy = pd.read_csv(spy_f)
    df_spy['Date'] = pd.to_datetime(df_spy['Date'])
    df_spy = df_spy[(df_spy['Date'] >= df_2026['date'].iloc[0]) & (df_spy['Date'] <= df_2026['date'].iloc[-1])]
    spy_ret = (df_spy['Close'].iloc[-1] - df_spy['Close'].iloc[0]) / df_spy['Close'].iloc[0] * 100
    print(f"SPY 2026 Return: +{spy_ret:.2f}%")

sse_f = os.path.join(DATA_DIR, '000001.SS.csv')
if os.path.exists(sse_f):
    df_sse = pd.read_csv(sse_f)
    df_sse['Date'] = pd.to_datetime(df_sse['Date'])
    df_sse = df_sse[(df_sse['Date'] >= df_2026['date'].iloc[0]) & (df_sse['Date'] <= df_2026['date'].iloc[-1])]
    sse_col = [c for c in df_sse.columns if 'Close' in c][0]
    sse_ret = (df_sse[sse_col].iloc[-1] - df_sse[sse_col].iloc[0]) / df_sse[sse_col].iloc[0] * 100
    print(f"SSE 2026 Return: +{sse_ret:.2f}%")
