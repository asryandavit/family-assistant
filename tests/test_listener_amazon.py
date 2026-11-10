"""listener.py wiring for /amazon (decision 101): the command and am: buttons go to amazon/bot.py,
never through the Runner (they do not block other jobs), a fault never crashes the listener, the
prompt reply routes to /amazon, and the existing routes are unchanged."""
import unittest
from unittest import mock

import listener
from lib import config
from tests.test_listener_ux import FakeRunner


class Amazon(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load()
        self.r = FakeRunner()

    def test_command_goes_to_amazon_bot(self):
        with mock.patch("amazon.bot.handle", return_value="queued") as h:
            self.assertEqual(listener.handle_text(self.cfg, self.r, "/amazon usb c 65w", "222"), "queued")
        h.assert_called_once_with(self.cfg, listener.ROOT, "/amazon usb c 65w", "222")
        self.assertEqual(self.r.calls, [])                       # not a Runner job

    def test_buttons_go_to_amazon_bot(self):
        with mock.patch("amazon.bot.callback", return_value=None) as c:
            self.assertIsNone(listener.handle_callback(self.cfg, self.r, "am:watch:ab12:1", "111", 9))
        c.assert_called_once_with(self.cfg, listener.ROOT, "am:watch:ab12:1", "111")

    def test_fault_does_not_crash_listener(self):
        with mock.patch("amazon.bot.handle", side_effect=RuntimeError("disk full")):
            r = listener.handle_text(self.cfg, self.r, "/amazon x y z", "111")
        self.assertIn("Amazon search is unavailable", r)

    def test_prompt_reply_routes(self):
        self.assertEqual(listener.route_reply("usb c charger", "🛒 Amazon search · what are you looking for?"),
                         "/amazon usb c charger")
        self.assertEqual(listener.route_reply("/help", "🛒 Amazon search · what are you looking for?"), "/help")

    def test_china_routes_are_unchanged(self):
        with mock.patch("china.bot.handle", return_value="china") as h:
            self.assertEqual(listener.handle_text(self.cfg, self.r, "/china GaN 65W", "222"), "china")
        h.assert_called_once()
        self.assertEqual(listener.route_reply("GaN", "🇨🇳 China search · what are you looking for?"), "/china GaN")


if __name__ == "__main__":
    unittest.main()
