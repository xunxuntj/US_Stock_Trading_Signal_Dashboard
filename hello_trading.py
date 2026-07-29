import pandas as pd
import ccxt
import plotly
import dotenv
import requests
import sys

def main():
    print(f"Python Setup Info:")
    print(f"Python Version: {sys.version}")
    print(f"Pandas Version: {pd.__version__}")
    print(f"CCXT Version: {ccxt.__version__}")
    print("Trading System Ready")

if __name__ == "__main__":
    main()
