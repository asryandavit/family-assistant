"""lib/telegram._button: the additive web_app kind (docs/briefs/MINI_APP.md §7) next to the
two existing kinds, which must come out exactly as before."""
import json
import unittest

from lib import telegram


class Buttons(unittest.TestCase):
    def test_callback_unchanged(self):
        self.assertEqual(telegram._button("Go", "ui:home"),
                         {"text": "Go", "callback_data": "ui:home"})

    def test_url_unchanged(self):
        self.assertEqual(telegram._button("Site", "https://example.com/x"),
                         {"text": "Site", "url": "https://example.com/x"})

    def test_web_app(self):
        self.assertEqual(telegram._button("📱 Open", {"web_app": "https://app.example/"}),
                         {"text": "📱 Open", "web_app": {"url": "https://app.example/"}})

    def test_mixed_row_in_markup(self):
        m = json.loads(telegram.reply_markup(buttons=[[("A", "cb:1"),
                                                       ("📱 Open", {"web_app": "https://a.b/"})]]))
        self.assertEqual(m["inline_keyboard"][0],
                         [{"text": "A", "callback_data": "cb:1"},
                          {"text": "📱 Open", "web_app": {"url": "https://a.b/"}}])


if __name__ == "__main__":
    unittest.main()
