import os
import yfinance as yf
import pandas as pd

def main():
    # Tickers list
    tickers = ["SPY", "QQQ", "SOXX", "TQQQ", "QUAL", "JEPQ", "QLD", "PSQ", "SH", "QID", "GLD", "TLT", "DBC", "BITO", "^VIX", "SGOV"]
    
    # Date range: We need data since 2020-01-01 to have warm-up for EMA200/DEMA200 starting 2021-06-08
    start_date = "2020-01-01"
    end_date = "2026-06-09" # To include 2026-06-08
    
    # Create data directory if it doesn't exist
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    
    print(f"Downloading historical data from {start_date} to {end_date}...")
    
    for ticker in tickers:
        print(f"Fetching {ticker}...")
        try:
            # yfinance download with actions=True to get dividend data
            df = yf.download(ticker, start=start_date, end=end_date, actions=True)

            if df.empty:
                print(f"Warning: No data received for {ticker}")
                continue
            
            # Reset index to make Date a column
            df = df.reset_index()
            
            # Check column names: yfinance sometimes returns multi-index columns if download is called in specific ways.
            # Flatten columns if necessary
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [col[0] if col[1] == '' else f"{col[0]}_{col[1]}" for col in df.columns]
                # If yfinance returned MultiIndex like ('Close', 'SPY')
                # Let's inspect or normalize
                # Normally yf.download('SPY') returns standard columns: Date, Open, High, Low, Close, Adj Close, Volume.
                # But when downloading a single ticker, standard download has simple columns.
                pass
            
            # Ensure column names are standard
            # We want Date, Open, High, Low, Close, Adj Close, Volume
            # Let's check what we have
            print(f"Columns for {ticker}: {list(df.columns)}")
            
            # Save to CSV
            file_path = os.path.join(data_dir, f"{ticker}.csv")
            df.to_csv(file_path, index=False)
            print(f"Saved {ticker} to {file_path} (Rows: {len(df)})")
            
        except Exception as e:
            print(f"Error downloading {ticker}: {str(e)}")

if __name__ == "__main__":
    main()
