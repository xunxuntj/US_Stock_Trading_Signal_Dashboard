"""
Telegram Bot Notification Dispatcher (core/notifier/telegram_dispatcher.py)
Sends rich Markdown trading decision cards and account reports via Telegram Bot API.
Supports optional HTTP/SOCKS proxy for network adaptability.
"""

import os
import httpx
from typing import Optional, Dict, Any


class TelegramDispatcher:
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None, proxy_url: Optional[str] = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.proxy_url = proxy_url or os.getenv("TELEGRAM_PROXY_URL") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")

    def is_configured(self) -> bool:
        return bool(
            self.bot_token and self.chat_id and
            self.bot_token != "TO_BE_FILLED" and
            self.chat_id != "TO_BE_FILLED"
        )

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Sends a text message to the configured Telegram chat."""
        if not self.is_configured():
            print(f"[Telegram Mock] (No Token Configured)\n{text}\n")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }

        try:
            client_kwargs: Dict[str, Any] = {"timeout": 15.0}
            if self.proxy_url:
                client_kwargs["proxy"] = self.proxy_url

            with httpx.Client(**client_kwargs) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    return True
                else:
                    print(f"Telegram send error ({resp.status_code}): {resp.text}")
                    return False
        except Exception as e:
            print(f"Telegram network exception: {e}")
            return False
