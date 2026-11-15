"""listener.py routes /list and gl:… buttons to shopping/bot.py (decision 106); a fault
there answers with a sentence instead of taking the listener down. Nothing is sent."""
import unittest
from unittest import mock

import listener
from lib import config, ui
from shopping import bot
from tests.test_listener_ux import FakeRunner


class Routing(unittest.TestCase):
    def setUp(self):
        self.cfg, self.r = config.load(), FakeRunner()

    def test_list_command_goes_to_the_tick_list(self):
        with mock.patch.object(bot, "handle", return_value=None) as h:
            self.assertIsNone(listener.handle_text(self.cfg, self.r, "/list monthly", "222"))
        h.assert_called_once_with(self.cfg, listener.ROOT, "/list monthly", "222")

    def test_gl_buttons_carry_chat_and_message(self):
        with mock.patch.object(bot, "callback", return_value=None) as c:
            self.assertIsNone(listener.handle_callback(self.cfg, self.r, "gl:t:w:abc123:4", "111", 77))
        c.assert_called_once_with(self.cfg, listener.ROOT, "gl:t:w:abc123:4", "111", 77)

    def test_a_fault_is_a_sentence(self):
        with mock.patch.object(bot, "callback", side_effect=RuntimeError("disk")):
            out = listener.handle_callback(self.cfg, self.r, "gl:v:w", "111", 77)
        self.assertIn("tick list is unavailable", out)

    def test_shopping_section_offers_the_tick_list(self):
        _, rows = ui.section("shop", listener.ROOT)
        self.assertIn((ui.TICK_LIST_BUTTON, "gl:o:w"), [b for row in rows for b in row])

    def test_list_in_menu_and_help(self):
        self.assertIn("/list", listener.HELP)


if __name__ == "__main__":
    unittest.main()
