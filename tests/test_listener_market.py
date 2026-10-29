"""listener.py wiring for Market watch (decision 087): /watch, the market job, dialog
replies, mk: buttons — and that the existing commands behave exactly as before."""
import unittest
from unittest import mock

import listener
from lib import config
from market import bot
from tests.test_listener_ux import FakeRunner, Recorder


class Market(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load()
        self.r = FakeRunner()

    def test_watch_check_launches_family_job(self):
        self.assertEqual(listener.handle_text(self.cfg, self.r, "/watch check", "222"), "launched market")
        self.assertEqual(self.r.calls[-1][0], "market")
        self.assertIn("--send", listener.JOBS["market"]["args"])
        self.assertNotIn("market", listener.REPLY_JOBS)        # report goes to both chats

    def test_check_now_button(self):
        self.assertEqual(listener.handle_callback(self.cfg, self.r, "cmd:market", "1", 2), "launched market")

    def test_watch_goes_to_market_bot(self):
        with mock.patch("market.bot.handle", return_value="ok") as h:
            self.assertEqual(listener.handle_text(self.cfg, self.r, "/watch price 2 9890", "111"), "ok")
        h.assert_called_once_with(self.cfg, listener.ROOT, "/watch price 2 9890", "111")
        self.assertEqual(self.r.calls, [])

    def test_add_button(self):
        with mock.patch("market.bot.start_add", return_value=None) as s:
            self.assertIsNone(listener.handle_callback(self.cfg, self.r, "mk:add", "111", 5))
        s.assert_called_once_with(self.cfg, listener.ROOT, "111")
        self.assertEqual(listener.handle_callback(self.cfg, self.r, "mk:nope", "111", 5),
                         "Unrecognised button.")

    def test_market_fault_does_not_crash_listener(self):
        with mock.patch("market.bot.handle", side_effect=RuntimeError("disk full")):
            out = listener.handle_text(self.cfg, self.r, "/watch", "111")
        self.assertIn("Market watch is unavailable right now (disk full)", out)

    def test_dialog_reply_routing(self):
        prompt = "🌍 %s\n1/4 · What is it?" % bot.PROMPT_MARK
        self.assertEqual(listener.route_reply("Airfryer", prompt), "/watch answer Airfryer")
        self.assertEqual(listener.route_reply("/watch", prompt), "/watch")
        self.assertEqual(bot.route_reply("Airfryer", prompt), "/watch answer Airfryer")

    def test_menu_and_help(self):
        self.assertIn("/watch", listener.HELP)


class ExistingBehaviourUnchanged(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load()
        self.r = FakeRunner()

    def test_price_prompt_routing(self):
        self.assertEqual(listener.route_reply("lentils", "🔍 Which product?"), "/price lentils")

    def test_jobs_kept(self):
        for name in ("scan", "digest", "stays", "flights", "price", "basket"):
            self.assertIn(name, listener.JOBS)
        self.assertEqual(listener.REPLY_JOBS, {"flights", "stays", "price"})

    def test_basket_and_scan(self):
        listener.handle_text(self.cfg, self.r, "/basket", "1")
        listener.handle_text(self.cfg, self.r, "/scan", "1")
        self.assertEqual([c[0] for c in self.r.calls], ["basket", "scan"])

    def test_unknown_text_silent(self):
        with Recorder() as rec:
            self.assertIsNone(listener.handle_text(self.cfg, self.r, "hello", "1"))
        self.assertEqual(rec.sent, [])


if __name__ == "__main__":
    unittest.main()
