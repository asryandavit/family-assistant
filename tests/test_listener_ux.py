"""Home screen, bottom keyboard, Price check prompt and ui: navigation in
listener.py. Telegram calls and the Windows task query are stubbed: nothing is
sent and no scheduled task is touched."""
import unittest

import listener
from lib import config, telegram, ui


class FakeRunner:
    current = None

    def __init__(self):
        self.calls = []

    def launch(self, name, extra_args=None, ack=None, chat_id=None):
        self.calls.append((name, list(extra_args or []), ack))
        self.chats = getattr(self, "chats", []) + [chat_id]
        return "launched " + name

    def cancel(self):
        return "cancelled"


class Recorder:
    """Swap telegram.send_html / edit_html for recorders during a test."""

    def __init__(self):
        self.sent, self.edited = [], []

    def __enter__(self):
        self._send, self._edit = telegram.send_html, telegram.edit_html
        self._next = listener._travel_next
        telegram.send_html = lambda cfg, text, **kw: self.sent.append((text, kw))
        telegram.edit_html = lambda cfg, chat, mid, text, buttons=None: self.edited.append(
            (chat, mid, text, buttons))
        listener._travel_next = lambda: "19.10 08:00"
        return self

    def __exit__(self, *exc):
        telegram.send_html, telegram.edit_html = self._send, self._edit
        listener._travel_next = self._next


class ReplyRouting(unittest.TestCase):
    def test_answer_to_price_prompt_becomes_price_command(self):
        prompt_text = "\U0001f50d Which product?\nType it below, in English or Armenian"
        self.assertEqual(listener.route_reply("lentils", prompt_text), "/price lentils")
        self.assertEqual(listener.route_reply("  ոսպ ", prompt_text), "/price ոսպ")

    def test_other_messages_untouched(self):
        self.assertEqual(listener.route_reply("lentils", None), "lentils")
        self.assertEqual(listener.route_reply("lentils", "some other message"), "lentils")
        prompt_text = "\U0001f50d Which product?"
        self.assertEqual(listener.route_reply("/scan", prompt_text), "/scan")
        self.assertEqual(listener.route_reply("", prompt_text), "")


class KeysAndCommands(unittest.TestCase):
    def setUp(self):
        self.cfg, self.r = config.load(), FakeRunner()

    def test_home_key_sends_home(self):
        with Recorder() as rec:
            out = listener.handle_text(self.cfg, self.r, ui.KEY_HOME)
        self.assertIsNone(out)
        text, kw = rec.sent[-1]
        self.assertIn("Family assistant", text)
        self.assertIn("19.10 08:00", text)
        self.assertEqual(kw["buttons"][0][0][1], "ui:today")
        self.assertTrue(kw["silent"])

    def test_price_key_opens_prompt(self):
        with Recorder() as rec:
            listener.handle_text(self.cfg, self.r, ui.KEY_PRICE)
        text, kw = rec.sent[-1]
        self.assertIn(ui.PRICE_PROMPT_MARK, text)
        self.assertEqual(kw["force_reply"], ui.PRICE_PLACEHOLDER)

    def test_start_attaches_keyboard_then_home(self):
        with Recorder() as rec:
            listener.handle_text(self.cfg, self.r, "/start")
        self.assertEqual(len(rec.sent), 2)
        self.assertEqual(rec.sent[0][1]["reply_keyboard"], ui.BOTTOM_KEYBOARD)
        self.assertIn("Family assistant", rec.sent[1][0])

    def test_menu_shows_home(self):
        with Recorder() as rec:
            listener.handle_text(self.cfg, self.r, "/menu")
        self.assertIn("Family assistant", rec.sent[-1][0])

    def test_help_mentions_keys_and_commands(self):
        out = listener.handle_text(self.cfg, self.r, "/help")
        self.assertIn("Home", out)
        for c in ("/price", "/flights", "/stays", "/scan", "/menu"):
            self.assertIn(c, out)


class Navigation(unittest.TestCase):
    def setUp(self):
        self.cfg, self.r = config.load(), FakeRunner()

    def test_sections_edit_in_place(self):
        for name in ui.SECTIONS:
            with Recorder() as rec:
                out = listener.handle_callback(self.cfg, self.r, "ui:" + name, "123", 45)
            self.assertIsNone(out, name)
            self.assertEqual(len(rec.edited), 1, name)
            chat, mid, text, buttons = rec.edited[0]
            self.assertEqual((chat, mid), ("123", 45))
            self.assertEqual(buttons[-1], [ui.HOME_BACK], name)
            self.assertFalse(rec.sent, name)

    def test_home_and_help_edit_in_place(self):
        with Recorder() as rec:
            listener.handle_callback(self.cfg, self.r, "ui:home", "123", 45)
            listener.handle_callback(self.cfg, self.r, "ui:help", "123", 45)
        self.assertIn("Family assistant", rec.edited[0][2])
        self.assertIn("/price", rec.edited[1][2])

    def test_price_button_opens_prompt(self):
        with Recorder() as rec:
            listener.handle_callback(self.cfg, self.r, "ui:price", "123", 45)
        self.assertEqual(rec.sent[-1][1]["force_reply"], ui.PRICE_PLACEHOLDER)

    def test_unknown_section(self):
        with Recorder():
            self.assertEqual(listener.handle_callback(self.cfg, self.r, "ui:nope", "1", 2),
                             "Unrecognised button.")

    def test_old_cmd_buttons_still_work(self):
        # buttons in messages sent before this change carry cmd: data
        out = listener.handle_callback(self.cfg, self.r, "cmd:scan", "1", 2)
        self.assertEqual(out, "launched scan")
        self.assertEqual(self.r.calls[-1][0], "scan")


if __name__ == "__main__":
    unittest.main()
