"""coach/plan_view.py against the real plan files (decision 085): ids, week number,
calendar, session lookup, first appearance, fallbacks. Edge cases run on a copy of
plan/ in a temp folder; the real files are never changed."""
import os
import shutil
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

from coach import plan_view as pv
from lib import ui

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
START = date(2026, 10, 19)


def copy_root():
    """A temp root with plan/ and config_coach.json copied in."""
    tmp = tempfile.mkdtemp()
    shutil.copytree(os.path.join(ROOT, "plan"), os.path.join(tmp, "plan"))
    shutil.copy(os.path.join(ROOT, "config_coach.json"), tmp)
    return tmp


class RealFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = pv.load_plan(ROOT)

    def test_start_date_from_config(self):
        self.assertEqual(self.plan["start"], START)

    def test_dishes_and_exercises_by_id(self):
        self.assertEqual(self.plan["dishes"]["ln-lobi"]["name"], "Bean stew (lobi) with herbs")
        self.assertEqual(self.plan["exercises"]["ex-bridge"]["name"], "Glute bridge")
        self.assertIn("squeeze glutes", self.plan["exercises"]["ex-bridge"]["how"])

    def test_every_id_used_by_the_plan_exists(self):
        menu = pv.load_week(ROOT, 1)
        for d, meals in menu["days"].items():
            for cell in meals.values():
                for i in pv.ids_in(cell):
                    self.assertIn(i, self.plan["dishes"], (d, i))
        for p in pv.PEOPLE:
            for ex in pv.first_appearance(self.plan["calendar"], self.plan["people"][p], p):
                self.assertIn(ex, self.plan["exercises"], (p, ex))

    def test_week_one_wednesday(self):
        menu = pv.load_week(ROOT, 1)
        wed = menu["days"]["Wed"]
        self.assertEqual(pv.ids_in(wed["lunch"]), ["ln-lobi", "ln-bulgur"])
        self.assertEqual(wed["prep"], "Batch: lobi")
        self.assertFalse(menu["fell_back"])
        self.assertEqual([b[0] for b in menu["batch"]], ["Sunday", "Wednesday"])

    def test_calendar_and_times(self):
        cal = self.plan["calendar"]
        self.assertEqual(pv.day_cell(cal, "davit", 1, "Mon"), "Strength A")
        self.assertEqual(pv.day_cell(cal, "davit", 6, "Tue"), "Cardio")
        self.assertEqual(pv.day_cell(cal, "karine", 2, "Thu"), "Foundations")
        self.assertEqual(pv.day_cell(cal, "karine", 3, "Tue"), "walk")
        self.assertEqual(pv.day_cell(cal, "davit", 10, "Fri"), "—")
        self.assertEqual(self.plan["times"], {"davit": "18:15", "karine": "13:45–15:30"})

    def test_sessions_resolve(self):
        dv, kr = self.plan["people"]["davit"], self.plan["people"]["karine"]
        a = pv.session_detail(dv, 1, "Strength A")
        self.assertEqual(pv.session_ids(a)[0], "ex-sit-stand")
        self.assertEqual(len(a["rows"]), 5)
        # weeks 5-8 say "same shape": exercises come from weeks 1-4
        a6 = pv.session_detail(dv, 6, "Strength A")
        self.assertEqual((a6["block"]["from"], a6["source"]["from"]), (5, 1))
        cardio = pv.session_detail(dv, 6, "Cardio")
        self.assertEqual(pv.session_ids(cardio), ["cd-stairs", "cd-circuit-low"])
        self.assertEqual(pv.session_ids(pv.session_detail(dv, 10, "Cardio")),
                         ["cd-stairs-int", "cd-circuit-low"])
        f = pv.session_detail(kr, 1, "Foundations")
        self.assertEqual(len(pv.session_ids(f)), 7)
        self.assertEqual(pv.session_ids(pv.session_detail(kr, 4, "Session 2"))[0], "ex-lunge-assist")
        self.assertEqual(pv.session_ids(pv.session_detail(kr, 10, "Cardio")), ["cd-circuit-low"])

    def test_cues_drop_doses(self):
        c = pv.cues(self.plan["exercises"]["ex-birddog"]["how"])
        self.assertTrue(2 <= len(c) <= 3)
        self.assertFalse(any(s[0].isdigit() for s in c))

    def test_first_appearance(self):
        dv = pv.first_appearance(self.plan["calendar"], self.plan["people"]["davit"], "davit")
        self.assertEqual(dv["ex-sit-stand"], (1, 0))          # week 1 Monday, Strength A
        self.assertEqual(dv["ex-lunge-assist"], (1, 2))       # week 1 Wednesday, Strength B
        self.assertEqual(dv["cd-stairs"], (5, 1))             # first Cardio, week 5 Tuesday
        self.assertEqual(dv["cd-stairs-int"], (9, 1))
        kr = pv.first_appearance(self.plan["calendar"], self.plan["people"]["karine"], "karine")
        self.assertEqual(kr["br-360"], (1, 0))
        self.assertEqual(kr["ex-chair-squat"], (3, 0))        # Session 1, week 3
        # deterministic: same answer twice
        self.assertEqual(dv, pv.first_appearance(self.plan["calendar"], self.plan["people"]["davit"], "davit"))

    def test_first_today_only_on_that_day(self):
        wed = pv.person_day(self.plan, "davit", 1, date(2026, 10, 21))
        self.assertIn("ex-lunge-assist", wed["first_today"])
        fri = pv.person_day(self.plan, "davit", 1, date(2026, 10, 23))
        self.assertEqual(fri["first_today"], set())           # Strength A again
        later = pv.person_day(self.plan, "davit", 2, date(2026, 10, 28))
        self.assertEqual(later["first_today"], set())

    def test_walk_and_rest_days(self):
        self.assertEqual(pv.person_day(self.plan, "davit", 1, date(2026, 10, 20))["kind"], "walk")
        self.assertEqual(pv.person_day(self.plan, "davit", 10, date(2026, 12, 25))["kind"], "rest")

    def test_habit_nudge_is_from_habits_md(self):
        n = pv.nudge_for(self.plan["habits"], date(2026, 10, 21))
        self.assertTrue(n)
        all_ = pv.habit_nudges(self.plan["habits"])
        self.assertIn("After coffee #1: 5 min mobility.", all_)


class WeekNumber(unittest.TestCase):
    def test_around_the_start(self):
        self.assertEqual(pv.week_of(START - timedelta(days=1), START), 0)
        self.assertEqual(pv.week_of(START, START), 1)
        self.assertEqual(pv.week_of(START + timedelta(days=6), START), 1)
        self.assertEqual(pv.week_of(START + timedelta(days=7), START), 2)
        self.assertEqual(pv.week_of(START + timedelta(days=83), START), 12)
        self.assertEqual(pv.week_of(START + timedelta(days=84), START), 13)
        self.assertEqual(pv.week_of(START, None), 0)

    def test_yerevan_midnight(self):
        # 20:30 UTC Sunday = 00:30 Monday in Yerevan: the local date is already week 2
        utc = datetime(2026, 10, 25, 20, 30, tzinfo=timezone.utc)
        local = utc.astimezone(ui.YEREVAN).date()
        self.assertEqual(local, date(2026, 10, 26))
        self.assertEqual(pv.week_of(local, START), 2)
        self.assertEqual(pv.week_of(utc.date(), START), 1)     # the UTC date would be wrong
        self.assertEqual(pv.weekday(local), "Mon")

    def test_before_start_shows_week_one(self):
        plan = pv.load_plan(ROOT)
        info = pv.today_info(plan, date(2026, 10, 18))
        self.assertTrue(info["before_start"])
        self.assertEqual(info["menu"]["number"], 1)


class Fallbacks(unittest.TestCase):
    def setUp(self):
        self.root = copy_root()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_missing_week_falls_back_to_latest(self):
        w = pv.load_week(self.root, 5)
        self.assertEqual((w["number"], w["fell_back"]), (1, True))
        shutil.copy(os.path.join(self.root, "plan", "meals", "week-01.md"),
                    os.path.join(self.root, "plan", "meals", "week-03.md"))
        self.assertEqual(pv.load_week(self.root, 5)["number"], 3)
        self.assertEqual(pv.load_week(self.root, 1)["number"], 1)

    def test_no_week_file_at_all(self):
        os.remove(os.path.join(self.root, "plan", "meals", "week-01.md"))
        self.assertIsNone(pv.load_week(self.root, 1))

    def test_no_start_date(self):
        with open(os.path.join(self.root, "config_coach.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        self.assertIsNone(pv.plan_start(self.root))

    def test_no_video_file(self):
        self.assertFalse(os.path.exists(os.path.join(self.root, "plan", "training", "exercise-videos.md")))
        self.assertEqual(pv.load_videos(self.root), {})

    def test_recipe_ref_allowlist(self):
        self.assertEqual(pv.recipe_ref({"ref": "https://www.bbcgoodfood.com/recipes/x"})[1], "BBC Good Food")
        self.assertIsNone(pv.recipe_ref({"ref": "https://example.com/recipe"}))
        self.assertIsNone(pv.recipe_ref({"ref": "http://www.bbcgoodfood.com/recipes/x"}))
        self.assertIsNone(pv.recipe_ref({"ref": None}))


if __name__ == "__main__":
    unittest.main()
