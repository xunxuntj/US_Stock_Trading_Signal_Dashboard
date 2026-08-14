import os
import yfinance as yf
import pandas as pd

def main():
    # Tickers list
    tickers = ["SPY", "QQQ", "SOXX", "TQQQ", "QUAL", "JEPQ", "QLD", "PSQ", "SH", "QID", "GLD", "TLT", "DBC", "BITO", "^VIX", "SGOV", "NVDA", "000001.SS"]
    
    # Date range: We need data since 2020-01-01 to have warm-up for EMA200/DEMA200 starting 2021-06-08
    # Date range: We need data since 2020-01-01 to have warm-up for EMA200/DEMA200
    start_date = "2020-01-01"
    
    # Create data directory if it doesn't exist
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    
    print(f"Downloading live real-time market data from {start_date} to today...")
    
    for ticker in tickers:
        print(f"Fetching {ticker}...")
        try:
            # yfinance download with actions=True to get live real-time data
            df = yf.download(ticker, start=start_date, actions=True)

            if df.empty:
                print(f"Warning: No data received for {ticker}")
                continue
            
            # Reset index to make Date a column
            df = df.reset_index()
            
            # Standardize column names if MultiIndex
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [col[0] for col in df.columns]
                
            # Clean column names by removing _TICKER suffix if present
            new_cols = []
            for col in df.columns:
                col_str = str(col)
                if "_" in col_str and not col_str.startswith("^"):
                    col_str = col_str.split("_")[0]
                new_cols.append(col_str)
            df.columns = new_cols
            
            # Save to CSV
            file_path = os.path.join(data_dir, f"{ticker}.csv")
            df.to_csv(file_path, index=False)
            print(f"Saved {ticker} to {file_path} (Rows: {len(df)})")
            
            # Sync fresh market prices to Supabase Cloud market_prices table
            try:
                import database
                cloud_rows = []
                for _, r in df.iterrows():
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
                    # Upsert latest 30 daily bars for fast, reliable cloud syncing
                    database.upsert_cloud_market_price_rows(cloud_rows[-30:])
                    print(f"  ☁️ Synced {ticker} latest bars to Supabase Cloud market_prices!")
            except Exception as cloud_err:
                print(f"  ⚠️ Supabase Sync Warning for {ticker}: {cloud_err}")
                
        except Exception as e:
            print(f"Error downloading {ticker}: {str(e)}")

if __name__ == "__main__":
    main()
