"""
Charles Schwab OAuth Token Exchange Utility (scripts/exchange_schwab_token.py)
Exchanges Schwab OAuth authorization code from redirect URL into:
- access_token (valid 30 mins)
- refresh_token (valid 7 days)
Supports automatic retry across redirect_uri variants (https://127.0.0.1 and https://127.0.0.1/)
and code decoding variants.
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

    if not app_key:
        app_key = input("请输入您的 SCHWAB_APP_KEY: ").strip()
    if not app_secret:
        app_secret = input("请输入您的 SCHWAB_APP_SECRET: ").strip()

    if not redirect_url:
        redirect_url = input("请粘贴浏览器重定向的完整URL (以https://127.0.0.1开头): ").strip()

    # Parse code from redirect url
    parsed = urllib.parse.urlparse(redirect_url)
    params = urllib.parse.parse_qs(parsed.query)
    raw_code = params.get("code", [None])[0]

    if not raw_code:
        if "code=" in redirect_url:
            raw_code = redirect_url.split("code=")[1].split("&")[0]
        else:
            raw_code = redirect_url.strip()

    # Schwab code variants: raw vs unquoted (@ vs %40)
    code_variants = []
    if raw_code:
        c1 = raw_code.replace("%40", "@")
        code_variants.append(c1)
        c2 = urllib.parse.unquote(raw_code)
        if c2 not in code_variants:
            code_variants.append(c2)
        if raw_code not in code_variants:
            code_variants.append(raw_code)

    print(f"🔑 Using App Key: {app_key[:6]}******")

    # Basic auth header: base64(app_key:app_secret)
    creds = f"{app_key}:{app_secret}".encode("utf-8")
    basic_auth = base64.b64encode(creds).decode("utf-8")

    token_url = "https://api.schwabapi.com/v1/oauth/token"
    headers = {
        "Authorization": f"Basic {basic_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    # Try both redirect_uri formats in case user registered with/without trailing slash
    redirect_uris = ["https://127.0.0.1", "https://127.0.0.1/"]

    proxies = None
    if not os.getenv("GITHUB_ACTIONS"):
        p_val = os.getenv("TELEGRAM_PROXY_URL")
        # In mainland China, Schwab auth needs proxy; in US/Azure runner, direct is used
        if p_val:
            proxies = p_val

    last_err = None
    for r_uri in redirect_uris:
        for c in code_variants:
            payload = {
                "grant_type": "authorization_code",
                "code": c,
                "redirect_uri": r_uri
            }
            try:
                with httpx.Client(timeout=15.0, proxy=proxies) as client:
                    resp = client.post(token_url, headers=headers, data=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        refresh_token = data.get("refresh_token")
                        access_token = data.get("access_token")
                        expires_in = data.get("expires_in")

                        print("\n" + "=" * 65)
                        print("🎉 恭喜！SCHWAB OAUTH 认证成功，REFRESH TOKEN 获取成功！")
                        print("=" * 65)
                        print(f"✅ access_token received (valid {expires_in}s)")
                        print(f"\n🔑 请复制以下完整的 REFRESH TOKEN 填入 GitHub Secrets 的 SCHWAB_REFRESH_TOKEN:\n")
                        print(f"{refresh_token}\n")
                        print("=" * 65)

                        # Update .env if present
                        update_env_tokens(app_key, app_secret, refresh_token)
                        return data
                    else:
                        last_err = f"Status {resp.status_code}: {resp.text}"
            except Exception as e:
                last_err = str(e)

    print(f"\n❌ Token 换取失败: {last_err}")
    print("💡 提示：嘉信的 authorization code 通常只有 30 秒至 1 分钟的有效期。")
    print("   如果提示 'invalid_grant' 或 'expired'，只需重新在浏览器点一次授权登录，生成新的 URL 即可秒级换取！")
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

    print(f"💾 本地配置文件 {ENV_PATH} 已自动同步保存！")


if __name__ == "__main__":
    url_arg = sys.argv[1] if len(sys.argv) > 1 else None
    k_arg = sys.argv[2] if len(sys.argv) > 2 else None
    s_arg = sys.argv[3] if len(sys.argv) > 3 else None
    exchange_code(url_arg, k_arg, s_arg)
