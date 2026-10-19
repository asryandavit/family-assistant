"""🧺 Basket in the Shopping section and /basket in listener.py (decision 084).
The ack answers the asker; the result is family content the job sends to both
chats itself, so the job never gets the asker's reply chat. Nothing is sent."""
import os
import unittest

import listener
from lib import config, telegram, ui
from tests.test_listener_ux import FakeRunner, Recorder

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KARINE = "222"


class ShoppingSection(unittest.TestCase):
    def test_basket_and_checklist_buttons(self):
        text, rows = ui.section("shop", ROOT)
        flat = [b for row in rows for b in row]
        self.assertIn((ui.BASKET_BUTTON, "cmd:basket"), flat)
        self.assertIn((ui.KEY_PRICE, "ui:price"), flat)
        links = dict(flat)
        self.assertTrue(links["\U0001f4cb Checklist"].startswith("https://docs.google.com/spreadsheets/d/"))
        self.assertIn("Basket", text)
        self.assertEqual(rows[-1], [ui.HOME_BACK])
        for _, data in flat:
            if not data.startswith("https://"):
                self.assertLessEqual(len(data.encode()), 64)

    def test_no_checklist_link_without_sheet_id(self):
        self.assertIsNone(ui.checklist_url(os.path.join(ROOT, "no-such-folder")))


class BasketCommand(unittest.TestCase):
    def setUp(self):
        self.cfg, self.r = config.load(), FakeRunner()

    def test_button_launches_weekly_for_the_asker(self):
        out = listener.handle_callback(self.cfg, self.r, "cmd:basket", KARINE, 9)
        self.assertEqual(out, "launched basket")
        self.assertEqual(self.r.calls[-1][:2], ("basket", []))
        self.assertEqual(self.r.chats[-1], KARINE)
        self.assertIn("--send", listener.JOBS["basket"]["args"])

    def test_typed_shortcut(self):
        for text, flag in (("/basket", "--weekly"), ("/basket weekly", "--weekly"),
                           ("/basket MONTHLY", "--monthly"), ("/basket all", "--all")):
            out = listener.handle_text(self.cfg, self.r, text, KARINE)
            self.assertEqual(out, "launched basket", text)
            self.assertEqual(self.r.calls[-1][1], [flag], text)
            self.assertIn("both of you", self.r.calls[-1][2])
            self.assertEqual(self.r.chats[-1], KARINE)

    def test_anything_else_is_refused(self):
        for text in ("/basket yearly", "/basket weekly monthly", "/basket --all", "/basket ; rm"):
            out = listener.handle_text(self.cfg, self.r, text, KARINE)
            self.assertIn("/basket monthly", out, text)
        self.assertEqual(self.r.calls, [])

    def test_result_is_family_content_not_a_reply(self):
        self.assertNotIn("basket", listener.REPLY_JOBS)
        env = listener.job_env("basket", KARINE, base={telegram.REPLY_CHAT_ENV: "999"})
        self.assertNotIn(telegram.REPLY_CHAT_ENV, env)

    def test_help_and_menu(self):
        self.assertIn("/basket", listener.HELP)
        with Recorder():
            out = listener.handle_text(self.cfg, self.r, "/help", KARINE)
        self.assertIn("/basket [monthly|all]", out)


if __name__ == "__main__":
    unittest.main()
