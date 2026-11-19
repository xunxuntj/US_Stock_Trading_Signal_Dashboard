"""Unit tests for modular UI helpers and zero-dollar-exposure poster builder."""

import os
import re
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ui.helpers import clean_account_label, get_app_secret
from ui.poster import build_mobile_poster_html
from ui.styles import GLOBAL_TERMINAL_CSS, inject_global_terminal_styles


class TestUIHelpers(unittest.TestCase):
    """Tests for privacy masking, secret resolution, styles, and share poster HTML."""

    def test_clean_account_label_masks_sensitive_numbers(self):
        self.assertEqual(clean_account_label("老虎证券 - 综合账户 (638812)"), "老虎证券 - 综合账户")
        self.assertEqual(clean_account_label("老虎证券 - 环球账户 (U9959007)"), "老虎证券 - 环球账户")
        self.assertEqual(clean_account_label("Charles Schwab (56169533)"), "Charles Schwab")
        self.assertEqual(clean_account_label("Tiger - 638812"), "Tiger")
        self.assertEqual(clean_account_label("New Broker (99887766)"), "New Broker")
        self.assertEqual(clean_account_label("Tiger Global (U1234567)"), "Tiger Global")
        self.assertEqual(clean_account_label("Charles Schwab (嘉信理财)"), "Charles Schwab (嘉信理财)")

    def test_clean_account_label_handles_nulls_and_edge_cases(self):
        self.assertEqual(clean_account_label(None), "")
        self.assertEqual(clean_account_label(np.nan), "")
        self.assertEqual(clean_account_label("账户 ( ) - "), "账户")
        self.assertEqual(clean_account_label(""), "")

    def test_get_app_secret_env_precedence_and_fallback(self):
        fake_st = SimpleNamespace(secrets={"MY_KEY": "from_secrets"})

        with patch.dict(os.environ, {"MY_KEY": "from_env"}, clear=False):
            self.assertEqual(get_app_secret(fake_st, "MY_KEY", "fallback"), "from_env")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MY_KEY", None)
            self.assertEqual(get_app_secret(fake_st, "MY_KEY", "fallback"), "from_secrets")
            self.assertEqual(get_app_secret(fake_st, "MISSING_KEY", "fallback"), "fallback")

        class _BrokenSecrets:
            def get(self, *_args, **_kwargs):
                raise RuntimeError("secrets unavailable")

        broken_st = SimpleNamespace(secrets=_BrokenSecrets())
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MISSING_KEY", None)
            self.assertEqual(get_app_secret(broken_st, "MISSING_KEY", "safe_default"), "safe_default")

    def test_inject_global_terminal_styles_emits_css(self):
        captured = []
        fake_st = SimpleNamespace(markdown=lambda html, unsafe_allow_html=False: captured.append((html, unsafe_allow_html)))
        inject_global_terminal_styles(fake_st)
        self.assertEqual(len(captured), 1)
        self.assertTrue(captured[0][1])
        self.assertIn("color-scheme: dark", GLOBAL_TERMINAL_CSS)
        self.assertIn("<style>", captured[0][0])

    def test_build_mobile_poster_html_zero_dollar_exposure(self):
        html = build_mobile_poster_html(
            today_str="2026-11-19",
            live_days=245,
            total_live_ret_pct=18.52,
            alpha_card_pct=6.14,
            spy_card_ret=12.38,
            live_sharpe=1.85,
            macro_moic=1.19,
            real_max_dd=-4.21,
            us_live_ret_pct=15.40,
            us_live_cagr=24.10,
            hk_contrib_pct=3.12,
            html_signals_rows="<div class='sig-row'><span>NVDA</span><span>HOLD</span></div>",
            svg_fill_path="M 0,68 L 320,10 L 320,68 Z",
            svg_path="M 0,68 L 320,10",
            end_dot_x=320.0,
            end_dot_y=10.0,
            cf_yield_pct=4.85,
        )
        self.assertIn('name="color-scheme" content="dark"', html)
        self.assertIn('crossorigin="anonymous"', html)
        self.assertIn("function downloadPoster()", html)
        self.assertIn("+18.52%", html)
        self.assertIn("+6.1%", html)
        self.assertIn("-4.2%", html)

        # Privacy assertion: capture card must contain zero dollar amounts or raw account IDs
        match = re.search(r'<div id="capture-card".*?</div>\s*<button', html, flags=re.DOTALL)
        self.assertIsNotNone(match, "Capture card block must exist in rendered poster HTML")
        card_html = match.group(0)
        self.assertNotIn("$", card_html, "Poster capture card must not expose raw USD amounts")
        for sensitive_id in ("638812", "U9959007", "56169533"):
            self.assertNotIn(sensitive_id, card_html)


if __name__ == "__main__":
    unittest.main()
