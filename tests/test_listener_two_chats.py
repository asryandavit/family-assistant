"""Two family chats in listener.py (decision 082): replies and asked-for job
results go to the chat that asked; travel scans stay with the owner. Telegram
and the Windows task query are stubbed -- nothing is sent."""
import unittest

import listener
from lib import config, telegram, ui
from tests.test_listener_ux import FakeRunner, Recorder

KARINE = "222"


class RepliesGoToTheAsker(unittest.TestCase):
    def setUp(self):
        self.cfg, self.r = config.load(), FakeRunner()

    def test_home_key_and_start(self):
        with Recorder() as rec:
            listener.handle_text(self.cfg, self.r, ui.KEY_HOME, KARINE)
            listener.handle_text(self.cfg, self.r, "/start", KARINE)
        self.assertTrue(rec.sent)
        self.assertTrue(all(kw.get("chat_id") == KARINE for _, kw in rec.sent))
        self.assertEqual(rec.sent[1][1]["reply_keyboard"], ui.BOTTOM_KEYBOARD)

    def test_price_prompt_and_price_job(self):
        with Recorder() as rec:
            listener.handle_text(self.cfg, self.r, ui.KEY_PRICE, KARINE)
        self.assertEqual(rec.sent[-1][1]["chat_id"], KARINE)
        out = listener.handle_text(self.cfg, self.r, "/price lentils", KARINE)
        self.assertEqual(out, "launched price")
        self.assertEqual(self.r.chats[-1], KARINE)

    def test_buttons(self):
        with Recorder() as rec:
            listener.handle_callback(self.cfg, self.r, "ui:price", KARINE, 7)
            listener.handle_callback(self.cfg, self.r, "ui:meals", KARINE, 7)
        self.assertEqual(rec.sent[-1][1]["chat_id"], KARINE)          # prompt
        self.assertEqual(rec.edited[-1][:2], (KARINE, 7))              # in-place edit
        listener.handle_callback(self.cfg, self.r, "cmd:scan", KARINE, 7)
        self.assertEqual(self.r.chats[-1], KARINE)

    def test_owner_default_unchanged(self):
        with Recorder() as rec:
            listener.handle_text(self.cfg, self.r, ui.KEY_HOME)
        self.assertIsNone(rec.sent[-1][1].get("chat_id"))             # -> owner's chat


class JobEnvironment(unittest.TestCase):
    def test_reply_jobs_carry_the_asker(self):
        for name in ("price", "flights", "stays"):
            env = listener.job_env(name, KARINE, base={})
            self.assertEqual(env[telegram.REPLY_CHAT_ENV], KARINE, name)

    def test_travel_scans_stay_with_the_owner(self):
        for name in ("scan", "digest"):
            self.assertNotIn(telegram.REPLY_CHAT_ENV, listener.job_env(name, KARINE, base={}), name)

    def test_no_asker_and_stale_value_removed(self):
        self.assertNotIn(telegram.REPLY_CHAT_ENV, listener.job_env("price", None, base={}))
        stale = {telegram.REPLY_CHAT_ENV: "999", "PATH": "x"}
        env = listener.job_env("scan", KARINE, base=stale)
        self.assertNotIn(telegram.REPLY_CHAT_ENV, env)
        self.assertEqual(env["PATH"], "x")


if __name__ == "__main__":
    unittest.main()
