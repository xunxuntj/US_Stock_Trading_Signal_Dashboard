import os
import yfinance as yf
import pandas as pd

def main():
    # Tickers list
    tickers = ["SPY", "QQQ", "SOXX", "TQQQ", "QUAL", "JEPQ", "QLD", "PSQ", "SH", "QID", "GLD", "TLT", "DBC", "BITO", "^VIX", "SGOV", "NVDA"]
    
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
            
        except Exception as e:
            print(f"Error downloading {ticker}: {str(e)}")

if __name__ == "__main__":
    main()
