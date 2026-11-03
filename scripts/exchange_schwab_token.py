"""
Charles Schwab OAuth Token Exchange Utility (scripts/exchange_schwab_token.py)
Exchanges Schwab OAuth authorization code from redirect URL into:
- access_token (valid 30 mins)
- refresh_token (valid 7 days)
And automatically updates .env or outputs for GitHub Secrets!
"""

import os
import sys
import base64
import urllib.parse
import httpx
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_PATH)


def exchange_code(redirect_url: str, app_key: str = None, app_secret: str = None):
    app_key = (app_key or os.getenv("SCHWAB_APP_KEY", "")).strip()
    app_secret = (app_secret or os.getenv("SCHWAB_APP_SECRET", "")).strip()

    if not app_key or not app_secret:
        print("❌ Error: SCHWAB_APP_KEY and SCHWAB_APP_SECRET are required!")
        print("Please provide them or configure them in .env")
        return None

    # Parse code from redirect url
    parsed = urllib.parse.urlparse(redirect_url)
    params = urllib.parse.parse_qs(parsed.query)
    raw_code = params.get("code", [None])[0]

    if not raw_code:
        if "code=" in redirect_url:
            raw_code = redirect_url.split("code=")[1].split("&")[0]
        else:
            raw_code = redirect_url

    # In Schwab, @ is encoded as %40, unquote if necessary
    code = urllib.parse.unquote(raw_code)
    if not code.endswith("@") and "%40" in raw_code:
        code = raw_code.replace("%40", "@")

    print(f"🔑 Using App Key: {app_key[:6]}******")
    print(f"📦 Authorization Code parsed: {code[:20]}...")

    # Basic auth header: base64(app_key:app_secret)
    creds = f"{app_key}:{app_secret}".encode("utf-8")
    basic_auth = base64.b64encode(creds).decode("utf-8")

    token_url = "https://api.schwabapi.com/v1/oauth/token"
    headers = {
        "Authorization": f"Basic {basic_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "https://127.0.0.1"
    }

    try:
        # Never use SOCKS proxy in GitHub Actions (direct US internet connection)
        proxies = None
        if not os.getenv("GITHUB_ACTIONS"):
            p_val = os.getenv("TELEGRAM_PROXY_URL")
            if p_val and "socks" not in p_val:
                proxies = p_val

        with httpx.Client(timeout=15.0, proxy=proxies) as client:
            resp = client.post(token_url, headers=headers, data=payload)

            if resp.status_code == 200:
                data = resp.json()
                refresh_token = data.get("refresh_token")
                access_token = data.get("access_token")
                expires_in = data.get("expires_in")

                print("\n" + "=" * 60)
                print("🎉 SCHWAB OAUTH AUTHORIZATION SUCCESSFUL!")
                print("=" * 60)
                print(f"✅ access_token received (valid {expires_in}s)")
                print(f"\n🔑 YOUR SCHWAB REFRESH TOKEN IS:\n")
                print(f"{refresh_token}\n")
                print("=" * 60)

                # Update .env if present
                update_env_tokens(app_key, app_secret, refresh_token)
                return data
            else:
                print(f"❌ Token exchange failed (Status {resp.status_code}): {resp.text}")
                return None
    except Exception as e:
        print(f"❌ Request error: {e}")
        return None


def update_env_tokens(app_key: str, app_secret: str, refresh_token: str):
    if not os.path.exists(ENV_PATH):
        return

    with open(ENV_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    updated = []
    key_found = False
    secret_found = False
    refresh_found = False

    for line in lines:
        if line.startswith("SCHWAB_APP_KEY="):
            updated.append(f"SCHWAB_APP_KEY={app_key}\n")
            key_found = True
        elif line.startswith("SCHWAB_APP_SECRET="):
            updated.append(f"SCHWAB_APP_SECRET={app_secret}\n")
            secret_found = True
        elif line.startswith("SCHWAB_REFRESH_TOKEN="):
            updated.append(f"SCHWAB_REFRESH_TOKEN={refresh_token}\n")
            refresh_found = True
        else:
            updated.append(line)

    if not key_found:
        updated.append(f"SCHWAB_APP_KEY={app_key}\n")
    if not secret_found:
        updated.append(f"SCHWAB_APP_SECRET={app_secret}\n")
    if not refresh_found:
        updated.append(f"SCHWAB_REFRESH_TOKEN={refresh_token}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(updated)

    print(f"💾 Updated {ENV_PATH} with SCHWAB_REFRESH_TOKEN!")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        url_arg = sys.argv[1]
        k_arg = sys.argv[2] if len(sys.argv) > 2 else None
        s_arg = sys.argv[3] if len(sys.argv) > 3 else None
        exchange_code(url_arg, k_arg, s_arg)
    else:
        print("Usage: python scripts/exchange_schwab_token.py <redirect_url> [app_key] [app_secret]")
