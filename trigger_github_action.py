#!/usr/bin/env python3
"""
External Cronjob Trigger for GitHub Actions Workflow
-----------------------------------------------------
Use this script on your local PC, Linux Server, Synology NAS, or any external Cronjob
to trigger the GitHub Actions workflow ('daily_scan.yml') precisely at specified market close times.

Usage:
  python trigger_github_action.py --token YOUR_GITHUB_PAT
"""

import argparse
import urllib.request
import json
import sys

REPO_OWNER = "xunxuntj"
REPO_NAME = "US_Stock_Trading_Signal_Dashboard"
WORKFLOW_FILE = "daily_scan.yml"

def trigger_workflow(github_token, branch="main"):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {github_token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "External-Cron-Trigger"
    }
    
    payload = json.dumps({"ref": branch}).encode('utf-8')
    
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status == 204:
                print(f"✅ Successfully triggered GitHub Action [{WORKFLOW_FILE}] for branch '{branch}'!")
                return True
            else:
                print(f"⚠️ Unexpected status code: {resp.status}")
                return False
    except Exception as e:
        print(f"❌ Failed to trigger GitHub Action: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trigger GitHub Actions via API for precise Cron Execution")
    parser.add_argument("--token", required=True, help="GitHub Personal Access Token (PAT) with repo scope")
    parser.add_argument("--branch", default="main", help="Branch name (default: main)")
    
    args = parser.parse_args()
    success = trigger_workflow(args.token, args.branch)
    sys.exit(0 if success else 1)
