#!/bin/bash
# ==============================================================================
# External Server Local Cronjob Runner
# Run this script directly on your Linux Server / NAS / Raspberry Pi to execute
# the signal scan locally and push updated portfolio.db & data to GitHub.
# ==============================================================================

set -e

# Change to project root directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] Starting External Local Cron Scan ==="

# 1. Pull latest changes from GitHub (to preserve any web UI inputs)
echo "[1/4] Pulling latest remote changes..."
git pull --rebase origin main

# 2. Run data download & signal scan
echo "[2/4] Downloading live market data & running signal scan..."
python3 download_data.py
python3 run_daily_scan.py

# 3. Commit updated portfolio.db and data files
echo "[3/4] Checking for changes..."
if git status --porcelain | grep -E 'portfolio.db|data/'; then
    echo "[4/4] Committing and pushing updated database to GitHub..."
    git add portfolio.db data/
    git commit -m "auto: External cron daily signal scan & database sync [$(date '+%Y-%m-%d')]"
    git push origin main
    echo "✅ Scan & GitHub sync complete!"
else
    echo "ℹ️ No database or data changes detected. Push skipped."
fi

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] Cron Task Finished Successfully ==="
