"""china/pricing.py: hand-checked totals on the stored tariffs (market/tariffs.json, read
2026-10-29) and a fixed CBA rate set (the 2026-10-30 CBA answer)."""
import copy
import json
import os
import unittest
from datetime import date

from china import parse, pricing, trust, validate

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


def mk(base, **kw):
    """A priced result with only the fields ranking reads replaced."""
    d = dict(base, promo="", suspicious=False, marks=[], badges=[], specs={}, sales=None,
             reviews=None, rating_text=None, complaint_types=[], spec_mismatch=False,
             reviews_read=False)
    d.update(kw)
    return d


class Ranking(unittest.TestCase):
    """Owner, 2026-11-09: the best and most trustworthy product first, price second."""

    def setUp(self):
        self.p = pricing.apply_trust([priced(r) for r in results()], "electronics")
        self.base = self.p[1]

    def test_trust_before_price(self):
        cheap = mk(self.base, id="1", seller=parse.UNMARKED, total_amd=3000.0)
        good = mk(self.base, id="2", seller=parse.OFFICIAL, total_amd=12000.0)
        ranked = pricing.rank(pricing.apply_trust([cheap, good]), 5)
        self.assertEqual([x["id"] for x in ranked], ["2", "1"])
        self.assertIs(pricing.best_pick([cheap, good])[0], good)

    def test_price_breaks_ties_within_a_band(self):
        a = mk(self.base, id="1", seller=parse.AUTHORISED, total_amd=9000.0)
        b = mk(self.base, id="2", seller=parse.AUTHORISED, total_amd=7000.0)
        pricing.apply_trust([a, b])
        self.assertEqual([x["id"] for x in pricing.rank([a, b], 5)], ["2", "1"])
        pick, why = pricing.best_pick([a, b])
        self.assertIs(pick, b)
        self.assertIn("the cheapest of 2 equally trusted", why)

    def test_reviews_and_sales_outrank_a_bare_listing(self):
        bare = mk(self.base, id="1", seller=parse.AUTHORISED, total_amd=7000.0)
        proven = mk(self.base, id="2", seller=parse.AUTHORISED, total_amd=9000.0, sales=50000,
                    reviews=2321, rating_text="好评率99%", reviews_read=True)
        pricing.apply_trust([bare, proven])
        pick, why = pricing.best_pick([bare, proven])
        self.assertIs(pick, proven)
        self.assertIn("2,321 reviews", why)
        self.assertIn("99% positive", why)
        self.assertIn("no serious complaints", why)

    def test_serious_complaints_sink_an_official_store(self):
        bad = mk(self.base, id="1", seller=parse.OFFICIAL, total_amd=8000.0,
                 complaint_types=["fake", "broken"], reviews_read=True)
        ok = mk(self.base, id="2", seller=parse.AUTHORISED, total_amd=9000.0, reviews_read=True)
        pricing.apply_trust([bad, ok])
        self.assertIs(pricing.best_pick([bad, ok])[0], ok)
        self.assertIn("complaints: fake", trust.reason(bad))

    def test_unpriced_last(self):
        none = mk(self.base, id="1", seller=parse.OFFICIAL, total_amd=None)
        some = mk(self.base, id="2", seller=parse.UNMARKED, total_amd=5000.0)
        pricing.apply_trust([none, some])
        self.assertEqual([x["id"] for x in pricing.rank([none, some], 5)], ["2", "1"])
        self.assertEqual(pricing.best_pick([none]), (None, ""))

    def test_promo_prices_never_picked(self):
        first_item = next(x for x in self.p if x["id"] == "987289867285")   # 首件¥89.9
        self.assertEqual(first_item["promo"], "first-item price")
        self.assertIsNot(pricing.best_pick(self.p)[0], first_item)
        self.assertIn(first_item, pricing.rank(self.p, 5))                 # still shown
        self.assertEqual(pricing.best_pick([first_item]), (None, ""))


class LiveDemo(unittest.TestCase):
    """Phone demo 2026-11-09 (/china GaN charger 65W EU plug): a no-name 1688 "65W" charger at
    ¥23.85 (1,888 AMD with shipping) was picked over brand-authorised Ugreen at ¥159."""

    def setUp(self):
        with open(os.path.join(F, "answer_1688_live.json"), encoding="utf-8") as f:
            d = json.load(f)
        d.pop("_source")
        self.ali = [priced(r) for r in validate.answer(d, "1688")["results"]]
        self.pdd = [priced(r) for r in results()]
        self.all = self.pdd + self.ali
        pricing.mark_suspicious(self.all, CFG["suspicious_ratio"])
        pricing.apply_trust(self.all, "electronics")

    def test_picks_the_brand(self):
        pick, why = pricing.best_pick(self.all)
        self.assertEqual(pick["seller"], parse.AUTHORISED)
        self.assertEqual(pick["site"], "pinduoduo")
        self.assertIn("brand-authorised", why)

    def test_no_name_is_suspicious_and_last(self):
        cheap = next(p for p in self.ali if p["id"] == "1089369915475")       # ¥23.85
        self.assertTrue(cheap["suspicious"])
        self.assertFalse(any(p["suspicious"] for p in self.pdd))
        self.assertIs(pricing.rank(self.all, 10)[-1], cheap)

    def test_suspicious_needs_three_prices(self):
        xs = [dict(self.pdd[1], price_amd=v, promo="") for v in (100.0, 9000.0)]
        pricing.mark_suspicious(xs, 0.25)
        self.assertFalse(any(x["suspicious"] for x in xs))

    def test_suspicious_never_picked(self):
        xs = [mk(self.pdd[1], id=str(i), seller=parse.OFFICIAL, price_amd=v, total_amd=v + 1500)
              for i, v in enumerate([1000.0, 8000.0, 8500.0, 9000.0])]
        pricing.mark_suspicious(xs, 0.25)
        self.assertEqual([x["suspicious"] for x in xs], [True, False, False, False])
        pricing.apply_trust(xs)
        self.assertEqual(pricing.best_pick(xs)[0]["price_amd"], 8000.0)


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
