"""Tests for lib/parse_grocery.py against payloads captured from the live shops
on 2026-10-18 (tests/fixtures/grocery/). Runs under unittest or pytest:

    python -m unittest discover -s tests -t .
    python -m pytest tests            (once pytest is installed)
"""
import json
import os
import unittest

from lib import parse_grocery as pg

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "grocery")


def _html(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def _json(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


def _by_name(items, name):
    return next(i for i in items if i["name"] == name)


class Arithmetic(unittest.TestCase):
    def test_amd_rounds_half_up(self):
        self.assertEqual(pg.amd(319.995), 320)
        self.assertEqual(pg.amd(2.5), 3)      # banker's rounding would give 2
        self.assertEqual(pg.amd(0.5), 1)
        self.assertIsNone(pg.amd(None))

    def test_size_from_name(self):
        self.assertEqual(pg.size_from_name("Lentils 500g"), (0.5, "kg"))
        self.assertEqual(pg.size_from_name("Lentils 1kg"), (1.0, "kg"))
        self.assertEqual(pg.size_from_name('Milk "Yeremyan" 3.2% 750ml'), (0.75, "l"))
        self.assertEqual(pg.size_from_name("Sunflower oil 1,5l"), (1.5, "l"))
        # the last size wins: count first, weight last
        self.assertEqual(pg.size_from_name("Chicken sausages 12pcs 350g"), (0.35, "kg"))
        self.assertIsNone(pg.size_from_name("Coriander"))
        self.assertIsNone(pg.size_from_name("Weird 0g"))

    def test_unit_price_from_name(self):
        self.assertEqual(pg.unit_price_from_name(220, "Lentils 500g"), (440.0, "kg"))
        self.assertEqual(pg.unit_price_from_name(900, "Milk 750ml"), (1200.0, "l"))
        self.assertEqual(pg.unit_price_from_name(230, "Coriander"), (None, None))


class Parma(unittest.TestCase):
    def test_weight_items_are_normalised_to_per_kg(self):
        items = pg.parse_parma(_html("parma_search_chicken.html"))
        self.assertEqual(len(items), 5)
        first = items[0]
        self.assertEqual(first["name"], "Chicken breast kg")
        # the card shows 1500 for the 0.5 kg minimum; the comparable price is per kg
        self.assertEqual(first["price"], 3000)
        self.assertEqual((first["unit_price"], first["unit"]), (3000, "kg"))
        self.assertTrue(first["sold_by_weight"])
        self.assertEqual(first["min_qty"], 0.5)
        self.assertEqual(first["url"], "https://parma.am/en/product/product?slug=chicken-breast-kg_82775")
        self.assertTrue(first["image"].startswith("https://static.parma.am/"))

    def test_discounts(self):
        items = pg.parse_parma(_html("parma_sales.html"))
        self.assertEqual(len(items), 60)
        self.assertTrue(all(i["old_price"] for i in items))
        y = items[0]
        self.assertEqual((y["price"], y["old_price"], y["discount_pct"]), (230, 290, 20.7))
        self.assertEqual((y["unit_price"], y["unit"]), (2000, "kg"))
        self.assertFalse(y["sold_by_weight"])

    def test_pager_and_second_page(self):
        page = _html("parma_search_oats_p2.html")
        self.assertEqual(pg.parma_page_range(page), (61, 73))
        self.assertEqual(len(pg.parse_parma(page)), 13)

    def test_empty_or_unrelated_html(self):
        self.assertEqual(pg.parse_parma(""), [])
        self.assertEqual(pg.parse_parma("<html><body>no products</body></html>"), [])
        self.assertIsNone(pg.parma_page_range(""))


class YerevanCity(unittest.TestCase):
    def test_package_unit_prices(self):
        items = pg.parse_yc(_json("yc_search_lentils.json"))
        self.assertEqual(len(items), 18)
        one_kg = _by_name(items, "Lentils 1kg")
        # shop gives no per-unit price for "1kg" packs; derived from the name
        self.assertEqual((one_kg["price"], one_kg["unit_price"], one_kg["unit"]), (410, 410, "kg"))
        half = _by_name(items, "Lentils 500g")
        self.assertEqual((half["price"], half["unit_price"], half["unit"]), (220, 440, "kg"))
        self.assertEqual(half["url"], "https://yerevan-city.am/shop/product-details/76665")
        self.assertIsNone(half["old_price"])

    def test_discount_uses_sale_price(self):
        items = pg.parse_yc(_json("yc_discounted_yogurt.json"))
        self.assertTrue(all(i["old_price"] for i in items))
        y = items[0]
        self.assertEqual(pg.amd(y["price"]), 320)       # discountedPrice 319.995
        self.assertEqual(y["old_price"], 390)
        self.assertEqual(y["discount_pct"], 17.9)

    def test_weight_items_min_qty_in_kg(self):
        items = pg.parse_yc(_json("yc_search_chicken.json"))
        roll = items[0]
        self.assertTrue(roll["sold_by_weight"])
        self.assertEqual((roll["unit_price"], roll["unit"]), (4090, "kg"))
        self.assertEqual(roll["min_qty"], 0.2)          # API sends 200 (grams)

    def test_counts_and_empty_payloads(self):
        self.assertEqual(pg.yc_counts(_json("yc_search_chicken.json")), (275, 10))
        self.assertEqual(pg.parse_yc({}), [])
        self.assertEqual(pg.parse_yc({"success": False, "data": None}), [])
        self.assertEqual(pg.parse_yc(None), [])


class Matching(unittest.TestCase):
    def test_whole_words_not_prefixes(self):
        self.assertIsNone(pg.match_score('Toffee "Roshen" Milky Splash kg', "milk"))
        self.assertIsNone(pg.match_score('Ice cream "Milka" Escimo', "milk"))

    def test_plurals_and_leading_type(self):
        self.assertEqual(pg.match_score("Lentils 1kg", "lentil"), 0)
        self.assertEqual(pg.match_score("Lentils 1kg", "lentils"), 0)
        self.assertEqual(pg.match_score("Boneless chicken breast kg", "chicken breast"), 0)
        self.assertEqual(pg.match_score("Pilaf with pasta, chicken breast kg", "chicken breast"), 1)
        self.assertEqual(pg.match_score("Chicken breast kg", "chicken breast"), 0)

    def test_descriptors_before_the_type_still_lead(self):
        self.assertEqual(pg.match_score('Frozen chicken breast fillet "Qualiko" 1kg', "chicken breast"), 0)
        self.assertEqual(pg.match_score('Fresh chicken breast "Ashtarak" 950g', "chicken breast"), 0)
        # a descriptor that IS the query is matched, not skipped
        self.assertEqual(pg.match_score("Whole milk 1l", "whole milk"), 0)
        # but a different product type still ranks lower
        self.assertEqual(pg.match_score("Chicken breast crepes", "crepes"), 1)

    def test_rank_cheap_puts_real_milk_first(self):
        items = pg.parse_yc(_json("yc_search_milk_100.json"))
        ranked = pg.rank(items, "milk", sort="cheap")
        self.assertLess(len(ranked), len(items))       # junk filtered out
        top = ranked[0]
        self.assertTrue(top["name"].lower().startswith("milk "))
        prices = [i["unit_price"] for i in ranked if pg.match_score(i["name"], "milk") == 0
                  and i["unit_price"] is not None]
        self.assertEqual(prices, sorted(prices))

    def test_rank_interleaves_shops(self):
        parma = pg.parse_parma(_html("parma_search_chicken.html"))
        yc = pg.parse_yc(_json("yc_search_chicken.json"))
        ranked = pg.rank(parma + yc, "chicken")
        self.assertEqual({ranked[0]["shop"], ranked[1]["shop"]}, {"parma", "yc"})


if __name__ == "__main__":
    unittest.main()
