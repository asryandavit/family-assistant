"""shopping/quality.py: the best value among acceptable products (decision 106).
Candidates come from the captured basket searches (tests/fixtures/grocery/basket/,
2026-10-19), so every rule is checked against real product names."""
import json
import os
import unittest
from decimal import Decimal

from jobs import grocery_basket as gb
from jobs.grocery_search import load_words
from lib import basket as bk
from shopping import quality as q

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "grocery", "basket")
ROWS = gb.load_rows(ROOT)
RULES = gb.load_rules(ROOT, ROWS)
WORDS = load_words(ROOT)
HEAD = ("| Item | Aisle | Avoid | Require | Prefer | Premium % | Min fat % | Max price | Why |\n"
        "|---|---|---|---|---|---|---|---|---|\n")


def row(name):
    return next(r for r in ROWS if r["item"] == name)


def items(name):
    with open(os.path.join(FIX, gb.fixture_slug(row(name)["search"]) + ".json"), encoding="utf-8") as f:
        return json.load(f)["items"]


def rule(text):
    return q.parse_rules(HEAD + text)


def one(md_row, item):
    r = rule(md_row)
    return q.pick(row(item), items(item), WORDS, r[item])


def chosen(item, rules=RULES):
    b = bk.price_basket([row(item)], {row(item)["search"]: {"items": items(item),
                                                            "status": {"yc": "ok", "parma": "ok"}}},
                        WORDS, picker=q.make_picker(rules))
    return b["lines"][0]


class ParseRules(unittest.TestCase):
    def test_seeded_table_covers_every_item_and_parses(self):
        self.assertEqual(set(RULES), {r["item"] for r in ROWS})
        oil = RULES["Olive oil"]
        self.assertEqual([t for t, _ in oil["require"]], ["extra virgin"])
        self.assertEqual(oil["max_price"], Decimal(8000))
        self.assertEqual(RULES["Whole milk (son)"]["min_fat"], Decimal("3.2"))
        self.assertEqual(RULES["Chicken breast"]["premium"], Decimal(15))

    def test_decimal_comma_units_and_default_premium(self):
        r = rule("| Matsun | Dairy | | | fresh | | 3,2 % | 8 000 AMD | |\n")["Matsun"]
        self.assertEqual((r["min_fat"], r["max_price"], r["premium"]),
                         (Decimal("3.2"), Decimal(8000), Decimal(q.DEFAULT_PREMIUM)))

    def test_no_table_means_no_rules(self):
        self.assertEqual(q.parse_rules("| weekly | Eggs | eggs | eggs | 20 | pcs | | | |"), {})

    def test_rejections_say_what_to_fix(self):
        bad = {
            "| Olive oyl | Oils | | extra virgin | | | | | |\n": "no such item",
            "| Matsun | Dairy | | | | | lots | | |\n": "not a number",
            "| Matsun | Dairy | | | | | 150 | | |\n": "out of range",
            "| Matsun | Dairy | | | | 10 | | | |\n": "without Prefer",
            "| Matsun | Dairy | | | fresh | 12.5 | | | |\n": "whole number",
            "| Matsun | Dairy | | | |\n": "expected 9",
            "| Matsun | Dairy | | | | | | | |\n| Matsun | Dairy | | | | | | | |\n": "two quality rows",
        }
        for text, words in bad.items():
            with self.assertRaises(ValueError) as cm:
                q.parse_rules(HEAD + text, ROWS)
            self.assertIn(words, str(cm.exception), text)

    def test_fat_from_names_including_the_armenian_dot(self):
        self.assertEqual(q.fat_pct('Milk "Marianna" 3․2% 450ml'), Decimal("3.2"))
        self.assertEqual(q.fat_pct('Curd "Biokat" 0%  400g'), Decimal(0))
        self.assertIsNone(q.fat_pct("Lavash kg"))


class NoRuleFallsBack(unittest.TestCase):
    def test_rows_without_rules_pick_what_best_per_shop_picks(self):
        """Every captured row, judged with no rules at all, matches the old choice --
        except where the old choice was a loose item without a price per kg."""
        changed = []
        for r in ROWS:
            if r["skip"]:
                continue
            its = items(r["item"])
            old = bk.best_per_shop(r, its, WORDS)
            new = q.pick(r, its, WORDS, None)
            for shop in old:
                if old[shop]["item"]["name"] != (new.get(shop) or {}).get("item", {}).get("name"):
                    self.assertTrue(q.unknown_price(old[shop]), (r["item"], shop))
                    changed.append(r["item"])
                elif new[shop]["reason"]:          # only ever about a no-per-kg item elsewhere
                    self.assertIn("skipped: no price per kg shown", new[shop]["reason"], r["item"])
        self.assertEqual(sorted(set(changed)), ["Apples", "Tomatoes"])

    def test_missing_rule_in_the_table_is_plain_cheapest(self):
        e = chosen("Eggs", rules={})
        self.assertEqual(e["line"]["item"]["name"], bk.best_per_shop(row("Eggs"), items("Eggs"), WORDS)[e["shop"]]["item"]["name"])
        self.assertIsNone(e["line"]["reason"])


class Rules(unittest.TestCase):
    def test_banned_brand_is_never_picked_even_when_cheapest(self):
        base = chosen("Matsun", rules={})["line"]["item"]["name"]
        self.assertIn("Igit", base)                                   # the cheapest one
        per_shop = one("| Matsun | Dairy | Igit | | | | | | |\n", "Matsun")
        names = [ln["item"]["name"] for ln in per_shop.values()]
        self.assertTrue(names and not any("Igit" in n for n in names), names)
        e = chosen("Matsun", rules=rule("| Matsun | Dairy | Igit | | | | | | |\n"))
        self.assertNotIn("Igit", e["line"]["item"]["name"])
        self.assertIn("“Igit” is on your avoid list", e["line"]["reason"])

    def test_banned_word_rejects_at_both_shops(self):
        for ev in q.evaluate(row("Trout"), items("Trout"), WORDS, RULES["Trout"]):
            name = ev["line"]["item"]["name"].lower()
            if "opener" in name or "sauce" in name or "own juice" in name:
                self.assertTrue(ev["rejected"], name)

    def test_olive_oil_must_be_extra_virgin(self):
        e = chosen("Olive oil")
        self.assertIn("Extra Virgin", e["line"]["item"]["name"])
        self.assertEqual(e["line"]["reason"], "Campagna is 2,000 ֏ less but not extra virgin; 1 more skipped")

    def test_nothing_passing_is_explained_not_guessed(self):
        r = rule("| Olive oil | Oils | | unicorn | | | | | |\n")
        e = chosen("Olive oil", rules=r)
        self.assertEqual(e["status"], "no match")
        self.assertIsNone(e["line"])
        why = q.explain_none(row("Olive oil"), items("Olive oil"), WORDS, r["Olive oil"])
        self.assertEqual(why, "nothing passes your rules — cheapest was Campagna (not unicorn)")

    def test_min_fat_rejects_low_and_unknown_fat(self):
        r = rule("| Katnashor (tvorog) | Dairy | | | | | 5 | | |\n")["Katnashor (tvorog)"]
        for ev in q.evaluate(row("Katnashor (tvorog)"), items("Katnashor (tvorog)"), WORDS, r):
            f = q.fat_pct(ev["line"]["item"]["name"])
            if f is None or f < 5:
                self.assertTrue(ev["rejected"], ev["line"]["item"]["name"])
            else:
                self.assertIsNone(ev["rejected"])

    def test_price_ceiling_on_what_is_bought(self):
        r = rule("| Trout | Fish | | | | | | 4700 | |\n")["Trout"]
        evs = q.evaluate(row("Trout"), items("Trout"), WORDS, r)
        for ev in evs:
            pu = q.per_unit(ev["line"])
            self.assertEqual(bool(ev["rejected"]), q.unknown_price(ev["line"]) or pu > 4700,
                             ev["line"]["item"]["name"])
        over = next(ev for ev in evs if ev["rejected"] and not q.unknown_price(ev["line"]))
        self.assertIn("over your 4,700 ceiling", over["rejected"])

    def test_preferred_within_premium_wins_beyond_it_loses(self):
        e = chosen("Chicken breast")
        self.assertEqual(e["line"]["item"]["name"], 'Fresh chicken breast "Ashtarak" 950g')
        self.assertEqual(e["line"]["reason"], "fresh, +13% over Qualiko (limit 15%)")
        tight = rule("| Chicken breast | Meat | | | fresh | 10 | | | |\n")
        e = chosen("Chicken breast", rules=tight)
        self.assertEqual(e["line"]["item"]["name"], 'Frozen chicken breast fillet "Qualiko" 1kg')
        self.assertIsNone(e["line"]["reason"])

    def test_preference_counts_across_shops(self):
        """A preferred product at one shop beats a cheaper plain one at the other only
        within the premium (lib.basket.choose reads the line's rank)."""
        r = {"list": "weekly", "item": "Thing", "search": "thing", "match": ["thing"], "qty": Decimal(1),
             "unit": "pack", "exclude": [], "shop": None, "note": "", "skip": False}
        its = [{"shop": "yc", "id": "1", "name": "Thing plain", "price": 1000.0, "sold_by_weight": False,
                "unit_price": None, "unit": None, "url": "u1", "min_qty": None, "available": True},
               {"shop": "parma", "id": "2", "name": "Thing fresh", "price": 1100.0, "sold_by_weight": False,
                "unit_price": None, "unit": None, "url": "u2", "min_qty": None, "available": True}]
        for premium, want in (("15", "parma"), ("5", "yc")):
            rules = {"Thing": q.parse_rules(HEAD + f"| Thing | X | | | fresh | {premium} | | | |\n")["Thing"]}
            b = bk.price_basket([r], {"thing": {"items": its, "status": {"yc": "ok", "parma": "ok"}}},
                                [], picker=q.make_picker(rules))
            self.assertEqual(b["lines"][0]["shop"], want, premium)
            self.assertEqual(b["totals"]["all"], 1100 if want == "parma" else 1000)

    def test_loose_item_without_price_per_kg_is_skipped(self):
        e = chosen("Apples")
        self.assertNotEqual(e["line"]["item"]["name"], "Fuji Apples kg Sh")
        self.assertEqual(e["line"]["reason"], "Fuji Apples kg Sh skipped: no price per kg shown")

    def test_processed_chicken_never_picked(self):
        for ev in q.evaluate(row("Chicken breast"), items("Chicken breast"), WORDS, RULES["Chicken breast"]):
            name = ev["line"]["item"]["name"].lower()
            if "marinated" in name or "curry" in name:
                self.assertTrue(ev["rejected"], name)


if __name__ == "__main__":
    unittest.main()
