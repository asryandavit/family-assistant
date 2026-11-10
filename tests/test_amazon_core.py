"""amazon/trust.py, pricing.py, validate.py, runner.py, limits.py: the rules of brief §1.1 and
CLAUDE.md §2 - numbers are code; model output that fails validation falls back, never partially
accepted."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from amazon import limits, parse, pricing, runner, trust, validate
from market import stores as stores_mod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "config_amazon.json"), encoding="utf-8") as _f:
    ACFG = json.load(_f)
TC = ACFG["trust"]
TODAY = date(2026, 11, 10)
RATES = {"date": "2026-11-10", "amd_per": {"GBP": 510.0, "EUR": 440.0, "USD": 390.0}}


def offer(cls=parse.UNREAD, price=20.0, site="de", **kw):
    o = {"market": "amazon", "site": site, "id": "B000000001", "url": "https://www.amazon.de/dp/B000000001",
         "title": "Test charger 65W", "price": price, "currency": parse.CURRENCY[site], "price_kind": "list",
         "list_price": None, "delivery_fee": 0.0, "delivery_text": "FREE delivery", "delivery_note": "free delivery",
         "delivery_eta": (date(2026, 11, 13), date(2026, 11, 13)),
         "seller": {"name": "X", "class": cls, "evidence": "Sold by X"}, "rating": 4.6, "reviews": 500,
         "sales": None, "sales_text": None, "badges": [], "sponsored": False, "weight_kg": 0.3,
         "dims_cm": None, "notes": []}
    o.update(kw)
    return o


class Trust(unittest.TestCase):
    def pts(self, **kw):
        return trust.score(offer(**kw), TC)[0]

    def test_seller_order_amazon_over_dispatched_over_third_party_over_unread(self):
        a, d, t, u = (self.pts(cls=c) for c in (parse.AMAZON, parse.DISPATCHED, parse.THIRD, parse.UNREAD))
        self.assertGreater(a, d)
        self.assertGreater(d, t)
        self.assertGreater(t, u)

    def test_rating_counts_only_with_enough_reviews(self):
        few = offer(rating=5.0, reviews=6)
        pts, parts = trust.score(few, TC)
        labels = [lbl for lbl, _ in parts]
        self.assertTrue(any("not counted" in lbl for lbl in labels))
        self.assertEqual(dict(parts)[next(lbl for lbl in labels if "not counted" in lbl)], 0.0)
        many = trust.score(offer(rating=5.0, reviews=600), TC)[0]
        self.assertGreater(many, pts)

    def test_low_rating_costs_points(self):
        self.assertLess(self.pts(rating=3.2, reviews=900), self.pts(rating=4.6, reviews=900))

    def test_sponsored_is_penalised_and_flagged(self):
        plain = self.pts()
        spons, parts = trust.score(offer(sponsored=True), TC)
        self.assertLess(spons, plain)
        self.assertIn("sponsored result", [lbl for lbl, _ in parts])

    def test_bought_in_past_month_is_evidence(self):
        a = trust.score(offer(sales=5000, sales_text="5K+ bought in past month"), TC)
        self.assertGreater(a[0], self.pts())
        self.assertTrue(any("5K+" in lbl for lbl, _ in a[1]))

    def test_weights_come_from_config(self):
        tc = json.loads(json.dumps(TC))
        tc["seller"]["amazon"] = 100
        self.assertEqual(trust.score(offer(cls=parse.AMAZON), tc)[0] - trust.score(offer(cls=parse.AMAZON), TC)[0],
                         60.0)

    def test_every_result_has_a_reason(self):
        o = offer(cls=parse.DISPATCHED)
        o["trust"], o["trust_parts"] = trust.score(o, TC)
        r = trust.reason(o)
        self.assertIn("dispatched by Amazon", r)
        o2 = offer(rating=5.0, reviews=3)
        o2["trust"], o2["trust_parts"] = trust.score(o2, TC)
        self.assertIn("not counted", trust.reason(o2))
        self.assertIn("seller not read", trust.reason(o2))


class Pricing(unittest.TestCase):
    def setUp(self):
        self.routes, self.tdate = pricing.load_routes(ROOT)
        self.rows = stores_mod.load()

    def price(self, o):
        return pricing.price_offer(o, self.rows["amazon_" + o["site"]], self.routes, RATES, TODAY, TC)

    def test_every_forwarder_and_mode_of_the_store_is_quoted(self):
        p = self.price(offer(site="de"))
        pairs = {(ln["forwarder"], ln["mode"]) for ln in p["quote"]["lines"]}
        self.assertEqual(pairs, {("onex", "air"), ("onex", "truck"), ("globbing", "air"), ("globbing", "truck")})
        self.assertEqual({(ln["forwarder"], ln["mode"]) for ln in self.price(offer(site="uk"))["quote"]["lines"]},
                         {("onex", "air"), ("globbing", "air")})
        self.assertEqual({ln["mode"] for ln in self.price(offer(site="it"))["quote"]["lines"]}, {"truck"})

    def test_total_is_item_in_amd_plus_shipping_plus_customs(self):
        p = self.price(offer(price=20.0, site="de"))
        b = p["best"]
        self.assertEqual(p["price_amd"], 20.0 * 440.0)
        self.assertAlmostEqual(b["total_amd"], p["price_amd"] + b["ship_amd"] + b["customs_amd"], 3)
        self.assertEqual(p["total_amd"], b["total_amd"])
        self.assertEqual(p["total_amd"], min(ln["total_amd"] for ln in p["quote"]["lines"]
                                             if ln["total_amd"] is not None))

    def test_unknown_weight_is_one_kg_and_flagged(self):
        p = self.price(offer(weight_kg=None))
        self.assertTrue(p["weight_assumed"])
        self.assertEqual(p["kg"], 1.0)
        q = self.price(offer(weight_kg=0.3))
        self.assertFalse(q["weight_assumed"])
        self.assertLess(q["total_amd"], p["total_amd"])

    def test_no_price_means_no_total(self):
        p = self.price(offer(price=None))
        self.assertIsNone(p["total_amd"])
        self.assertIsNone(p["quote"])

    def test_unknown_amazon_delivery_is_not_counted_and_said(self):
        p = self.price(offer(delivery_fee=None, delivery_note="free on a first/eligible order only - real cost unknown"))
        self.assertTrue(any("store delivery" in n for n in p["quote"]["notes"]))
        paid = self.price(offer(delivery_fee=5.0))
        free = self.price(offer(delivery_fee=0.0))
        self.assertAlmostEqual(paid["total_amd"] - free["total_amd"], 5.0 * 440.0 + 0, delta=5.0 * 440.0 * 0.2)

    def test_no_rate_means_no_amd(self):
        p = pricing.price_offer(offer(), self.rows["amazon_de"], self.routes, None, TODAY, TC)
        self.assertIsNone(p["total_amd"])

    def test_rank_by_trust_band_then_price_and_sponsored_never_wins(self):
        def mk(cls, price, **kw):
            return self.price(offer(cls=cls, price=price, **kw))
        amazon_dear = mk(parse.AMAZON, 30.0)
        third_cheap = mk(parse.THIRD, 10.0)
        ranked = pricing.rank([third_cheap, amazon_dear], 5, TC["band"])
        self.assertIs(ranked[0], amazon_dear)               # trust first
        a = mk(parse.AMAZON, 20.0, sponsored=True)
        b = mk(parse.AMAZON, 20.0)
        a["trust"] = b["trust"]
        self.assertIs(pricing.rank([a, b], 2, TC["band"])[0], b)
        pick, why = pricing.best_pick([a, b], TC["band"])
        self.assertIs(pick, b)
        # a sponsored result may be picked only when it is all there is
        pick2, why2 = pricing.best_pick([a], TC["band"])
        self.assertIs(pick2, a)
        self.assertIn("sponsored", why2)

    def test_unpriced_last_and_empty_pick(self):
        none = self.price(offer(price=None))
        ok = self.price(offer(price=10.0))
        self.assertIs(pricing.rank([none, ok], 5, TC["band"])[0], ok)
        self.assertEqual(pricing.best_pick([none], TC["band"]), (None, ""))


class Validate(unittest.TestCase):
    GOOD = {"query_en": "usb c charger 65w",
            "queries": {"uk": "usb c charger 65w", "de": "usb c ladegerät 65w", "it": "caricatore usb c 65w"},
            "category": "electronics", "vague": False, "questions": []}

    def test_good_plan(self):
        p = validate.plan(self.GOOD)
        self.assertEqual(p["queries"]["de"], "usb c ladegerät 65w")
        self.assertEqual(p["queries"]["us"], "usb c charger 65w")       # US falls back to English
        self.assertFalse(p["vague"])

    def test_plan_rejections(self):
        def bad(**kw):
            d = json.loads(json.dumps(self.GOOD))
            d.update(kw)
            with self.assertRaises(ValueError):
                validate.plan(d)
        bad(category="weapons")
        bad(queries={"uk": "a b", "de": "https://evil.example/x", "it": "caricatore usb"})
        bad(queries={"uk": "a b", "de": "a b"})                          # it missing
        bad(vague=True, questions=[])
        bad(vague=True, questions=[{"q": "A?", "options": ["x", "y"]}, {"q": "B?", "options": ["x", "y"]}])
        bad(vague=True, questions=[{"q": "A?", "options": ["only one"]}])
        with self.assertRaises(ValueError):
            validate.plan([])

    def test_one_question_kept_when_vague(self):
        d = dict(self.GOOD, vague=True, questions=[{"q": "How old is the baby?", "options": ["0-3 months", "3-6 months"]}])
        p = validate.plan(d)
        self.assertTrue(p["vague"])
        self.assertEqual(len(p["questions"]), 1)

    def test_reason_numbers_must_come_from_the_facts(self):
        facts = "PICK: Anker 65W - EUR 18.96; total delivered 12,345 AMD; trust: sold by Amazon"
        self.assertEqual(validate.reason({"reason": "Sold by Amazon at 12,345 AMD."}, facts), "Sold by Amazon at 12,345 AMD.")
        self.assertEqual(validate.reason({"reason": "Sold by Amazon and well reviewed."}, facts),
                         "Sold by Amazon and well reviewed.")
        with self.assertRaises(ValueError):
            validate.reason({"reason": "That is 1,000 AMD cheaper."}, facts)        # a number it made up
        with self.assertRaises(ValueError):
            validate.reason({"reason": ""}, facts)
        with self.assertRaises(ValueError):
            validate.reason({"reason": "See https://x.example"}, facts)
        with self.assertRaises(ValueError):
            validate.reason("not an object", facts)


class FakeRun:
    """Stands in for subprocess.run: returns the queued replies in order."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw.get("input")))
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(returncode=0, stdout=json.dumps({"result": r, "session_id": "s1",
                                                                "usage": {"output_tokens": 7}}), stderr="")


def priced_pick():
    routes, _ = pricing.load_routes(ROOT)
    p = pricing.price_offer(offer(cls=parse.AMAZON), stores_mod.load()["amazon_de"], routes, RATES, TODAY, TC)
    return p


class Runner(unittest.TestCase):
    def test_plan_is_validated_and_asked_with_no_browsing_tools_and_the_cheap_model(self):
        fake = FakeRun(json.dumps(Validate.GOOD))
        p, u = runner.plan({}, ACFG, "usb c charger 65w", run=fake)
        self.assertEqual(p["category"], "electronics")
        cmd, prompt = fake.calls[0]
        self.assertIn("--model", cmd)
        self.assertEqual(cmd[cmd.index("--model") + 1], ACFG["claude_model"])
        self.assertNotIn("--chrome", cmd)
        self.assertIn("usb c charger 65w", prompt)
        self.assertEqual(u["out"], 7)

    def test_plan_rejected_then_repaired_once(self):
        bad = dict(Validate.GOOD, category="weapons")
        fake = FakeRun(json.dumps(bad), json.dumps(Validate.GOOD))
        p, _ = runner.plan({}, ACFG, "usb c charger 65w", run=fake)
        self.assertEqual(p["category"], "electronics")
        self.assertEqual(len(fake.calls), 2)
        self.assertIn("--resume", fake.calls[1][0])

    def test_plan_rejected_twice_raises(self):
        bad = json.dumps(dict(Validate.GOOD, category="weapons"))
        with self.assertRaises(ValueError):
            runner.plan({}, ACFG, "x y z", run=FakeRun(bad, bad))

    def test_reason_accepts_a_sentence_with_facts_only(self):
        pick = priced_pick()
        fake = FakeRun(json.dumps({"reason": "Sold by Amazon with plenty of good reviews."}))
        s, u = runner.reason({}, ACFG, pick, run=fake)
        self.assertEqual(s, "Sold by Amazon with plenty of good reviews.")
        self.assertIn("{:,.0f}".format(pick["total_amd"]), fake.calls[0][1])        # the model gets the final number
        self.assertIn("NEVER calculate", fake.calls[0][1])

    def test_reason_with_an_invented_number_falls_back_to_the_deterministic_sentence(self):
        pick = priced_pick()
        bad = json.dumps({"reason": "It is 999 AMD cheaper than the rest."})
        s, u = runner.reason({}, ACFG, pick, run=FakeRun(bad, bad))
        self.assertEqual(s, trust.reason(pick))
        self.assertEqual(u, {})

    def test_reason_with_a_dead_model_falls_back(self):
        pick = priced_pick()
        s, _ = runner.reason({}, ACFG, pick, run=FakeRun(RuntimeError("claude failed")))
        self.assertEqual(s, trust.reason(pick))


class Limits(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_daily_cap(self):
        today = date(2026, 11, 10)
        self.assertTrue(limits.can_start(self.root, today, 2)[0])
        limits.count_run(self.root, today)
        limits.count_run(self.root, today)
        ok, why = limits.can_start(self.root, today, 2)
        self.assertFalse(ok)
        self.assertIn("2 times today", why)
        self.assertTrue(limits.can_start(self.root, date(2026, 11, 11), 2)[0])    # next local day

    def test_cooldown_after_a_block(self):
        now = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
        self.assertEqual(limits.cooling(self.root, "de", 24, now), 0.0)
        limits.mark_blocked(self.root, "de", now)
        self.assertAlmostEqual(limits.cooling(self.root, "de", 24, now + timedelta(hours=1)), 23.0, places=2)
        self.assertEqual(limits.cooling(self.root, "de", 24, now + timedelta(hours=25)), 0.0)
        self.assertEqual(limits.cooling(self.root, "uk", 24, now), 0.0)           # per store


if __name__ == "__main__":
    unittest.main()
