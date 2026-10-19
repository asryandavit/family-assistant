"""Basket pricing (lib/basket.py): mapping parser, package/cost arithmetic, product
choice and totals -- on the real search results captured for every list item on
2026-10-19 (tests/fixtures/grocery/basket/, parsed by lib.parse_grocery)."""
import json
import os
import re
import unittest
from decimal import Decimal

from lib import basket as bk
from lib import parse_grocery as pg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(os.path.dirname(__file__), "fixtures", "grocery", "basket")


def _read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


WORDS = pg.parse_word_list(_read("plan", "meals", "grocery-words.md"))
ROWS = bk.parse_mapping(_read("plan", "meals", "basket.md"))


def results(rows=ROWS):
    out = {}
    for r in rows:
        if r["search"] and r["search"] not in out:
            slug = re.sub(r"[^a-z0-9]+", "_", r["search"].lower()).strip("_")
            with open(os.path.join(FIX, slug + ".json"), encoding="utf-8") as f:
                out[r["search"]] = json.load(f)
    return out


RESULTS = results()


def priced(kind):
    return bk.price_basket([r for r in ROWS if r["list"] == kind], RESULTS, WORDS)


def entry(b, item):
    return next(e for e in b["lines"] if e["row"]["item"] == item)


def row(qty, unit, **kw):
    r = {"list": "weekly", "item": "X", "search": "x", "match": ["x"], "exclude": [],
         "unit": unit, "shop": None, "qty": Decimal(str(qty)), "skip": False, "note": ""}
    r.update(kw)
    return r


def item(name, price, shop="yc", by_weight=False, min_qty=None):
    return {"shop": shop, "id": name, "name": name, "price": price, "sold_by_weight": by_weight,
            "min_qty": min_qty, "unit_price": None, "unit": None, "available": True,
            "url": "https://x/" + name, "app_url": None, "name_hy": None}


class Mapping(unittest.TestCase):
    def test_real_file_parses(self):
        self.assertGreater(len(ROWS), 40)
        self.assertEqual({r["list"] for r in ROWS}, {"weekly", "monthly"})
        oats = next(r for r in ROWS if r["item"].startswith("Rolled oats"))
        self.assertEqual((oats["qty"], oats["unit"], oats["search"]), (Decimal("3.5"), "kg", "oat flakes"))
        oil = next(r for r in ROWS if r["item"] == "Olive oil")
        self.assertIn(["pomace"], oil["exclude"])
        peas = next(r for r in ROWS if r["item"] == "Frozen peas")
        self.assertEqual(peas["match"], ["peas frozen", "green peas frozen"])

    def test_skipped_rows(self):
        skipped = [r["item"] for r in ROWS if r["skip"]]
        self.assertEqual(skipped, ["Spices", "Coffee", "Scoolinary project ingredients"])
        self.assertTrue(all(r["qty"] is None for r in ROWS if r["skip"]))

    def _one(self, qty="1", unit="kg", shop=""):
        return bk.parse_mapping("| weekly | Eggs | eggs | eggs | %s | %s | | %s | |" % (qty, unit, shop))

    def test_decimal_comma_and_shop(self):
        r = self._one("1,5", "kg", "Yerevan City")[0]
        self.assertEqual((r["qty"], r["shop"]), (Decimal("1.5"), "yc"))

    def test_rejections(self):
        for qty, unit, shop in (("abc", "kg", ""), ("0", "kg", ""), ("500", "kg", ""),
                                ("1.5", "pcs", ""), ("2", "bags", ""), ("2", "kg", "carrefour")):
            with self.assertRaises(ValueError, msg=(qty, unit, shop)) as cm:
                self._one(qty, unit, shop)
            self.assertIn("Eggs", str(cm.exception))
        with self.assertRaises(ValueError):
            bk.parse_mapping("| weekly | Eggs | eggs |")
        with self.assertRaises(ValueError):
            bk.parse_mapping("| weekly | Eggs |  |  | 2 | kg | | | |")   # no search words

    def test_other_lines_ignored(self):
        self.assertEqual(bk.parse_mapping("| List | Item |\n|---|---|\ntext\n| Item | Approx |"), [])


class Arithmetic(unittest.TestCase):
    def test_weight_item_uses_qty_or_shop_minimum(self):
        ln = bk.line_for(row(1.5, "kg"), item("Apple kg", 265.0, by_weight=True, min_qty=1.0))
        self.assertEqual((ln["cost"], ln["buy"], ln["min_order"]), (398, "1.5 kg", False))  # 397.5 half up
        ln = bk.line_for(row(0.1, "kg"), item("Garlic kg", 1190.0, by_weight=True, min_qty=0.3))
        self.assertEqual((ln["cost"], ln["buy"], ln["min_order"]), (357, "0.3 kg", True))

    def test_packages_round_up(self):
        ln = bk.line_for(row(3.5, "kg"), item('Oat flakes "Y" 500g', 389.991))
        self.assertEqual((ln["buy"], ln["cost"]), ("7 × 500 g", 2730))       # 6.3 -> 7 packs
        ln = bk.line_for(row(2, "kg"), item("Bulgur 800g", 390.0))
        self.assertEqual((ln["buy"], ln["cost"]), ("3 × 800 g", 1170))       # 2.25 -> 3
        ln = bk.line_for(row(2, "l"), item('Olive oil "C" 1l', 3489.944))
        self.assertEqual((ln["buy"], ln["cost"]), ("2 × 1 l", 6980))
        ln = bk.line_for(row(1, "kg"), item('Tomato paste "S" 1050g', 590.0))
        self.assertEqual(ln["buy"], "1 × 1.05 kg")

    def test_ten_percent_short_counts(self):
        ln = bk.line_for(row(1, "kg"), item('Chicken thigh "A" 950g', 1210.0))
        self.assertEqual((ln["buy"], ln["cost"]), ("1 × 950 g", 1210))
        ln = bk.line_for(row(1, "kg"), item("Lentils 800g", 800.0))
        self.assertEqual(ln["buy"], "2 × 800 g")                           # 20% short is not enough

    def test_pieces(self):
        self.assertEqual(bk.line_for(row(20, "pcs"), item('Eggs "K" 10pcs', 990.0))["buy"], "2 × 10 pcs")
        ln = bk.line_for(row(20, "pcs"), item('Eggs "A" #0-1 6pcs', 480.0))
        self.assertEqual((ln["buy"], ln["cost"]), ("3 × 6 pcs", 1440))
        self.assertIsNone(bk.line_for(row(20, "pcs"), item("Eggs loose", 100.0)))

    def test_packs(self):
        ln = bk.line_for(row(5, "pack"), item('Mackerel "Z" in oil 185gr', 990.0))
        self.assertEqual((ln["buy"], ln["cost"]), ("5 × 185 g", 4950))
        self.assertEqual(bk.line_for(row(1, "pack"), item("Parsley pc", 275.0))["buy"], "1 pc")
        self.assertEqual(bk.line_for(row(2, "pack"), item("Dill", 260.0))["buy"], "2 pcs")

    def test_unit_mismatch_is_not_a_line(self):
        self.assertIsNone(bk.line_for(row(2, "l"), item("Lactel milk 1000g", 1290.0)))
        self.assertIsNone(bk.line_for(row(1, "l"), item("Mortadella kg", 8990.0, by_weight=True)))
        self.assertIsNone(bk.line_for(row(2, "pack"), item("Lavash kg", 645.0, by_weight=True)))
        self.assertIsNone(bk.line_for(row(1, "kg"), item("Spinach pc", 275.0)))

    def test_size_label(self):
        self.assertEqual(bk.size_label(Decimal("0.8"), "kg"), "800 g")
        self.assertEqual(bk.size_label(Decimal("0.45"), "l"), "450 ml")
        self.assertEqual(bk.size_label(Decimal("2"), "kg"), "2 kg")


class Choosing(unittest.TestCase):
    def test_leads_with_the_product(self):
        self.assertTrue(bk.leads("Cucumber (russian) kg", "cucumbers", WORDS))
        self.assertTrue(bk.leads("Greenhouse tomatoes (armenian) kg", "tomatoes", WORDS))
        self.assertTrue(bk.leads('Canned mackerel "5 Morey" in oil 250g', "mackerel", WORDS))
        self.assertTrue(bk.leads('Curd "Igit" 9% kg', "katnashor", WORDS))
        self.assertFalse(bk.leads('Cat food "Whiskas" trout and salmon 75g', "trout", WORDS))
        self.assertFalse(bk.leads('Shampoo "Palmolive" olive 450ml', "olive oil", WORDS))
        self.assertFalse(bk.leads('Hummus "Ayo" green walnut 250g', "walnuts", WORDS))

    def test_chosen_products_on_real_results(self):
        m, w = priced("monthly"), priced("weekly")
        name = lambda b, it: entry(b, it)["line"]["item"]["name"]  # noqa: E731
        self.assertEqual(name(m, "Olive oil"), 'Olive oil "Campagna" g/b 1l')     # not pomace / blend
        self.assertEqual(name(m, "Walnuts (unsalted)"), "Walnut kg")
        self.assertEqual(name(m, "Honey (small)"), 'Natural honey "Meghu" 150g')
        self.assertEqual(name(w, "Trout"), 'Frozen trout fillet "Okeanos" kg')
        self.assertEqual(name(w, "Eggs"), 'Eggs "Arzni" havkirt #0-1 6pcs')
        self.assertEqual(entry(w, "Garlic")["shop"], "parma")
        for b in (m, w):
            for e in b["lines"]:
                if e["line"]:
                    n = e["line"]["item"]["name"].lower()
                    for bad in ("pomace", "shampoo", "cat food", "pastry", "noodle", "vinegar"):
                        self.assertNotIn(bad, n, e["row"]["item"])

    def test_cheaper_shop_wins_and_yc_on_tie(self):
        r = row(1, "pack", match=["dill"])
        per = {"yc": {"cost": 300}, "parma": {"cost": 260}}
        self.assertEqual(bk.choose(r, per)[0], "parma")
        self.assertEqual(bk.choose(r, {"yc": {"cost": 260}, "parma": {"cost": 260}})[0], "yc")
        self.assertEqual(bk.choose(dict(r, shop="yc"), per)[0], "yc")             # preferred shop
        self.assertEqual(bk.choose(dict(r, shop="yc"), {"parma": {"cost": 1}})[0], "parma")
        self.assertEqual(bk.choose(r, {}), (None, None))


class Totals(unittest.TestCase):
    def test_totals_and_split_add_up(self):
        for kind in ("weekly", "monthly"):
            b = priced(kind)
            ok = [e for e in b["lines"] if e["status"] == "ok"]
            self.assertEqual(b["totals"]["all"], sum(e["line"]["cost"] for e in ok))
            self.assertEqual(b["totals"]["all"], b["totals"]["yc"] + b["totals"]["parma"])
            groups = bk.by_shop(b)
            self.assertEqual([s for s, _, _ in groups], ["yc", "parma"])          # YC first
            self.assertEqual(sum(t for _, _, t in groups), b["totals"]["all"])
            c = b["compare"]
            self.assertLessEqual(c["cheapest"], min(c["yc"], c["parma"]))
            for e in ok:                       # the chosen shop is the cheaper one
                self.assertEqual(e["line"]["cost"], min(ln["cost"] for ln in e["per_shop"].values()))

    def test_first_capture_totals(self):
        """Pinned on the 2026-10-19 capture: a change here is a change in behaviour."""
        self.assertEqual(priced("weekly")["totals"], {"yc": 12179, "parma": 3342, "all": 15521})
        self.assertEqual(priced("monthly")["totals"], {"yc": 42290, "parma": 2905, "all": 45195})
        self.assertEqual(priced("weekly")["compare"],
                         {"n": 22, "yc": 17562, "parma": 18240, "cheapest": 15291})

    def test_no_match_is_excluded_and_partial(self):
        rows = [row(1, "kg", item="Dragonfruit", search="apples", match=["dragonfruit"]),
                row(1.5, "kg", item="Apples", search="apples", match=["apples"])]
        b = bk.price_basket(rows, RESULTS, WORDS)
        self.assertEqual(b["lines"][0]["status"], "no match")
        self.assertTrue(b["partial"])
        self.assertEqual(b["totals"]["all"], b["lines"][1]["line"]["cost"])
        self.assertEqual([e["row"]["item"] for e in bk.not_priced(b)], ["Dragonfruit"])

    def test_shop_down_is_unavailable_not_no_match(self):
        res = {"apples": {"items": [], "status": {"yc": "error: timeout", "parma": "error: 503"}}}
        b = bk.price_basket([row(1, "kg", search="apples", match=["apples"])], res, WORDS)
        self.assertEqual(b["lines"][0]["status"], "unavailable")
        self.assertEqual(b["failed"], ["parma", "yc"])
        self.assertEqual(b["totals"]["all"], 0)

    def test_skipped_rows_cost_nothing(self):
        b = priced("monthly")
        self.assertEqual({e["row"]["item"] for e in b["lines"] if e["status"] == "skipped"},
                         {"Spices", "Coffee"})
        self.assertFalse(b["partial"])


class Budget(unittest.TestCase):
    def test_projection(self):
        self.assertEqual(bk.month_projection(15000, 30000), 95000)          # 15000*52/12 = 65000
        self.assertEqual(bk.month_projection(15521, 45195), 112453)        # 67257.67 -> 67258
        self.assertEqual(bk.month_projection(12000, None), 52000)
        self.assertEqual(bk.month_projection(None, 30000), 30000)
        self.assertIsNone(bk.month_projection())

    def test_verdict(self):
        self.assertEqual(bk.budget_verdict(112453, 80000, 100000), ("over", 12453))
        self.assertEqual(bk.budget_verdict(90000, 80000, 100000), ("within", 0))
        self.assertEqual(bk.budget_verdict(100000, 80000, 100000), ("within", 0))
        self.assertEqual(bk.budget_verdict(70000, 80000, 100000), ("under", 10000))


if __name__ == "__main__":
    unittest.main()
