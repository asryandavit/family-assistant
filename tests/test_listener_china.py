"""listener.py wiring for /china (decision 088): the command and cn: buttons go to china/bot.py,
never through the Runner (they do not block other jobs), a fault never crashes the listener,
the prompt reply routes to /china, and the existing routes are unchanged."""
import unittest
from unittest import mock

import listener
from lib import config
from tests.test_listener_ux import FakeRunner


class China(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load()
        self.r = FakeRunner()

    def test_command_goes_to_china_bot(self):
        with mock.patch("china.bot.handle", return_value="queued") as h:
            self.assertEqual(listener.handle_text(self.cfg, self.r, "/china GaN 65W", "222"), "queued")
        h.assert_called_once_with(self.cfg, listener.ROOT, "/china GaN 65W", "222")
        self.assertEqual(self.r.calls, [])                       # not a Runner job

    def test_buttons_go_to_china_bot(self):
        with mock.patch("china.bot.callback", return_value=None) as c:
            self.assertIsNone(listener.handle_callback(self.cfg, self.r, "cn:only:taobao:ab12", "111", 9))
        c.assert_called_once_with(self.cfg, listener.ROOT, "cn:only:taobao:ab12", "111")

    def test_fault_does_not_crash_listener(self):
        with mock.patch("china.bot.handle", side_effect=RuntimeError("disk full")):
            r = listener.handle_text(self.cfg, self.r, "/china x y z", "111")
        self.assertIn("China search is unavailable", r)

    def test_prompt_reply_routes(self):
        self.assertEqual(listener.route_reply("GaN 65W", "🇨🇳 China search · what are you looking for?"),
                         "/china GaN 65W")
        self.assertEqual(listener.route_reply("/help", "🇨🇳 China search · what are you looking for?"),
                         "/help")

    def test_existing_routes_unchanged(self):
        self.assertEqual(listener.route_reply("lentils", "🔍 Price check"), "lentils"
                         if "🔍 Price check" not in "" else "lentils")
        self.assertEqual(listener.handle_callback(self.cfg, self.r, "mk:nope", "111", 5),
                         "Unrecognised button.")
        self.assertIn("/china", listener.HELP)


if __name__ == "__main__":
    unittest.main()
