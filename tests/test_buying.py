"""market/buying.py: the "How to buy" steps (docs/briefs/CROSS_BORDER.md X1).
Words come from market/buying.md; every number from the quote. The rejection paths: no row, a
broken file, a stale row, a forwarder with no published rule."""
import os
import tempfile
import unittest
from datetime import date

from market import buying

TODAY = date(2026, 11, 18)
DAYS_TRUCK = {"min": 12, "max": 20, "unit": "working"}
DAYS_AIR = {"min": 5, "max": 7, "unit": "working"}


def line(fw, mode, total, latest, customs=0.0, near=False, days=DAYS_TRUCK):
    return {"forwarder": fw, "mode": mode, "total_amd": total, "customs_amd": customs,
            "customs_near": near, "days": days,
            "arrival": {"earliest": latest, "latest": latest, "notes": []}}


TRUCK = line("onex", "truck", 5655.0, date(2026, 12, 9))
AIR = line("onex", "air", 7055.0, date(2026, 11, 27), days=DAYS_AIR)
ROWS = {"amazon_de": {"key": "amazon_de", "postcode": "82152"},
        "pinduoduo": {"key": "pinduoduo", "postcode": ""}}


class RealFile(unittest.TestCase):
    def test_the_committed_file_loads(self):
        d = buying.load()
        for k in ("pinduoduo", "taobao", "1688", "amazon_uk", "amazon_de", "amazon_it"):
            self.assertIn(k, d["stores"])
            self.assertIsNotNone(d["stores"][k]["checked_date"])
        self.assertEqual(len(d["restrict"]), 16)          # 4 forwarders x 4 items
        self.assertEqual({r["rule"] for r in d["restrict"]}, {"limited", "refused", "unknown"})

    def test_no_price_in_the_stores_table(self):
        # The file holds words; prices live in tariffs.json (buying.md header).
        for r in buying.load()["stores"].values():
            self.assertNotIn("AMD", r["pay"] + r["delivery"])
            self.assertGreater(len(r["watch"]), 10)       # a real sentence, not "Same"


class Steps(unittest.TestCase):
    def setUp(self):
        self.data = buying.load()

    def steps(self, lines, store="amazon_de", flags=(), today=TODAY, extra=()):
        return buying.how_to(self.data, store, {"lines": lines}, "€12.99",
                             "Amazon's delivery there: FREE delivery", flags=flags, extra=extra,
                             today=today, store_rows=ROWS)

    def test_order_and_words(self):
        s = self.steps([TRUCK, AIR])
        self.assertEqual(s[0], "Buy on amazon.de with your card — €12.99.")
        self.assertTrue(s[1].startswith("Deliver to your forwarder's Germany warehouse (82152)"))
        self.assertIn("Amazon's delivery there: FREE delivery.", s[1])
        self.assertIn("choose Onex truck — the cheapest, 5,655 AMD delivered", s[2])
        self.assertIn("12–20 wd", s[2])
        self.assertTrue(s[3].startswith("Faster: Onex air, +1,400 AMD, "))   # 7,055 - 5,655, in code
        self.assertEqual(s[4], "Customs: none (under €200 and 31 kg).")
        self.assertTrue(s[5].startswith("Check: "))

    def test_no_faster_line_when_the_cheapest_is_also_the_fastest(self):
        slow_air = line("onex", "air", 9000.0, date(2026, 12, 20), days=DAYS_AIR)
        s = self.steps([TRUCK, slow_air])
        self.assertFalse(any(x.startswith("Faster") for x in s))

    def test_unpriced_says_so_and_has_no_customs_line(self):
        s = self.steps([dict(TRUCK, total_amd=None, customs_amd=None)])
        self.assertIn("Shipping cannot be priced yet", s[2])
        self.assertFalse(any(x.startswith("Customs") for x in s))

    def test_customs_over_and_near(self):
        s = self.steps([dict(TRUCK, customs_amd=4200.0)])
        self.assertIn("Customs: about 4,200 AMD — over the €200 limit; already in the total.", s)
        s = self.steps([dict(TRUCK, customs_near=True)])
        self.assertTrue(any("Within 10% of €200" in x for x in s))

    def test_restrictions_unknown_refused_limited(self):
        s = self.steps([TRUCK], flags=["battery"])
        self.assertIn("⚠️ Battery: Onex publishes no rule — check with Onex before ordering.", s)
        g = line("globbing", "air", 5000.0, date(2026, 11, 30))
        s = self.steps([g], flags=["magnet", "battery"])
        self.assertTrue(any(x.startswith("⚠️ Magnets: Globbing does not take it") for x in s))
        self.assertTrue(any(x.startswith("⚠️ Battery: Globbing takes it only if") for x in s))

    def test_extra_lines_and_china_row(self):
        s = buying.how_to(self.data, "pinduoduo", {"lines": [TRUCK]}, "¥39.9",
                          "The seller's delivery there: free China delivery",
                          extra=["Minimum order: 2件."], today=TODAY, store_rows=ROWS)
        self.assertEqual(s[0], "Buy in the Pinduoduo app yourself — ¥39.9.")
        self.assertTrue(s[1].startswith("Deliver to your forwarder's China warehouse — "))  # no postcode
        self.assertIn("Minimum order: 2件.", s)
        self.assertTrue(any("拼单" in x for x in s))

    def test_store_without_a_row_gets_no_steps(self):
        self.assertEqual(buying.how_to(self.data, "wildberries", {"lines": [TRUCK]}, "₽1", "x"), [])

    def test_stale_row_is_shown_with_its_date(self):
        s = self.steps([TRUCK], today=date(2027, 6, 1))
        self.assertEqual(s[-1], "⚠️ Buying steps last checked on 2026-11-18.")
        self.assertFalse(any("last checked" in x for x in self.steps([TRUCK])))


class Broken(unittest.TestCase):
    def test_file_without_stores_table_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "buying.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write("# nothing\n\n## Other\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
            with self.assertRaises(ValueError):
                buying.load(p)

    def test_attach_with_a_broken_file_tells_every_result(self):
        orig = buying.load

        def broken(path=None):
            raise ValueError("no Stores table")
        buying.load = broken
        try:
            logs, offers = [], [{"site": "x"}, {"site": "y"}]
            buying.attach(offers, lambda *a: ["never"], TODAY, log=logs.append)
        finally:
            buying.load = orig
        self.assertEqual([o["how"] for o in offers],
                         [["How to buy is unavailable: market/buying.md could not be read."]] * 2)
        self.assertIn("no Stores table", logs[0])


if __name__ == "__main__":
    unittest.main()
