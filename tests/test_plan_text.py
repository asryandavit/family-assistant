"""Plan messages and Home sections (decision 085): content from the real plan files,
the link rule, forbidden words, size, unknown ids, videos, delivery to both chats and
the /today route. Telegram is stubbed and the Runs log is skipped: nothing is sent."""
import os
import shutil
import unittest
from datetime import date, datetime, timedelta
from unittest import mock

import listener
from coach import plan_text as pt
from coach import plan_view as pv
from jobs import coach_brief
from lib import config, telegram, ui
from lib import exercise_videos as xv
from tests.test_listener_ux import FakeRunner, Recorder
from tests.test_plan_view import ROOT, START, copy_root

# every day of the 12 weeks plus one week either side
DAYS = [START + timedelta(days=i) for i in range(-7, 7 * 13)]


def all_texts(plan, day):
    return {"today": pt.today_text(plan, day), "training": pt.training_text(plan, day),
            "meals": pt.meals_text(plan, day), "morning": pt.morning_text(plan, day),
            "week": pt.week_text(plan, day)}


def allowed_url(url, plan):
    """The link rule: a verified video, an allowlisted dish ref, or a code-built search."""
    if url.startswith(pv.YOUTUBE_SEARCH):
        return True
    if url in {v["video_url"] for v in plan["videos"].values()}:
        return True
    refs = {pv.recipe_ref(d)[0] for d in plan["dishes"].values() if pv.recipe_ref(d)}
    return url in refs


def write_videos(root):
    """A generated exercise-videos.md: one verified row, one unverified, one off-YouTube."""
    with open(os.path.join(root, "plan", "training", "exercises.md"), encoding="utf-8") as f:
        lib = xv.parse_library(f.read())
    rows = []
    for r in lib:
        r = dict(r)
        if r["id"] == "ex-bridge":
            r.update(video_url="https://www.youtube.com/watch?v=AAAAAAAAAAA", video_title="Glute bridge how-to",
                     channel="Some Physio", duration_sec=95, verified_at="2026-10-21")
        elif r["id"] == "ex-calf":
            r.update(video_url="https://www.youtube.com/watch?v=BBBBBBBBBBB", video_title="Calf raise")
        elif r["id"] == "ex-birddog":
            r.update(video_url="https://example.com/v", video_title="x", verified_at="2026-10-21")
        rows.append(r)
    with open(os.path.join(root, "plan", "training", "exercise-videos.md"), "w", encoding="utf-8") as f:
        f.write(xv.render(rows, {}, today="2026-10-21"))


class RealPlanMessages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = pv.load_plan(ROOT)

    def test_today_wednesday_week_one(self):
        t = pt.today_text(self.plan, date(2026, 10, 21))
        self.assertIn("Week 1 of 12", t)
        self.assertIn("Bean stew (lobi) with herbs", t)                 # lunch by id
        self.assertIn("Batch: lobi", t)                                 # prep for tomorrow
        self.assertIn("<b>Davit</b> 18:15 · Strength B", t)
        self.assertIn("<b>Karine</b> 13:45–15:30 · Foundations", t)
        self.assertIn("Reverse lunge, holding the wall", t)             # Davit's exercise
        self.assertIn(pv.FIRST_TIME, t)                                 # first Strength B
        self.assertIn("Habit:", t)
        self.assertIn(pt.SAFETY, t)
        self.assertNotIn("`", t)                                        # no raw ids left

    def test_walk_day(self):
        t = pt.today_text(self.plan, date(2026, 10, 20))
        self.assertIn("<b>Davit</b> no session today · walk", t)

    def test_meals_week_folded_per_day_with_refs(self):
        t = pt.meals_text(self.plan, date(2026, 10, 21))
        self.assertEqual(t.count("<blockquote expandable>"), 8)        # 7 days + notes
        self.assertIn("Wed 21 Oct · today", t)
        self.assertIn('href="https://www.bbcgoodfood.com/recipes/spiced-carrot-lentil-soup"', t)
        for line in t.splitlines():
            self.assertLessEqual(line.count("recipe:"), 1, line)       # at most one per meal

    def test_week_message_points_to_basket(self):
        t = pt.week_text(self.plan, date(2026, 10, 25))
        self.assertIn("Week 2", t)
        self.assertIn("showing week 1's", t)                           # week-02.md not written
        self.assertIn("Basket", t)

    def test_training_section_has_safety_and_cues(self):
        t = pt.training_text(self.plan, date(2026, 10, 21))
        self.assertIn("Hand on wall.", t)
        self.assertIn("<b>Safety</b>", t)

    def test_every_day_size_links_and_words(self):
        for day in DAYS:
            for kind, t in all_texts(self.plan, day).items():
                self.assertLessEqual(len(t), telegram.LIMIT, (day, kind))
                self.assertEqual(pt.forbidden_words(t), [], (day, kind))
                for u in pt.urls(t):
                    self.assertTrue(allowed_url(u, self.plan), (day, kind, u))
                for word in ("kcal", "calorie", "macro", "check-in"):
                    self.assertNotIn(word, t.lower(), (day, kind))

    def test_cues_kept_on_normal_days(self):
        # 2-3 cues per exercise is the aim; check a heavy day still has two
        t = pt.training_text(self.plan, date(2026, 10, 21))
        self.assertIn("Step one foot back and lower the back knee towards the floor, return.", t)

    def test_forbidden_word_scanner(self):
        self.assertEqual(pt.forbidden_words("a <b>Treatment</b> plan"), ["treatment"])
        self.assertEqual(pt.forbidden_words("Low-impact conditioning"), [])


class EdgeCases(unittest.TestCase):
    def setUp(self):
        self.root = copy_root()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _edit(self, rel, old, new):
        p = os.path.join(self.root, *rel.split("/"))
        with open(p, encoding="utf-8") as f:
            s = f.read()
        self.assertIn(old, s)
        with open(p, "w", encoding="utf-8") as f:
            f.write(s.replace(old, new))

    def test_unknown_ids_shown_not_crashing(self):
        self._edit("plan/meals/week-01.md", "`bf-katnashor` | `ln-lobi`", "`bf-mystery` | `ln-lobi`")
        self._edit("plan/family/davit.md", "| 1 | `ex-lunge-assist` |", "| 1 | `ex-moonwalk` |")
        plan = pv.load_plan(self.root)
        t = pt.today_text(plan, date(2026, 10, 21))
        self.assertIn("<code>bf-mystery</code> <i>(not in the dish list)</i>", t)
        self.assertIn("<code>ex-moonwalk</code> <i>(not in the exercise library)</i>", t)

    def test_video_fallback_without_file(self):
        plan = pv.load_plan(self.root)
        t = pt.training_text(plan, date(2026, 10, 19))
        self.assertIn(pv.YOUTUBE_SEARCH + "Glute+bridge+form+tutorial", t)
        self.assertNotIn("youtube.com/watch", t)

    def test_verified_video_used_unverified_ignored(self):
        write_videos(self.root)
        plan = pv.load_plan(self.root)
        self.assertEqual(set(plan["videos"]), {"ex-bridge"})
        t = pt.training_text(plan, date(2026, 10, 19))
        self.assertIn('Video: <a href="https://www.youtube.com/watch?v=AAAAAAAAAAA">Glute bridge how-to</a> '
                      "(Some Physio)", t)
        self.assertNotIn("BBBBBBBBBBB", t)
        self.assertNotIn("example.com", t)
        for u in pt.urls(t):
            self.assertTrue(allowed_url(u, plan), u)

    def test_video_never_swaps_an_exercise(self):
        write_videos(self.root)
        with_v = pv.load_plan(self.root)
        os.remove(os.path.join(self.root, "plan", "training", "exercise-videos.md"))
        without = pv.load_plan(self.root)
        for day in (date(2026, 10, 19), date(2026, 11, 2), date(2026, 12, 21)):
            for p in pv.PEOPLE:
                a = [pv.session_ids(o["detail"]) for o in pv.person_day(with_v, p, pv.week_of(day, START), day)["options"]]
                b = [pv.session_ids(o["detail"]) for o in pv.person_day(without, p, pv.week_of(day, START), day)["options"]]
                self.assertEqual(a, b)

    def test_ref_off_allowlist_not_shown(self):
        self._edit("plan/meals/dishes.md", "https://www.bbcgoodfood.com/recipes/spiced-carrot-lentil-soup",
                   "https://example.com/lentils")
        t = pt.meals_text(pv.load_plan(self.root), date(2026, 10, 21))
        self.assertNotIn("example.com", t)

    def test_missing_week_said_out_loud(self):
        plan = pv.load_plan(self.root)
        t = pt.today_text(plan, date(2026, 11, 4))                     # week 3, no week-03.md
        self.assertIn("No menu for week 3 yet — showing week 1's.", t)

    def test_section_survives_a_broken_plan(self):
        shutil.rmtree(os.path.join(self.root, "plan", "family"))
        os.remove(os.path.join(self.root, "plan", "training", "exercises.md"))
        with mock.patch("coach.plan_view.load_plan", side_effect=ValueError("boom")):
            text, rows = ui.section("today", self.root)
        self.assertIn("couldn't be read", text)
        self.assertEqual(rows[-1], [ui.HOME_BACK])


class Sections(unittest.TestCase):
    def test_live_sections_keep_drive_links_and_home(self):
        links = ui.plan_links(ROOT)
        for name, key in (("today", "rhythm"), ("meals", "week"), ("training", "davit")):
            text, rows = ui.section(name, ROOT)
            self.assertLessEqual(len(text), telegram.LIMIT, name)
            self.assertNotIn("couldn't be read", text, name)
            self.assertEqual(rows[-1], [ui.HOME_BACK], name)
            self.assertIn(links[key], [u for row in rows for _, u in row], name)

    def test_today_hook_receives_the_chat(self):
        seen = []
        with mock.patch("coach.plan_text.today_extras",
                        side_effect=lambda plan, p, day, chat_id=None: seen.append((p, chat_id)) or []):
            ui.section("today", ROOT, chat_id="222")
        self.assertEqual(seen, [("davit", "222"), ("karine", "222")] * (len(seen) // 2))
        self.assertTrue(seen)


class Delivery(unittest.TestCase):
    ENV = {"TELEGRAM_BOT_TOKEN": "x", "TELEGRAM_CHAT_ID": "111", "TELEGRAM_CHAT_ID_2": "222"}

    def setUp(self):
        self.cfg = config.load()

    def _run(self, kind, hhmm, **kw):
        posted = []
        now = datetime(2026, 10, 21, *hhmm, tzinfo=ui.YEREVAN)
        with mock.patch.dict(os.environ, self.ENV), \
                mock.patch.object(telegram, "_post", lambda tok, p: posted.append(p)), \
                mock.patch.object(coach_brief, "_log", lambda *a: None):
            os.environ.pop(telegram.REPLY_CHAT_ENV, None)
            status, _ = coach_brief.run(self.cfg, kind, now=now, **kw)
        return status, posted

    def test_morning_to_both_chats_silent(self):
        status, posted = self._run("morning", (7, 30))
        self.assertEqual(status, "sent")
        self.assertEqual(sorted(p["chat_id"] for p in posted), ["111", "222"])
        self.assertTrue(all(p["disable_notification"] for p in posted))
        self.assertTrue(all("Good morning" in p["text"] for p in posted))

    def test_late_morning_dropped(self):
        status, posted = self._run("morning", (10, 5))
        self.assertEqual((status, posted), ("dropped", []))
        self.assertEqual(self._run("morning", (9, 59))[0], "sent")

    def test_week_to_both_chats(self):
        status, posted = self._run("week", (18, 0), day=date(2026, 10, 25))
        self.assertEqual(status, "sent")
        self.assertEqual(sorted(p["chat_id"] for p in posted), ["111", "222"])

    def test_failure_tells_owner_only(self):
        notes = []
        with mock.patch.object(coach_brief, "build", side_effect=ValueError("bad file")), \
                mock.patch.object(telegram, "notify", lambda cfg, t: notes.append(t)):
            status, posted = self._run("morning", (7, 30))
        self.assertEqual((status, posted), ("failed", []))
        self.assertIn("bad file", notes[0])


class TodayCommand(unittest.TestCase):
    def test_today_replies_to_the_asker(self):
        cfg, r = config.load(), FakeRunner()
        with Recorder() as rec:
            out = listener.handle_text(cfg, r, "/today", "222")
        self.assertIsNone(out)
        text, kw = rec.sent[-1]
        self.assertEqual(kw["chat_id"], "222")
        self.assertTrue(kw["silent"])
        self.assertIn("Today", text)
        self.assertEqual(kw["buttons"][-1], [ui.HOME_BACK])

    def test_today_in_help_and_menu(self):
        self.assertIn("/today", listener.HELP)


if __name__ == "__main__":
    unittest.main()
