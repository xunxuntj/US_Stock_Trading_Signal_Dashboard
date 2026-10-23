import os
import sys
import yfinance as yf
import pandas as pd

sys.path.append('.')

def main():
    # Core tickers list
    tickers = ["SPY", "QQQ", "SOXX", "TQQQ", "QUAL", "JEPQ", "QLD", "PSQ", "SH", "QID", "GLD", "TLT", "DBC", "BITO", "^VIX", "SGOV", "NVDA", "000001.SS"]
    start_date = "2020-01-01"
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    
    print(f"==================================================")
    print(f"🚀 DOWNLOADING LIVE REAL-TIME MARKET DATA TO SUPABASE & CSV")
    print(f"==================================================")
    
    for ticker in tickers:
        print(f"Fetching {ticker}...")
        try:
            # 1. Download primary historical dataset
            df_hist = yf.download(ticker, start=start_date, actions=True)
            if not df_hist.empty:
                df_hist = df_hist.reset_index()
                if isinstance(df_hist.columns, pd.MultiIndex):
                    df_hist.columns = [col[0] for col in df_hist.columns]
                df_hist.columns = [str(col).split("_")[0] if "_" in str(col) and not str(col).startswith("^") else str(col) for col in df_hist.columns]
                df_hist['Date'] = pd.to_datetime(df_hist['Date']).dt.tz_localize(None)
                df_hist = df_hist.set_index('Date')
            else:
                df_hist = pd.DataFrame()

            # 2. Patch with recent 10d real-time bars to bypass API caching lag
            try:
                tk = yf.Ticker(ticker)
                df_recent = tk.history(period="10d")
                if not df_recent.empty:
                    df_recent.index = pd.to_datetime(df_recent.index).tz_localize(None)
                    if not df_hist.empty:
                        df_comb = pd.concat([df_hist, df_recent])
                        df_comb = df_comb.loc[~df_comb.index.duplicated(keep='last')].sort_index()
                    else:
                        df_comb = df_recent.sort_index()
                else:
                    df_comb = df_hist
            except Exception as patch_err:
                print(f"  ⚠️ Patch warning for {ticker}: {patch_err}")
                df_comb = df_hist

            if df_comb.empty:
                print(f"Warning: No data available for {ticker}")
                continue

            # 3. Save to local CSV
            df_out = df_comb.reset_index()
            file_path = os.path.join(data_dir, f"{ticker}.csv")
            df_out.to_csv(file_path, index=False)
            last_date_str = str(df_out['Date'].iloc[-1])[:10]
            print(f"  ✅ Saved {ticker}.csv (Rows: {len(df_out)} | Last Date: {last_date_str})")
            
            # 4. Sync latest bars to Supabase Cloud market_prices table
            try:
                import database
                cloud_rows = []
                for _, r in df_out.tail(30).iterrows():
                    d_str = str(r['Date'])[:10]
                    cloud_rows.append({
                        "ticker": ticker,
                        "date": d_str,
                        "open": float(r['Open']) if pd.notnull(r.get('Open')) else None,
                        "high": float(r['High']) if pd.notnull(r.get('High')) else None,
                        "low": float(r['Low']) if pd.notnull(r.get('Low')) else None,
                        "close": float(r['Close']) if pd.notnull(r.get('Close')) else None,
                        "volume": int(r['Volume']) if pd.notnull(r.get('Volume')) else None
                    })
                if cloud_rows:
                    database.upsert_cloud_market_price_rows(cloud_rows)
                    print(f"  ☁️ Upserted {len(cloud_rows)} bars for {ticker} to Supabase market_prices (Latest: {last_date_str})")
            except Exception as cloud_err:
                print(f"  ⚠️ Supabase Sync Warning for {ticker}: {cloud_err}")
                
        except Exception as e:
            print(f"❌ Error downloading {ticker}: {str(e)}")

    # 5. Update S5FI Market Breadth (% S&P 500 stocks above 50-day SMA)
    try:
        import io, requests, database
        url_sp = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        headers_sp = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        tables_sp = pd.read_html(io.StringIO(requests.get(url_sp, headers=headers_sp, timeout=15).text))
        sp_tickers = tables_sp[0]['Symbol'].str.replace('.', '-', regex=False).tolist()
        df_sp_close = yf.download(sp_tickers, period="4mo", progress=False)['Close']
        sma50 = df_sp_close.rolling(window=50).mean()
        s5fi_series = ((df_sp_close > sma50).sum(axis=1) / df_sp_close.notna().sum(axis=1) * 100).dropna()
        if not s5fi_series.empty:
            df_s5fi_new = pd.DataFrame({'Date': pd.to_datetime(s5fi_series.index).tz_localize(None).strftime('%Y-%m-%d'), 'Close': s5fi_series.values})
            s5fi_path = os.path.join(data_dir, "S5FI.csv")
            if os.path.exists(s5fi_path):
                df_s5fi_old = pd.read_csv(s5fi_path)
                df_s5fi_old['Date'] = pd.to_datetime(df_s5fi_old['Date']).dt.strftime('%Y-%m-%d')
                df_s5fi_comb = pd.concat([df_s5fi_old, df_s5fi_new]).drop_duplicates(subset=['Date'], keep='last').sort_values('Date').reset_index(drop=True)
            else:
                df_s5fi_comb = df_s5fi_new
            df_s5fi_comb.to_csv(s5fi_path, index=False)
            s5fi_rows = [{"ticker": "S5FI", "date": r['Date'], "open": float(r['Close']), "high": float(r['Close']), "low": float(r['Close']), "close": float(r['Close']), "volume": 0} for _, r in df_s5fi_comb.tail(30).iterrows()]
            database.upsert_cloud_market_price_rows(s5fi_rows)
            print(f"  ✅ Updated S5FI.csv & Cloud (Latest: {df_s5fi_comb['Date'].iloc[-1]} = {df_s5fi_comb['Close'].iloc[-1]:.2f}%)")
    except Exception as s5fi_err:
        print(f"  ⚠️ S5FI update warning: {s5fi_err}")

    print(f"--------------------------------------------------")
    print(f"🎉 MARKET DATA SYNC COMPLETED SUCCESSFULLY!")
    print(f"==================================================")

if __name__ == "__main__":
    main()
