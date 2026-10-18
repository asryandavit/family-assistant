"""Armenian / transliterated queries (plan/meals/grocery-words.md) and the
shop comparison, against payloads captured from both shops on 2026-10-18."""
import json
import os
import unittest

from lib import fmt_grocery, parse_grocery as pg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "grocery")
with open(os.path.join(ROOT, "plan", "meals", "grocery-words.md"), encoding="utf-8") as f:
    WORDS = pg.parse_word_list(f.read())


def _parma(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return pg.parse_parma(f.read())


def _yc(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return pg.parse_yc(json.load(f))


class WordList(unittest.TestCase):
    def test_real_file_parses(self):
        self.assertGreater(len(WORDS), 30)
        lentils = next(r for r in WORDS if ["vosp"] in r["aliases"])
        self.assertEqual(lentils["search"], "lentils")         # ✓ mark stripped
        self.assertIn(["ոսպ"], lentils["aliases"])
        self.assertEqual(lentils["match"], [["lentil"]])

    def test_header_separator_and_bad_rows_are_skipped(self):
        md = ("| You can type | Search shops for | Product names to match |\n"
              "|---|---|---|\n| only two | cells |\n| sokh, onion | onions | onion |\n")
        self.assertEqual(pg.parse_word_list(md),
                         [{"aliases": [["sokh"], ["onion"]], "search": "onions", "match": [["onion"]]}])
        self.assertEqual(pg.parse_word_list(""), [])

    def test_expand_query(self):
        self.assertEqual(pg.expand_query("vosp", WORDS), ("lentils", [[["lentil"]]]))
        self.assertEqual(pg.expand_query("ոսպ", WORDS)[0], "lentils")
        # longest alias wins: "chicken breast", not "chicken" + "breast"
        self.assertEqual(pg.expand_query("chicken breast", WORDS), ("chicken breast", [[["chicken", "breast"]]]))
        # unknown words pass through; known ones are replaced in place
        s, groups = pg.expand_query("katnashor 9%", WORDS)
        self.assertEqual(s, "katnashor 9%")
        self.assertEqual(groups[0], [["cottage", "cheese"], ["curd"], ["tvorog"]])
        self.assertEqual(groups[1], [["9%"]])
        # without a word list nothing changes
        self.assertEqual(pg.expand_query("vosp"), ("vosp", [[["vosp"]]]))


class ArmenianMatching(unittest.TestCase):
    def test_transliteration_matches_shop_names(self):
        self.assertEqual(pg.match_score('Matzoon "Dili" 3.2% 450g', "matsun", WORDS), 0)
        self.assertIsNone(pg.match_score('Matzoon "Dili" 3.2% 450g', "matsun"))    # no list: no match
        self.assertEqual(pg.match_score('Curd "Ani" 7% 200g', "katnashor", WORDS), 0)
        self.assertEqual(pg.match_score('Cottage cheese "Yeremyan Products" 12% 170g', "կաթնաշոռ", WORDS), 0)

    def test_armenian_script_uses_yc_armenian_name(self):
        items = _yc("yc_search_hy_vosp.json")
        lentils = next(i for i in items if i["name"] == "Lentils 1kg")
        self.assertEqual(lentils["name_hy"], "Ոսպ 1կգ")
        # even without a word list, the Armenian name matches the Armenian query
        self.assertEqual(pg.match_score(lentils["name"], "ոսպ", None, lentils["name_hy"]), 0)

    def test_parma_english_name_trusts_shop_for_unknown_armenian(self):
        # an Armenian word that isn't in the list can't be read on Parma's English site
        self.assertEqual(pg.match_score('Lentil "Arter" 800g', "ոսպ", None, None), 1)

    def test_katnashor_ranks_both_shops(self):
        items = _parma("parma_search_katnashor.html") + _yc("yc_search_katnashor.json")
        ranked = pg.rank(items, "katnashor", sort="cheap", words=WORDS)
        self.assertEqual({i["shop"] for i in ranked}, {"parma", "yc"})
        self.assertTrue(all(i["match"] in (0, 1) for i in ranked))


class Compare(unittest.TestCase):
    def test_pct_cheaper(self):
        self.assertEqual(pg.pct_cheaper(410, 1013), 60)      # 59.53 -> 60
        self.assertEqual(pg.pct_cheaper(90, 100), 10)
        self.assertEqual(pg.pct_cheaper(100, 100), 0)
        self.assertEqual(pg.pct_cheaper(None, 100), 0)

    def test_best_per_shop_lentils(self):
        items = _parma("parma_search_lentils.html") + _yc("yc_search_lentils.json")
        ranked = pg.rank(items, "lentils", sort="cheap", words=WORDS)
        cmp = pg.compare_shops(ranked)
        self.assertEqual(cmp["unit"], "kg")
        self.assertEqual(set(cmp["best"]), {"parma", "yc"})
        p, y = cmp["best"]["parma"], cmp["best"]["yc"]
        for shop, best in cmp["best"].items():          # really the cheapest leading match
            self.assertEqual(best["unit_price"], min(i["unit_price"] for i in ranked
                             if i["shop"] == shop and i["match"] == 0 and i["unit"] == "kg"))
        lo, hi = sorted([p["unit_price"], y["unit_price"]])
        self.assertEqual(cmp["pct"], pg.pct_cheaper(lo, hi))
        self.assertEqual(cmp["cheaper"], "yc" if y["unit_price"] < p["unit_price"] else "parma")

    def test_one_shop_only_gives_no_verdict(self):
        ranked = pg.rank(_yc("yc_search_lentils.json"), "lentils", sort="cheap", words=WORDS)
        self.assertIsNone(pg.compare_shops(ranked))
        self.assertIsNone(pg.compare_shops([]))

    def test_product_key_is_strict(self):
        k = pg.product_key
        self.assertNotEqual(k('Curd "Marianna" Bifido 9% 180g'), k('Curd "Marianna" 9% 180g'))
        self.assertNotEqual(k('Trout smoked "Santa Bremor" 300g'), k('Trout fillet "Santa Bremor" 300g'))
        self.assertNotEqual(k('Curd "Ani" 7% 200g'), k('Curd "Ani" 9% 200g'))
        self.assertNotEqual(k('Curd "Ani" 7% 200g'), k('Curd "Ani" 7% 400g'))
        # different type words for the same product are fine once they are type words
        tw = {"cottage", "cheese", "curd", "tvorog"}
        self.assertEqual(k('Cottage cheese "Yeremyan Products" 12% 170g', tw),
                         k('Curd "Yeremyan Products" 12% 170g', tw))
        self.assertIsNone(k("Buckwheat 1kg"))              # no brand: can't tell

    def test_same_products_buckwheat(self):
        items = _parma("parma_search_buckwheat.html") + _yc("yc_search_buckwheat.json")
        ranked = pg.rank(items, "buckwheat", sort="cheap", words=WORDS)
        pairs = pg.same_products(ranked, "buckwheat", WORDS)
        self.assertTrue(pairs)
        for p, y, diff, pct in pairs:
            self.assertEqual((p["shop"], y["shop"]), ("parma", "yc"))
            self.assertEqual(diff, y["price"] - p["price"])
            self.assertEqual(pct, pg.pct_cheaper(min(p["price"], y["price"]), max(p["price"], y["price"])))
        mistral = [t for t in pairs if 'Mistral' in t[0]["name"] and "900g" in t[0]["name"]]
        self.assertEqual(len(mistral), 1)
        diffs = [abs(t[2]) for t in pairs]
        self.assertEqual(diffs, sorted(diffs, reverse=True))   # biggest gap first


class CompareMessage(unittest.TestCase):
    def test_block_and_title(self):
        items = _parma("parma_search_buckwheat.html") + _yc("yc_search_buckwheat.json")
        ranked = pg.rank(items, "հնդկաձավար", sort="cheap", words=WORDS)
        cmp, pairs = pg.compare_shops(ranked), pg.same_products(ranked, "հնդկաձավար", WORDS)
        msg = fmt_grocery.build("հնդկաձավար", ranked, {"parma": "ok", "yc": "ok"},
                                searched="buckwheat", cmp=cmp, pairs=pairs)
        self.assertIn("հնդկաձավար <i>(buckwheat)</i>", msg)
        self.assertIn("Compare", msg)
        self.assertIn("cheaper per kg", msg)
        self.assertIn("Same product, both shops", msg)
        self.assertLess(len(msg), 4096)

    def test_no_compare_block_without_data(self):
        self.assertEqual(fmt_grocery.compare_block(None, []), [])


if __name__ == "__main__":
    unittest.main()
