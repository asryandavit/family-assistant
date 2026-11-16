"""Mini App Stage B, Today (decision 108): today's meals with recipe links and the batch note on
top, this week's generated menu below with today open, next week as its own page.

Built from the public pieces of coach/plan_text (week_parts at full detail, meal_lines with
refs) instead of the chat texts, which drop links to fit one Telegram message. The drift tests
compare with the chat's own text so the two cannot silently disagree. Real plan files; the
dates are fixed (a Monday and a Sunday of plan week 4)."""
import json
import os
import unittest
from datetime import date
from unittest import mock

from coach import plan_text as pt
from coach import plan_view as pv
from miniapp import menus, screens

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MON = date(2026, 11, 9)       # week 4, a day whose dishes have recipe links
SUN = date(2026, 11, 15)      # week 4's Sunday: the batch session for next week is cooked today


def text_of(block):
    return "".join(s["t"] for s in block["s"])


def paragraphs(page):
    return [text_of(b) for b in page["blocks"] if b["k"] == "p"]


def folds(page):
    return [b for b in page["blocks"] if b["k"] == "fold"]


def links(blocks):
    n = 0
    for b in blocks:
        for p in ([b] if b["k"] == "p" else b["b"]):
            n += sum(1 for s in p["s"] if s.get("a"))
    return n


def chat(day, fn, *a):
    plan = pv.load_plan(ROOT)
    return screens.html_blocks(fn(plan, day, *a))


class Today(unittest.TestCase):
    def setUp(self):
        self.page = menus.today_page(ROOT, "111", MON)

    def test_title_and_meals_on_top(self):
        self.assertTrue(self.page["title"].startswith("📅 Today"))
        ps = paragraphs(self.page)
        for label in ("Breakfast", "Lunch", "Dinner"):
            self.assertTrue(any(p.startswith(label) for p in ps), label)

    def test_recipe_links_are_there(self):
        first_meals = [b for b in self.page["blocks"] if b["k"] == "p"][:6]
        self.assertGreaterEqual(links(first_meals), 1)

    def test_meal_lines_match_the_chat_apart_from_links(self):
        c = chat(MON, pt.today_text, "111")
        want = [text_of(b) for b in c["blocks"] if b["k"] == "p"
                and b["s"][0].get("b") and b["s"][0]["t"] in ("Breakfast", "Lunch", "Dinner")]
        self.assertTrue(want)
        ps = paragraphs(self.page)
        for line in want:
            self.assertTrue(any(p.startswith(line.rstrip()) for p in ps), line)

    def test_this_weeks_menu_follows_with_today_open(self):
        ps = paragraphs(self.page)
        self.assertTrue(any("This week's menu" in p for p in ps))
        titles = [f["title"] for f in folds(self.page)]
        days = [t for t in titles if t[:3] in pv.DAYS]
        self.assertEqual(len(days), 7)
        self.assertEqual([t for t in days if "today" in t], [t for t in days if t.startswith("Mon 9 Nov")])
        self.assertTrue(any(menus.TODAY_ABOVE in t for t in days))   # folded: its meals are on top
        self.assertIn("Every day", titles)

    def test_week_menu_comes_after_the_meals_not_before(self):
        blocks = self.page["blocks"]
        lunch = next(i for i, b in enumerate(blocks) if b["k"] == "p" and text_of(b).startswith("Lunch"))
        first_day = next(i for i, b in enumerate(blocks) if b["k"] == "fold" and b["title"][:3] in pv.DAYS)
        self.assertLess(lunch, first_day)

    def test_training_and_safety_are_kept(self):
        titles = [f["title"] for f in folds(self.page)]
        self.assertIn("Safety", titles)
        ps = " ".join(paragraphs(self.page))
        self.assertIn("Davit", ps)
        self.assertIn("Karine", ps)

    def test_sunday_shows_the_batch_session(self):
        page = menus.today_page(ROOT, "111", SUN)
        self.assertTrue(any(p.startswith("Batch cooking") for p in paragraphs(page)))

    def test_no_markup_survives(self):
        self.assertNotIn("<", json.dumps(self.page, ensure_ascii=False).replace("<br", "")
                         .replace("\\u003c", ""))

    def test_missing_menu_says_so_in_one_sentence(self):
        missing = {"missing": True, "error": "no fish left", "number": 4, "days": {}, "batch": [],
                   "notes": [], "new": [], "warnings": ["no fish left"]}
        with mock.patch.object(pv, "load_week", return_value=missing):
            page = menus.today_page(ROOT, "111", MON)
        self.assertTrue(any(pt.MISSING in p for p in paragraphs(page)))


class MenuPages(unittest.TestCase):
    def test_next_week_matches_the_chats_days_and_has_at_least_its_links(self):
        app = menus.menu_page(ROOT, "week", MON)
        c = chat(MON, pt.week_text)
        self.assertEqual([f["title"] for f in folds(app)], [f["title"] for f in folds(c)])
        self.assertGreaterEqual(links(app["blocks"]), links(c["blocks"]))
        self.assertFalse(any("today" in f["title"] for f in folds(app)))

    def test_this_week_marks_today_and_matches_the_chat(self):
        app = menus.menu_page(ROOT, "meals", MON)
        c = chat(MON, pt.meals_text)
        self.assertEqual([f["title"] for f in folds(app)], [f["title"] for f in folds(c)])
        self.assertGreaterEqual(links(app["blocks"]), links(c["blocks"]))
        self.assertEqual(sum("today" in f["title"] for f in folds(app)), 1)

    def test_full_detail_keeps_son_and_tip_lines(self):
        app = menus.menu_page(ROOT, "meals", MON)
        lines = [text_of(p) for f in folds(app) for p in f["b"]]
        self.assertTrue(any(x.startswith("👶") for x in lines))

    def test_unknown_page(self):
        self.assertIsNone(menus.menu_page(ROOT, "yesterday", MON))


class WiredIntoThePlanPages(unittest.TestCase):
    def test_plan_page_uses_them(self):
        t = screens.plan_page(ROOT, "today", "111")
        self.assertTrue(any(f["title"][:3] in pv.DAYS for f in folds(t)))      # the week is under Today
        w = screens.plan_page(ROOT, "week", "111")
        self.assertTrue(w["title"].startswith("🍽"))

    def test_training_is_unchanged(self):
        self.assertTrue(screens.plan_page(ROOT, "training", "111")["title"].startswith("🏃"))


if __name__ == "__main__":
    unittest.main()
