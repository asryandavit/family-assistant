"""lib/ui.py (template + Home screens) and the additive lib/telegram.py helpers.
Offline: builds payloads and text, sends nothing."""
import json
import os
import re
import unittest
from datetime import datetime

from lib import telegram, ui

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _all_buttons(rows):
    return [b for row in rows for b in row]


class Template(unittest.TestCase):
    def test_header_escapes_and_formats(self):
        self.assertEqual(ui.header("X", "A&B", "ctx", "sub"),
                         "X <b>A&amp;B</b> · <i>ctx</i>\n<i>sub</i>")
        self.assertEqual(ui.header("X", "T"), "X <b>T</b>")

    def test_fold(self):
        self.assertEqual(ui.fold([]), "")
        self.assertEqual(ui.fold(["", None]), "")
        f = ui.fold(["a", "b"], "More")
        self.assertTrue(f.startswith("<blockquote expandable><b>More</b>\na"))
        self.assertTrue(f.endswith("b</blockquote>"))

    def test_page(self):
        p = ui.page("H", ["x", None, "y"], ui.fold(["z"]), "foot")
        self.assertEqual(p.split("\n")[0], "H")
        self.assertIn("x\ny\n<blockquote expandable>z</blockquote>", p)
        self.assertTrue(p.endswith("foot"))

    def test_day_label_and_timezone(self):
        self.assertEqual(ui.day_label(datetime(2026, 10, 5, 9, tzinfo=ui.YEREVAN)), "Mon 5 Oct")
        self.assertEqual(ui.now_local().utcoffset().total_seconds(), 4 * 3600)


class Screens(unittest.TestCase):
    def test_home_has_six_sections(self):
        text, rows = ui.home(ROOT, running="scan", travel_next="19.10 08:00")
        self.assertIn("Family assistant", text)
        self.assertIn("Running now: <b>scan</b>", text)
        self.assertIn("19.10 08:00", text)
        data = [d for _, d in _all_buttons(rows)]
        self.assertEqual(data, ["ui:" + s for s in ui.SECTIONS])

    def test_every_section_has_home_and_valid_buttons(self):
        for name in ui.SECTIONS:
            text, rows = ui.section(name, ROOT)
            self.assertLess(len(text), 4096, name)
            self.assertEqual(rows[-1], [ui.HOME_BACK], name)
            for label, data in _all_buttons(rows):
                self.assertTrue(label, name)
                if data.startswith("https://"):
                    continue
                self.assertLessEqual(len(data.encode("utf-8")), 64, (name, data))
                self.assertRegex(data, r"^(ui|cmd):[a-z]+$", (name, data))

    def test_plan_sections_link_to_drive(self):
        _, rows = ui.section("meals", ROOT)
        urls = [d for _, d in _all_buttons(rows) if d.startswith("https://")]
        self.assertTrue(urls)
        self.assertTrue(all("docs.google.com" in u for u in urls))

    def test_missing_config_drops_link_buttons_not_the_screen(self):
        text, rows = ui.section("training", os.path.join(ROOT, "no-such-dir"))
        self.assertEqual(rows, [[ui.HOME_BACK]])
        self.assertIn("Training", text)

    def test_unknown_section(self):
        self.assertIsNone(ui.section("nope", ROOT))


class TelegramHelpers(unittest.TestCase):
    def test_button_kinds(self):
        self.assertEqual(telegram._button("A", "ui:home"), {"text": "A", "callback_data": "ui:home"})
        self.assertEqual(telegram._button("B", "https://x.am"), {"text": "B", "url": "https://x.am"})

    def test_reply_markup_kinds_and_precedence(self):
        self.assertIsNone(telegram.reply_markup())
        inline = json.loads(telegram.reply_markup([[("A", "cmd:scan"), ("L", "https://a.b")]]))
        self.assertEqual(inline["inline_keyboard"][0][1], {"text": "L", "url": "https://a.b"})
        kb = json.loads(telegram.reply_markup(reply_keyboard=ui.BOTTOM_KEYBOARD))
        self.assertEqual(kb["keyboard"], [[{"text": ui.KEY_HOME}, {"text": ui.KEY_PRICE}]])
        self.assertTrue(kb["is_persistent"] and kb["resize_keyboard"])
        fr = json.loads(telegram.reply_markup(force_reply=ui.PRICE_PLACEHOLDER))
        self.assertEqual(fr, {"force_reply": True, "input_field_placeholder": ui.PRICE_PLACEHOLDER})
        # inline buttons win when several are given
        both = json.loads(telegram.reply_markup([[("A", "cmd:scan")]], ui.BOTTOM_KEYBOARD, "x"))
        self.assertIn("inline_keyboard", both)

    def test_existing_callers_unchanged(self):
        # old-style rows of (label, callback_data) produce the same JSON as before
        old = json.dumps({"inline_keyboard": [[{"text": "A", "callback_data": "st:T1:LCA"}]]})
        self.assertEqual(telegram._markup([[("A", "st:T1:LCA")]]), old)
        self.assertEqual(telegram.reply_markup([[("A", "st:T1:LCA")]]), old)

    def test_split_keeps_folded_blocks_valid(self):
        body = "\n".join("line %04d %s" % (i, "x" * 60) for i in range(150))
        text = "head\n" + ui.fold(body.split("\n"), "Details") + "\ntail"
        chunks = telegram._split(text)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(len(c), telegram.LIMIT)
            opens = len(re.findall(r"<blockquote[^>]*>", c))
            closes = c.count("</blockquote>")
            self.assertEqual(opens, closes, c[:80])
        self.assertTrue(chunks[0].startswith("head"))
        self.assertTrue(chunks[-1].endswith("tail"))

    def test_split_short_text_untouched(self):
        self.assertEqual(telegram._split("hello"), ["hello"])


if __name__ == "__main__":
    unittest.main()
