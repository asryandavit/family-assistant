"""The bot token never reaches listener.log (requests puts the Bot API URL, token included,
into its exception text — seen in poll-error lines, 2026-11-15)."""
import io
import unittest
from unittest import mock

import listener

FAKE = "bot1234567890:AAHfake-Token_value0123456789abcdefXYZ"
POLL_ERROR = ("HTTPSConnectionPool(host='api.telegram.org', port=443): Max retries exceeded "
              f"with url: /{FAKE}/getUpdates?timeout=50&offset=0")


class RedactTest(unittest.TestCase):
    def test_token_in_url_is_replaced(self):
        out = listener.redact(POLL_ERROR)
        self.assertNotIn("AAHfake", out)
        self.assertNotIn("1234567890:", out)
        self.assertIn("/bot<token>/getUpdates", out)

    def test_cut_off_token_is_replaced_too(self):
        # the poll-error line is cut at 120 characters, which can split the token
        self.assertEqual(listener.redact("x /bot1234567890:AAHfa"), "x /bot<token>")

    def test_ordinary_text_unchanged(self):
        for text in ("job price finished rc=0", "app cmd: /price lentils", "robot 12:30", ""):
            self.assertEqual(listener.redact(text), text)

    def test_non_string_is_accepted(self):
        self.assertEqual(listener.redact(RuntimeError(FAKE)), "bot<token>")

    def test_log_writes_redacted_line(self):
        buf = io.StringIO()
        with mock.patch.object(listener, "_log_f", buf), mock.patch("builtins.print"):
            listener.log(f"poll error: {POLL_ERROR[:120]}; retry in 5s")
        self.assertNotIn("AAHfake", buf.getvalue())
        self.assertNotIn("1234567890:", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
