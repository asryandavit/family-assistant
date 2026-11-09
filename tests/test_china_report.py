"""china/report.py: the rich and plain answers from real (P0-derived) results."""
import json
import os
import re
import unittest
from datetime import date

from china import pricing, report, validate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = os.path.join(ROOT, "tests", "fixtures", "china")
with open(os.path.join(ROOT, "market", "tariffs.json"), encoding="utf-8") as f:
    ROUTES = json.load(f)["routes"]
with open(os.path.join(ROOT, "config_china.json"), encoding="utf-8") as f:
    CFG = json.load(f)
RATES = {"date": "2026-10-30", "amd_per": {"USD": 360.14, "EUR": 403.36, "CNY": 54.132}}


def build(**kw):
    with open(os.path.join(F, "answer_pinduoduo_contract.json"), encoding="utf-8") as f:
        d = json.load(f)
    d.pop("_source")
    a = validate.answer(d, "pinduoduo")
    priced = [pricing.price_result(r, ROUTES, RATES, date(2026, 11, 9), CFG) for r in a["results"]]
    ranked = pricing.rank(priced, 5)
    sites = [{"site": "pinduoduo", "status": "ok", "ranked": ranked},
             {"site": "taobao", "status": "login", "ranked": []},
             {"site": "1688", "status": "check", "notice": "访问异常 <script>", "ranked": []}]
    pick, why = pricing.best_pick(ranked, 25)
    args = dict(job="j1", query="GaN charger 65W, EU plug", sites=sites, pick=pick, reason=why,
                groups=[], rates=RATES, tariffs_date="2026-10-29", category="electronics")
    args.update(kw)
    return report.build(**args), ranked


class Rich(unittest.TestCase):
    def setUp(self):
        (self.rich, self.plain, self.btns), self.ranked = build()

    def test_limits(self):
        self.assertTrue(report.fits(self.rich))
        self.assertNotIn("\n", self.rich)                       # newline would be a space

    def test_tables_have_four_columns(self):
        for row in re.findall(r"<tr>(.*?)</tr>", self.rich):
            self.assertEqual(len(re.findall(r"<t[hd]", row)), 4, row)

    def test_numbers_come_from_pricing(self):
        p = self.ranked[0]
        self.assertIn("{:,.0f}".format(round(p["total_amd"])), self.rich)
        self.assertIn("{:,.0f}".format(round(p["total_amd"])), self.plain)

    def test_weight_warning_uppercase(self):
        self.assertIn("SHIPPING ESTIMATED FOR 1 KG — WEIGHT NOT LISTED", self.rich)
        self.assertIn("有欧标插头吗", self.rich)                 # electronics -> EU plug question

    def test_blocked_sites_named_with_search_link(self):
        self.assertIn("Taobao logged out — open Chrome on the PC and sign in", self.rich)
        self.assertIn("1688 showed a check page", self.rich)
        self.assertIn("&lt;script&gt;", self.rich)             # model/page text escaped
        self.assertIn("https://s.taobao.com/search?q=GaN", self.rich)

    def test_suspicious_shown_in_table_details_and_plain(self):
        self.assertNotIn("SUSPICIOUSLY CHEAP", self.rich)
        self.ranked[1]["suspicious"] = True
        rich, plain, _ = report.build("j1", "GaN", [{"site": "pinduoduo", "status": "ok",
                                                      "ranked": self.ranked}],
                                      self.ranked[0], "x", [], RATES, "2026-10-29", "electronics")
        self.assertIn("SUSPICIOUSLY CHEAP", rich)
        self.assertIn("⚠️ suspiciously cheap: far below the other listings", rich)
        self.assertIn("⚠️ suspiciously cheap", plain)
        self.assertTrue(report.fits(rich))

    def test_pdd_group_price_note(self):
        self.assertIn("single-buy price is only in the PDD app", self.rich)

    def test_buttons(self):
        datas = [d for row in self.btns for _, d in row]
        self.assertIn("cn:only:taobao:j1", datas)
        self.assertTrue(all(len(d.encode()) <= 64 for d in datas))
        self.assertIn('data="cn:watch:j1:1"', self.rich)
        self.assertNotIn("callback_data=", self.rich)
        self.assertFalse(any(d.startswith("cn:rev") for d in datas))   # all 3 had reviews read

    def test_links_only_built(self):
        hrefs = re.findall(r'href="([^"]+)"', self.rich)
        self.assertTrue(hrefs)
        for h in hrefs:
            self.assertTrue(h.startswith(("https://mobile.yangkeduo.com/", "https://s.taobao.com/",
                                          "https://s.1688.com/")), h)

    def test_plain_uses_expandable_folds(self):
        self.assertIn("<blockquote expandable>", self.plain)
        self.assertNotIn("<details>", self.plain)
        self.assertNotIn("<br>", self.plain)

    def test_poizon_only_for_clothes(self):
        self.assertNotIn("Poizon", self.rich)
        (rich, _, _), _ = build(category="shoes")
        self.assertIn("Poizon", rich)


if __name__ == "__main__":
    unittest.main()
