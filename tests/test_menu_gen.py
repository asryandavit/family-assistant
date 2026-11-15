"""coach/menu_gen.py (decision 107): the week generator against the real dish library --
rules over a year of weeks, novelty, determinism, hand-edited weeks, the rejection path
and the shopping words. Edge cases run on a temp copy of plan/; real files never change."""
import os
import re
import shutil
import unittest

from coach import menu_gen as mg
from coach import plan_text as pt
from coach import plan_view as pv
from tests.test_plan_view import ROOT, copy_root

WEEKS = range(mg.FIRST_GENERATED, 60)


def mains(menu):
    """(day, meal, dish id) for every lunch and dinner main dish (sides left out)."""
    out = []
    for d in pv.DAYS:
        for k in ("lunch", "dinner"):
            ids = pv.ids_in(menu["days"][d][k])
            if ids:
                out.append((d, k, ids[0]))
    return out


class RealLibrary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dishes = pv.parse_dishes(pv.read_dishes(ROOT))
        cls.menus = {w: mg.week_menu(ROOT, cls.dishes, w) for w in WEEKS}

    def test_every_week_keeps_the_balance_rules(self):
        for w, m in self.menus.items():
            self.assertEqual(mg.check_rules(self.dishes, m), [], w)
            c = mg.balance(self.dishes, m)
            self.assertGreaterEqual(c["fish"], 2, w)
            self.assertTrue(3 <= c["legume"] <= 4, (w, c))
            self.assertGreaterEqual(c["poultry"], 2, w)
            self.assertGreaterEqual(c["oats"], 3, w)
            self.assertEqual(c["red_meat"], 0, w)

    def test_never_two_legume_meals_in_a_day(self):
        for w, m in self.menus.items():
            for d in pv.DAYS:
                n = sum("legume" in mg.meal_proteins(self.dishes, m["days"][d][k]) for k in ("lunch", "dinner"))
                self.assertLessEqual(n, 1, (w, d))

    def test_no_main_dish_returns_the_week_after(self):
        for w in list(WEEKS)[1:]:
            last = {i for _, _, i in mains(self.menus[w - 1])} - {"wk-scoolinary"}
            now = {i for _, _, i in mains(self.menus[w])}
            self.assertEqual(last & now, set(), w)

    def test_consecutive_weeks_never_share_a_day_plan(self):
        for w in list(WEEKS)[1:]:
            for d in pv.DAYS:
                self.assertNotEqual(self.menus[w - 1]["days"][d], self.menus[w]["days"][d], (w, d))

    def test_week_five_is_not_week_one(self):
        one = pv.load_week(ROOT, 1)
        for d in pv.DAYS:
            self.assertNotEqual(one["days"][d], self.menus[5]["days"][d], d)

    def test_a_month_has_more_than_two_menus(self):
        """Weeks w and w+2 are not the same rotation (the A/B/A/B trap): at least 4 of the
        9 main dishes differ, also in the first weeks while the lists are short."""
        for w in list(WEEKS)[2:]:
            a = {i for _, _, i in mains(self.menus[w - 2])}
            b = {i for _, _, i in mains(self.menus[w])}
            self.assertLessEqual(len(a & b), 5, w)                     # of 9 main dishes

    def test_new_dishes_every_week_while_the_queue_lasts(self):
        debuted = []
        for w in range(5, 13):
            m = self.menus[w]
            self.assertTrue(1 <= len(m["new"]) <= mg.NEW_HARD_MAX, (w, m["new"]))
            for i in m["new"]:
                self.assertEqual(self.dishes[i]["status"], "new", i)
                self.assertNotIn(i, debuted, i)                       # new only once
            debuted += m["new"]
        for w in range(5, 9):                                          # a month: ≥ 4 new
            self.assertGreaterEqual(sum(len(self.menus[x]["new"]) for x in range(w, w + 4)), 4)

    def test_queue_running_out_tells_the_owner(self):
        warned = [w for w, m in self.menus.items() if any("queue" in x for x in m["warnings"])]
        self.assertTrue(warned)
        self.assertGreater(min(warned), 8)

    def test_every_id_is_in_the_library_and_mediterranean_staples_show_up(self):
        seen = set()
        for m in self.menus.values():
            for d in pv.DAYS:
                for cell in m["days"][d].values():
                    for i in pv.ids_in(cell):
                        self.assertIn(i, self.dishes, i)
                        seen.add(i)
        for staple in ("ln-lobi", "ln-veg-stew", "ln-dolma-lean", "sp-spas", "dn-matsun-bowl",
                       "bf-katnashor", "sd-bulgur", "sd-buckwheat", "sd-barley"):
            self.assertIn(staple, seen)

    def test_deterministic(self):
        again = mg.week_menu(ROOT, self.dishes, 20)
        self.assertEqual(again["days"], self.menus[20]["days"])

    def test_committed_weeks_five_to_eight(self):
        for w in range(5, 9):
            self.assertEqual(self.menus[w]["source"], "file", w)
            gen = mg.week_menu(ROOT, self.dishes, w, ignore_file=True)
            norm = lambda days: {d: {k: ("" if v in ("—", "-") else v) for k, v in m.items()}  # noqa: E731
                                 for d, m in days.items()}
            self.assertEqual(norm(gen["days"]), norm(self.menus[w]["days"]), w)   # as generated

    def test_saturday_lunch_has_a_protein_and_dinners_are_light(self):
        for w, m in self.menus.items():
            ps = mg.meal_proteins(self.dishes, m["days"]["Sat"]["lunch"])
            self.assertTrue(ps & {"chicken", "turkey", "egg", "fish", "legume", "dairy"}, w)
            for d in pv.DAYS:
                dinner = pv.ids_in(m["days"][d]["dinner"])[0]
                self.assertIn(self.dishes[dinner]["slot"], ("soup", "fish", "egg", "light", "weekend", "project"))

    def test_batch_day_two_keeps_day_one(self):
        for w, m in self.menus.items():
            self.assertEqual(m["days"]["Mon"]["lunch"], m["days"]["Tue"]["lunch"], w)
            self.assertEqual(m["days"]["Wed"]["lunch"], m["days"]["Thu"]["lunch"], w)

    def test_shopping_words_no_amounts(self):
        words = mg.week_ingredients(ROOT, 5)
        self.assertIn("Rolled oats (hercules)", words)
        self.assertFalse([w for w in words if re.search(r"\d", w)])


class Library(unittest.TestCase):
    def setUp(self):
        self.dishes = pv.parse_dishes(pv.read_dishes(ROOT))

    def test_child_safety_notes(self):
        for i, d in self.dishes.items():
            if "Walnuts" in (d.get("buy") or ""):
                self.assertIn("ground", d.get("son") or "", i)            # never whole for the son
            if "Chickpeas" in (d.get("buy") or "") and d.get("slot") == "main":
                self.assertIn("Mash", d.get("son") or "", i)

    def test_refs_are_allowlisted_and_new_dishes_have_one(self):
        for i, d in self.dishes.items():
            if d.get("ref"):
                self.assertIsNotNone(pv.recipe_ref(d), i)
            if d.get("status") == "new":
                self.assertTrue(d.get("ref"), "%s is new to the family but has no recipe" % i)

    def test_porridge_says_how_it_is_made(self):
        self.assertIn("water or lactose-free milk", self.dishes["bf-hercules"]["name"])

    def test_no_dish_name_offers_two_dishes(self):
        for i, d in self.dishes.items():
            if d.get("slot") not in ("—", "side"):
                self.assertIsNone(re.search(r" or [A-Z]", d["name"]), i)   # "Dolma or Stew"

    def test_short_names(self):
        self.assertEqual(mg.short_name("Harissa — chicken and wheat porridge"), "Harissa")
        self.assertEqual(mg.short_name("Sheet-pan salmon with vegetables"), "Sheet-pan salmon")


class EditsAndFailures(unittest.TestCase):
    def setUp(self):
        self.root = copy_root()
        self.dishes = pv.parse_dishes(pv.read_dishes(self.root))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _path(self, w):
        return os.path.join(self.root, "plan", "meals", "week-%02d.md" % w)

    def test_hand_edited_week_wins_and_later_weeks_follow(self):
        with open(self._path(8), encoding="utf-8") as f:
            md = f.read()
        mon = pv.parse_week(md)["days"]["Fri"]["lunch"]
        md = md.replace("| %s |" % mon, "| `ln-fish-bake` + `sd-buckwheat` |", 1)
        with open(self._path(8), "w", encoding="utf-8") as f:
            f.write(md)
        w8 = mg.week_menu(self.root, self.dishes, 8)
        self.assertEqual(w8["days"]["Fri"]["lunch"], "`ln-fish-bake` + `sd-buckwheat`")
        w9 = mg.week_menu(self.root, self.dishes, 9)
        self.assertNotIn("ln-fish-bake", [i for _, _, i in mains(w9)])  # rests after the edit

    def test_rule_broken_by_a_hand_edit_is_reported(self):
        with open(self._path(5), encoding="utf-8") as f:
            md = f.read()
        md = re.sub(r"`(ln-fish-bake|fs-[a-z-]+)`", "`dn-omelette`", md)
        with open(self._path(5), "w", encoding="utf-8") as f:
            f.write(md)
        w = mg.week_menu(self.root, self.dishes, 5)
        self.assertTrue(any("fish 0×" in x for x in w["warnings"]), w["warnings"])

    def test_no_fish_in_the_library_fails_loudly_not_silently(self):
        no_fish = {k: v for k, v in self.dishes.items() if v.get("slot") != "fish"}
        for w in range(5, 9):
            os.remove(self._path(w))
        with self.assertRaises(mg.GenerationError):
            mg.week_menu(self.root, no_fish, 5)
        plan = pv.load_plan(self.root)
        plan["dishes"] = no_fish
        menu = pv.load_week(self.root, 5, no_fish)
        self.assertTrue(menu["missing"])
        self.assertIn("fish", menu["error"])
        _, body, _ = pt.week_parts(plan, 5, plan["start"])
        self.assertEqual(body, [pt.esc(pt.MISSING)])

    def test_write_command(self):
        for w in range(5, 9):
            os.remove(self._path(w))
        md = mg.render_md(5, pv.plan_start(self.root), mg.week_menu(self.root, self.dishes, 5))
        parsed = pv.parse_week(md)
        self.assertEqual(sorted(parsed["days"]), sorted(pv.DAYS))
        self.assertEqual([b[0] for b in parsed["batch"]], ["Sunday", "Wednesday"])


class WeekMessage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = pv.load_plan(ROOT)

    def test_rich_week_five(self):
        from datetime import date
        rich, plain, btns, menu = pt.week_rich(self.plan, date(2026, 11, 15), "https://app.example")
        self.assertIn("Week 5 · 16–22 Nov", rich)
        self.assertEqual(rich.count("<details>"), 8)
        self.assertIn("✨", rich)                                       # new dishes marked
        self.assertIn("This week: fish 2×", rich)
        self.assertNotIn("](", rich + plain)                            # no Markdown links
        self.assertNotIn("plan/", rich + plain)                         # no file paths
        self.assertNotIn("Home →", rich + plain)
        refs = {pv.recipe_ref(d)[0] for d in self.plan["dishes"].values() if pv.recipe_ref(d)}
        for url in pt.urls(rich):
            self.assertIn(url, refs)
        self.assertLessEqual(len(plain), pt.LIMIT)
        self.assertIn("tg-button-row", rich)


if __name__ == "__main__":
    unittest.main()
