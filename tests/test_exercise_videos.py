"""lib/exercise_videos.py — the parts that don't need the YouTube API. Titles and oEmbed
responses are real (captured from YouTube on 2026-10-21)."""
import json
import os
import unittest

from lib import exercise_videos as ev

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "youtube")


def _read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


LIB = ev.parse_library(_read("plan", "training", "exercises.md"))
CFG = ev.parse_config(_read("plan", "training", "video-config.md"))

# real search results for "wall push up form tutorial" (2026-10-21)
REAL = [
    {"video_id": "5NPvv40gd3Q", "title": "6: Push-ups against a wall",
     "channel": "Sunnybrook Hospital", "channel_id": "SB", "duration_sec": 72},
    {"video_id": "wIPJvBQs7RA", "title": "How to Do Wall Push Ups: A Guide from Physical Therapists",
     "channel": "Hinge Health", "channel_id": "HH", "duration_sec": 71},
    {"video_id": "YWw-3rGaoT0", "title": "Wall Push-Ups for Absolute Beginners | Easy Upper Body Workout",
     "channel": "Pilates On Demand with Linds", "channel_id": "PD", "duration_sec": 57},
]


class Inputs(unittest.TestCase):
    def test_library(self):
        self.assertEqual(len(LIB), 52)
        wall = next(r for r in LIB if r["id"] == "ex-pushup-wall")
        self.assertEqual((wall["name"], wall["level"], wall["pattern"], wall["equipment"]),
                         ("Wall push-up", 0, "upper body", "wall"))
        self.assertEqual(next(r for r in LIB if r["id"] == "ex-bridge")["equipment"], "mat")
        self.assertEqual(next(r for r in LIB if r["id"] == "cd-stairs")["equipment"], "stairs")
        self.assertEqual(next(r for r in LIB if r["id"] == "mb-chin-tuck")["pattern"], "mobility")

    def test_config(self):
        names = [c["name"] for c in CFG["channels"]]
        self.assertIn("Sunnybrook Hospital", names)
        self.assertNotIn("", names)
        self.assertTrue(all(not n.startswith("*") for n in names))   # placeholder row skipped
        self.assertIn("wall push up", CFG["synonyms"]["ex-pushup-wall"])
        self.assertEqual(CFG["manual"], {})
        self.assertEqual(ev.approved_channel_ids(CFG), set())          # nothing approved yet
        ids = {r["id"] for r in LIB}
        self.assertTrue(set(CFG["synonyms"]) <= ids, set(CFG["synonyms"]) - ids)


class Matching(unittest.TestCase):
    def test_core_name_and_query(self):
        self.assertEqual(ev.core_name("Sit-to-stand (chair)"), "Sit-to-stand")
        self.assertEqual(ev.core_name("Dead bug — heel taps"), "Dead bug")
        self.assertEqual(ev.core_name("Reverse lunge, holding the wall"), "Reverse lunge")
        self.assertEqual(ev.search_query("Wall push-up"), "Wall push-up form tutorial")

    def test_real_titles(self):
        self.assertIsNotNone(ev.title_matches(REAL[0]["title"], "Wall push-up"))   # "Push-ups against a wall"
        self.assertIsNotNone(ev.title_matches(REAL[1]["title"], "Wall push-up"))
        self.assertIsNone(ev.title_matches("Full body HIIT workout", "Wall push-up"))
        self.assertIsNone(ev.title_matches("Glute bridge tutorial", "Wall push-up"))

    def test_synonyms(self):
        self.assertIsNone(ev.title_matches("Diaphragmatic Breathing Technique", "360° breathing"))
        self.assertEqual(ev.title_matches("Diaphragmatic Breathing Technique", "360° breathing",
                                          CFG["synonyms"]["br-360"]), "diaphragmatic breathing")

    def test_iso_and_length(self):
        self.assertEqual(ev.iso_seconds("PT1M12S"), 72)
        self.assertEqual(ev.iso_seconds("PT8M"), 480)
        self.assertEqual(ev.iso_seconds("PT1H2M3S"), 3723)
        self.assertIsNone(ev.iso_seconds("72"))
        self.assertIsNone(ev.iso_seconds(""))
        self.assertTrue(ev.length_ok(60) and ev.length_ok(480))
        self.assertFalse(ev.length_ok(57) or ev.length_ok(481) or ev.length_ok(None))

    def test_choose_follows_every_rule(self):
        # only allowlisted channels count, in search order
        self.assertEqual(ev.choose(REAL, {"HH", "SB"}, "Wall push-up")["video_id"], "5NPvv40gd3Q")
        self.assertEqual(ev.choose(REAL, {"HH"}, "Wall push-up")["video_id"], "wIPJvBQs7RA")
        # under a minute is rejected even from an allowed channel
        self.assertIsNone(ev.choose(REAL, {"PD"}, "Wall push-up"))
        # never widened beyond the allowlist
        self.assertIsNone(ev.choose(REAL, set(), "Wall push-up"))

    def test_video_id_from_url(self):
        for u in ("https://www.youtube.com/watch?v=5NPvv40gd3Q", "https://youtu.be/5NPvv40gd3Q",
                  "https://www.youtube.com/shorts/5NPvv40gd3Q"):
            self.assertEqual(ev.video_id_from_url(u), "5NPvv40gd3Q")
        self.assertIsNone(ev.video_id_from_url("https://example.com/video"))


class FakeResp:
    def __init__(self, status, payload=None):
        self.status_code, self._p = status, payload

    def json(self):
        return self._p


class FakeSession:
    def __init__(self, resp=None, error=None):
        self.resp, self.error, self.calls = resp, error, []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if self.error:
            raise self.error
        return self.resp


class LinkCheck(unittest.TestCase):
    def test_public_video(self):
        with open(os.path.join(FIX, "oembed_public.json"), encoding="utf-8") as f:
            real = json.load(f)
        s = FakeSession(FakeResp(real["status"], real["json"]))
        r = ev.check_link("https://www.youtube.com/watch?v=5NPvv40gd3Q", s)
        self.assertEqual((r["ok"], r["channel"]), (True, "Sunnybrook Hospital"))
        self.assertEqual(s.calls[0][0], ev.OEMBED)

    def test_missing_private_or_error(self):
        with open(os.path.join(FIX, "oembed_missing.json"), encoding="utf-8") as f:
            real = json.load(f)
        self.assertFalse(ev.check_link("x", FakeSession(FakeResp(real["status"])))["ok"])  # 400
        self.assertFalse(ev.check_link("x", FakeSession(FakeResp(401)))["ok"])              # private
        r = ev.check_link("x", FakeSession(error=OSError("timeout")))
        self.assertFalse(r["ok"])
        self.assertIn("timeout", r["status"])


class GeneratedFile(unittest.TestCase):
    def test_render_parse_roundtrip(self):
        rows = [dict(LIB[0], video_url=None),
                dict(next(r for r in LIB if r["id"] == "ex-pushup-wall"),
                     video_url="https://www.youtube.com/watch?v=5NPvv40gd3Q",
                     video_title="6: Push-ups | against a wall", channel="Sunnybrook Hospital",
                     duration_sec=72, verified_at="2026-10-21")]
        report = {"seeded": 1, "verified": 1, "failed": 0, "manual": [("br-360", "360° breathing")]}
        md = ev.render(rows, report, today="2026-10-21")
        back = ev.parse_generated(md)
        self.assertIsNone(back["br-360"]["video_url"])
        w = back["ex-pushup-wall"]
        self.assertEqual((w["video_url"], w["duration_sec"], w["verified_at"]),
                         ("https://www.youtube.com/watch?v=5NPvv40gd3Q", 72, "2026-10-21"))
        self.assertEqual(w["video_title"], "6: Push-ups / against a wall")    # '|' made safe
        self.assertIn("- `br-360`", md)
        self.assertIn("seeded 1 · verified 1 · failed 0", md)


if __name__ == "__main__":
    unittest.main()
