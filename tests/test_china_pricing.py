"""china/pricing.py: hand-checked totals on the stored tariffs (market/tariffs.json, read
2026-10-29) and a fixed CBA rate set (the 2026-10-30 CBA answer)."""
import copy
import json
import os
import unittest
from datetime import date

from china import parse, pricing, validate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = os.path.join(ROOT, "tests", "fixtures", "china")
with open(os.path.join(ROOT, "market", "tariffs.json"), encoding="utf-8") as f:
    ROUTES = json.load(f)["routes"]
with open(os.path.join(ROOT, "config_china.json"), encoding="utf-8") as f:
    CFG = json.load(f)
RATES = {"date": "2026-10-30", "amd_per": {"USD": 360.14, "EUR": 403.36, "CNY": 54.132}}
TODAY = date(2026, 11, 9)


def results():
    with open(os.path.join(F, "answer_pinduoduo_contract.json"), encoding="utf-8") as f:
        d = json.load(f)
    d.pop("_source")
    return validate.answer(d, "pinduoduo")["results"]


def priced(r):
    return pricing.price_result(r, ROUTES, RATES, TODAY, CFG)


class OneResult(unittest.TestCase):
    def test_no_weight_uses_1kg_and_says_so(self):
        p = priced(results()[1])                 # ¥159, no weight on the page
        self.assertEqual(p["price"], 159.0)
        self.assertTrue(p["weight_assumed"])
        self.assertEqual(p["kg"], 1.0)
        self.assertAlmostEqual(p["price_amd"], 159 * 54.132, places=2)
        # cheapest 1 kg route: EasyTrans truck 1,500 (min 1,500) = Onex sea 1,500 (min)
        self.assertAlmostEqual(p["best"]["ship_amd"], 1500.0, places=2)
        self.assertAlmostEqual(p["total_amd"], 159 * 54.132 + 1500, places=2)
        self.assertAlmostEqual(p["total_usd"], (159 * 54.132 + 1500) / 360.14, places=4)
        self.assertEqual(p["best"]["customs_amd"], 0.0)   # ~€21, far under €200

    def test_only_configured_routes(self):
        p = priced(results()[1])
        got = {(ln["forwarder"], ln["mode"]) for ln in p["quote"]["lines"]}
        self.assertEqual(got, {tuple(x) for x in CFG["routes"]})
        self.assertNotIn(("onex", "truck"), got)

    def test_weight_from_page(self):
        r = dict(results()[1], weight_text="重量180g")
        p = priced(r)
        self.assertFalse(p["weight_assumed"])
        self.assertEqual(p["kg"], 0.18)
        bfy = next(ln for ln in p["quote"]["lines"] if ln["forwarder"] == "buyforyou")
        self.assertEqual(bfy["ship_amd"], 900.0)  # 4,900/kg × 0.18 = 882 → rounded up to 100

    def test_price_not_read_gives_no_total(self):
        p = priced(dict(results()[1], price_text="see page"))
        self.assertIsNone(p["price"])
        self.assertIsNone(p["total_amd"])

    def test_usd_price_on_1688(self):
        r = dict(results()[1], site="1688", price_text="$12.50")
        p = priced(r)
        self.assertEqual(p["currency"], "USD")
        self.assertAlmostEqual(p["price_amd"], 12.5 * 360.14, places=2)

    def test_customs_over_200_eur(self):
        p = priced(dict(results()[1], price_text="¥2000"))  # 108,264 AMD ≈ €268
        ln = next(x for x in p["quote"]["lines"] if x["forwarder"] == "onex" and x["mode"] == "air")
        value_eur = 2000 * 54.132 / 403.36
        self.assertAlmostEqual(ln["customs_amd"], (value_eur - 200) * 0.15 * 403.36, places=1)

    def test_seller_and_link(self):
        p = priced(results()[0])
        self.assertEqual(p["seller"], parse.AUTHORISED)          # 绿联赛文斯专卖店
        self.assertEqual(p["link"], "https://mobile.yangkeduo.com/goods.html?goods_id=616805280700")
        self.assertEqual(p["reviews"], 274)


class Delivery(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(pricing.delivery_cny("包邮", "pinduoduo")[0], 0.0)
        self.assertEqual(pricing.delivery_cny("运费¥8", "taobao")[0], 8.0)
        self.assertIsNone(pricing.delivery_cny("Shipping cost¥4Start", "1688")[0])
        self.assertIsNone(pricing.delivery_cny(None, "taobao")[0])
        self.assertIsNone(pricing.delivery_cny("48小时内发货", "pinduoduo")[0])  # unknown, not free

    def test_unknown_delivery_named_in_notes(self):
        p = priced(results()[1])
        self.assertIn("store delivery China delivery not shown", p["quote"]["notes"])


class Ranking(unittest.TestCase):
    def setUp(self):
        self.p = [priced(r) for r in results()]

    def test_rank_cheapest_first(self):
        ranked = pricing.rank(self.p, 5)
        totals = [x["total_amd"] for x in ranked]
        self.assertEqual(totals, sorted(totals))
        self.assertEqual(ranked[0]["id"], "987289867285")        # 首件¥89.9

    def test_best_pick_prefers_trusted_within_pct(self):
        pick, why = pricing.best_pick(self.p, 25)
        self.assertEqual(pick["seller"], parse.AUTHORISED)
        self.assertIn("cheapest", why)

    def test_best_pick_falls_back_to_cheapest(self):
        p = copy.deepcopy(self.p)
        for x in p:
            x["seller"] = parse.UNMARKED
        pick, why = pricing.best_pick(p, 25)
        self.assertEqual(pick["total_amd"], min(x["total_amd"] for x in p))
        self.assertIn("no official or authorised", why)

    def test_trusted_too_expensive_loses(self):
        a = dict(self.p[0], total_amd=10000.0, seller=parse.UNMARKED)
        b = dict(self.p[1], total_amd=13000.0, seller=parse.OFFICIAL)   # +30% > 25%
        self.assertIs(pricing.best_pick([a, b], 25)[0], a)
        c = dict(b, total_amd=12000.0)                                  # +20%
        self.assertIs(pricing.best_pick([a, c], 25)[0], c)

    def test_nothing_priced(self):
        self.assertEqual(pricing.best_pick([dict(self.p[0], total_amd=None)], 25), (None, ""))


class SameProduct(unittest.TestCase):
    def test_groups_across_sites_only(self):
        a = {"site": "pinduoduo", "title_en": "UGREEN 65W GaN charger Nexode 3 ports"}
        b = {"site": "taobao", "title_en": "Ugreen Nexode 65W GaN charger, 3 ports"}
        c = {"site": "pinduoduo", "title_en": "UGREEN 65W GaN charger Nexode 3 ports"}
        d = {"site": "1688", "title_en": "Anker 140W charger"}
        g = pricing.same_product([a, b, c, d])
        self.assertEqual(len(g), 1)
        self.assertEqual({x["site"] for x in g[0]}, {"pinduoduo", "taobao"})


class Parcel(unittest.TestCase):
    def test_two_items_cross_the_limit_together(self):
        route = next(r for r in ROUTES if r["forwarder"] == "onex" and r["mode"] == "air")
        items = [{"value_eur": 120.0, "kg": 0.5}, {"value_eur": 110.0, "kg": 0.4}]
        c = pricing.parcel_customs(items, route, RATES)
        self.assertAlmostEqual(c["eur"], 30 * 0.15, places=6)            # €230 → 15% of €30
        self.assertAlmostEqual(c["amd"], 30 * 0.15 * 403.36, places=4)
        self.assertIsNone(pricing.parcel_customs([{"value_eur": None, "kg": 1}], route, RATES))


if __name__ == "__main__":
    unittest.main()
