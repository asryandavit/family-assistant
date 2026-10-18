"""Tests for the /price Telegram message (lib/fmt_grocery.py), built from the
real captured payloads."""
import json
import os
import unittest

from lib import fmt_grocery, parse_grocery as pg

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "grocery")


def _items():
    with open(os.path.join(FIX, "parma_search_chicken.html"), encoding="utf-8") as f:
        parma = pg.parse_parma(f.read())
    with open(os.path.join(FIX, "yc_search_chicken.json"), encoding="utf-8") as f:
        yc = pg.parse_yc(json.load(f))
    return parma + yc


class Message(unittest.TestCase):
    def test_lists_cheapest_with_links_and_fits_telegram(self):
        ranked = pg.rank(_items(), "chicken breast", sort="cheap")
        msg = fmt_grocery.build("chicken breast", ranked, {"parma": "ok", "yc": "ok"})
        self.assertTrue(msg.startswith("\U0001f6d2 <b>chicken breast</b>"))
        # top 3 above the fold, the rest folded away
        above, _, folded = msg.partition("<blockquote expandable>")
        self.assertEqual(above.count('href="https://'), 3)
        self.assertIn("4. ", folded)
        self.assertTrue(folded.split("</blockquote>")[0])
        self.assertIn('href="https://', msg)
        self.assertIn("/kg", msg)
        self.assertLess(len(msg), 4096)
        self.assertNotIn("unavailable", msg)

    def test_weight_items_show_per_kg_and_minimum(self):
        parma = [i for i in _items() if i["shop"] == "parma"]
        line = fmt_grocery._line(1, parma[0])
        self.assertIn("3,000 ֏/kg", line)
        self.assertIn("min 0.5 kg", line)

    def test_discount_shows_old_price(self):
        with open(os.path.join(FIX, "yc_discounted_yogurt.json"), encoding="utf-8") as f:
            y = pg.parse_yc(json.load(f))[0]
        line = fmt_grocery._line(1, y)
        self.assertIn("<b>320 ֏</b>", line)
        self.assertIn("<s>390</s>", line)
        self.assertIn("−17.9%", line)

    def test_shop_failure_is_reported_not_hidden(self):
        ranked = pg.rank([i for i in _items() if i["shop"] == "yc"], "chicken", sort="cheap")
        msg = fmt_grocery.build("chicken", ranked, {"parma": "error: timeout", "yc": "ok"})
        self.assertIn("Parma unavailable this run", msg)

    def test_no_match_gives_a_hint(self):
        msg = fmt_grocery.build("unicorn steak", [], {"parma": "ok", "yc": "ok"})
        self.assertIn("Nothing matched", msg)
        self.assertIn("/price lentils", msg)

    def test_names_are_html_escaped(self):
        item = dict(_items()[0], name='Milk <b>"x" & y</b>')
        line = fmt_grocery._line(1, item)
        self.assertIn("&lt;b&gt;", line)
        self.assertNotIn("<b>\"x\"", line)


if __name__ == "__main__":
    unittest.main()
