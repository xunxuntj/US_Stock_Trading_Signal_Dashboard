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

    print(f"--------------------------------------------------")
    print(f"🎉 MARKET DATA SYNC COMPLETED SUCCESSFULLY!")
    print(f"==================================================")

if __name__ == "__main__":
    main()
