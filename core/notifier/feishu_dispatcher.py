"""
Feishu / Lark Webhook Dispatcher (core/notifier/feishu_dispatcher.py)
Sends formatted rich interactive cards and technical alert cards to Feishu bots.
"""

import os
import httpx
from typing import Optional, Dict, Any, List


class FeishuDispatcher:
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("FEISHU_WEBHOOK_URL")

    def is_configured(self) -> bool:
        return bool(self.webhook_url and self.webhook_url.startswith("http"))

    def send_card(self, title: str, elements: List[Dict[str, Any]], template_color: str = "blue") -> bool:
        """
        Sends a Feishu interactive card message.
        template_color options: 'blue', 'green', 'red', 'orange', 'yellow', 'grey'
        """
        if not self.is_configured():
            print(f"[Feishu Mock] (No Webhook Configured) Title: {title}\nElements: {elements}\n")
            return False

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title
                    },
                    "template": template_color
                },
                "elements": elements
            }
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(self.webhook_url, json=payload)
                if resp.status_code == 200 and resp.json().get("StatusCode") == 0:
                    return True
                else:
                    print(f"Feishu send error: {resp.text}")
                    return False
        except Exception as e:
            print(f"Feishu network exception: {e}")
            return False

    def send_markdown(self, title: str, md_content: str, color: str = "blue") -> bool:
        """Convenient method to send Markdown text in an interactive card."""
        elements = [
            {
                "tag": "markdown",
                "content": md_content
            }
        ]
        return self.send_card(title=title, elements=elements, template_color=color)
