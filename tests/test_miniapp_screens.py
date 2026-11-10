"""Mini App step 2 (decision 098): the screen builders, the form actions, and the endpoints.

Fixtures are real: basket_weekly.json is the file the basket job saved on 2026-10-19, travel_rows
.json holds the latest Trips/Stays rows read from the travel Sheet on 2026-11-10. The plan pages
run the real plan code on the committed plan/ files. Market edits run against a temp data dir;
Telegram, the Sheet and the listener are never touched."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from lib import config
from miniapp import actions, inbox, people, screens
from tests.test_miniapp_server import ADULT, OWNER, STRANGER, Base, init_data

F = os.path.join(os.path.dirname(__file__), "fixtures", "miniapp")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fixture(name):
    with open(os.path.join(F, name), encoding="utf-8") as f:
        return json.load(f)


class HtmlBlocks(unittest.TestCase):
    def test_structure(self):
        h = ("📅 <b>Today</b> · <i>Tue 10 Nov</i>\n━━━━━━━━━━━━\n<b>Lunch</b> soup &amp; bread\n"
             '<a href="https://x.am/a?b=1">link</a> <a href="javascript:alert(1)">bad</a>\n'
             "<blockquote expandable><b>Safety</b>\nStop at chest pain.\nCall a doctor.</blockquote>")
        p = screens.html_blocks(h)
        self.assertEqual(p["title"], "📅 Today · Tue 10 Nov")
        kinds = [b["k"] for b in p["blocks"]]
        self.assertEqual(kinds, ["p", "p", "fold"])                     # the ━━ divider is gone
        self.assertEqual(p["blocks"][0]["s"], [{"t": "Lunch", "b": 1}, {"t": " soup & bread"}])
        segs = p["blocks"][1]["s"]
        self.assertEqual(segs[0], {"t": "link", "a": "https://x.am/a?b=1"})
        self.assertNotIn("a", segs[-1])                                   # javascript: dropped
        fold = p["blocks"][2]
        self.assertEqual(fold["title"], "Safety")
        self.assertEqual([b["s"][0]["t"] for b in fold["b"]], ["Stop at chest pain.", "Call a doctor."])

    def test_no_markup_survives(self):
        p = screens.html_blocks("<b>a</b> <code>x</code> <i>y</i>\n\n<b>z</b>")
        flat = json.dumps(p)
        self.assertNotIn("<", flat)

    def test_empty(self):
        self.assertEqual(screens.html_blocks(""), {"title": "", "blocks": []})
        self.assertEqual(screens.plain("a <b>b</b> &amp; c"), "a b & c")


class Plan(unittest.TestCase):
    def test_every_page_builds_from_the_real_plan(self):
        for name in screens.PLAN_NAMES:
            p = screens.plan_page(ROOT, name, "111")
            self.assertTrue(p and p["title"] and p["blocks"], name)
            self.assertNotIn("<", json.dumps(p), name)

    def test_unknown_name(self):
        self.assertIsNone(screens.plan_page(ROOT, "nope", "111"))

    def test_unreadable_plan_is_none(self):
        with mock.patch("coach.plan_view.load_plan", side_effect=OSError("gone")):
            self.assertIsNone(screens.plan_page(ROOT, "today", "111"))


class BasketView(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, ".browser"))
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_real_file(self):
        shutil.copy(os.path.join(F, "basket_weekly.json"), os.path.join(self.root, ".browser"))
        v = screens.basket_view(self.root, "weekly")
        raw = fixture("basket_weekly.json")
        self.assertFalse(v["empty"])
        self.assertEqual(v["total"], "15,521 ֏")
        self.assertEqual([(g["shop"], g["subtotal"], len(g["items"])) for g in v["groups"]],
                         [("yc", "12,179 ֏", 16), ("parma", "3,342 ֏", 7)])
        priced = [e for e in raw["lines"] if e["status"] == "ok"]
        self.assertEqual(sum(len(g["items"]) for g in v["groups"]), len(priced))
        self.assertEqual(len(v["unpriced"]) + len(v["skipped"]) + len(priced), len(raw["lines"]))
        self.assertIn("22 items at both shops", v["compare"])
        self.assertTrue(all(i["url"] is None or i["url"].startswith("https://")
                            for g in v["groups"] for i in g["items"]))
        self.assertRegex(v["when"], r"^\d\d \w{3} \d\d:\d\d$")

    def test_missing_file_and_bad_kind(self):
        self.assertEqual(screens.basket_view(self.root, "monthly"), {"empty": True, "kind": "monthly"})
        self.assertIsNone(screens.basket_view(self.root, "yearly"))

    def test_corrupt_file_is_empty(self):
        with open(os.path.join(self.root, ".browser", "basket_weekly.json"), "w") as f:
            f.write("{nope")
        self.assertTrue(screens.basket_view(self.root, "weekly")["empty"])


class TravelView(unittest.TestCase):
    def rows(self, tab):
        return fixture("travel_rows.json")[tab]

    def view(self, **over):
        with mock.patch("lib.tasks.query", return_value={"exists": True, "enabled": True,
                                                          "next_run": "x", "last_run": "y"}), \
                mock.patch("lib.tasks._short_dt", side_effect=lambda s: f"@{s}"):
            return screens.travel_view({}, rows_fn=over.get("rows_fn", self.rows))

    def test_real_rows(self):
        v = self.view()
        self.assertEqual(v["run_date"], "2026-11-10")
        totals = [float(t["total"].replace(",", "")) for t in v["trips"]]
        self.assertEqual(totals, sorted(totals))                          # cheapest first
        self.assertLessEqual(len(v["trips"]), 8)
        self.assertEqual(v["trips"][0]["route"], "BRI")
        self.assertEqual(v["trips"][0]["total"], "158")
        scores = [s for s in v["stays"]]
        self.assertTrue(scores and len(scores) <= 6)
        self.assertTrue(all(s["url"] is None or s["url"].startswith("https://") for s in scores))
        self.assertEqual(v["scan"], {"enabled": True, "next": "@x", "last": "@y"})

    def test_stays_best_score_first(self):
        raw = self.rows("Stays")
        want = max(raw, key=lambda r: float(r[14]))
        self.assertEqual(self.view()["stays"][0]["name"], want[6])

    def test_sheet_unavailable(self):
        v = self.view(rows_fn=lambda tab: [])
        self.assertTrue(v["unavailable"])
        self.assertEqual((v["trips"], v["stays"]), ([], []))

    def test_short_rows_ignored(self):
        v = self.view(rows_fn=lambda tab: [["2026-11-10", "x"]])
        self.assertTrue(v["unavailable"])

    def test_cache_does_not_keep_failures(self):
        screens._cache.clear()
        calls = []
        with mock.patch("lib.sheets.read_all", side_effect=lambda cfg, tab: calls.append(tab) or []):
            screens._sheet_rows({}, "Trips", now=1000.0)
            screens._sheet_rows({}, "Trips", now=1001.0)
        self.assertEqual(len(calls), 2)                                    # empty = failed, not cached
        with mock.patch("lib.sheets.read_all", side_effect=lambda cfg, tab: calls.append(tab) or [["r"]]):
            screens._sheet_rows({}, "Stays", now=1000.0)
            screens._sheet_rows({}, "Stays", now=1100.0)
            screens._sheet_rows({}, "Stays", now=1000.0 + screens.CACHE_S + 1)
        self.assertEqual(len(calls), 4)                                    # one cached, one expired
        screens._cache.clear()


class Compose(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load()

    def test_ok(self):
        for job, args, want in [("basket", "weekly", "/basket weekly"), ("scan", "", "/scan"),
                                ("digest", "ignored", "/digest"), ("market", "", "/watch check"),
                                ("price", "olive oil", "/price olive oil"),
                                ("price", "--xx", "/price xx"),
                                ("flights", "BUD 01-30.11 7", "/flights BUD 01-30.11 7"),
                                ("stays", "LCA 04-11.11 sea", "/stays LCA 04-11.11 sea"),
                                ("china", "GaN charger 65W", "/china GaN charger 65W"),
                                ("china", "only 1688 socks", "/china only 1688 socks")]:
            self.assertEqual(actions.compose(job, args, self.cfg), (want, None), (job, args))

    def test_rejected_with_a_human_sentence(self):
        for job, args in [("basket", "yearly"), ("basket", ""), ("price", ""), ("price", "!!"),
                          ("price", "a" * 41), ("flights", "BUD"), ("flights", ""),
                          ("stays", "xx"), ("china", "ab"), ("china", "only foo socks"),
                          ("china", ""), ("cancel", ""), ("", ""), ("rm -rf", "")]:
            text, err = actions.compose(job, args, self.cfg)
            self.assertIsNone(text, (job, args))
            self.assertTrue(err and "<" not in err, (job, args))

    def test_whitespace_collapsed_and_never_multiline(self):
        text, _ = actions.compose("price", "olive\n  oil", self.cfg)
        self.assertEqual(text, "/price olive oil")

    def test_run_queues_for_the_listener(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        inbox.heartbeat(root)                    # the listener's inbox thread is alive (decision 102)
        ok, msg = actions.run(root, self.cfg, 111, "basket", "weekly")
        self.assertTrue(ok)
        self.assertIn("arrives in your chat", msg)
        self.assertEqual(inbox.take(root, ["111"]), [("111", "/basket weekly")])
        ok, msg = actions.run(root, self.cfg, 111, "flights", "BUD")
        self.assertFalse(ok)
        self.assertEqual([n for n in os.listdir(inbox.inbox_dir(root)) if n.endswith(".json")], [])


class MarketActions(unittest.TestCase):
    """Real market code on a temp data dir: no Sheet, no Telegram."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.cfg = config.load()
        os.environ.setdefault("TELEGRAM_CHAT_ID", "111")

    LINK = "https://www.amazon.com/dp/B000TEST01"

    def test_add_then_bought_then_gone(self):
        ok, msg = actions.market_add(self.cfg, self.root, "111", "Test cable", self.LINK, "0.2 kg")
        self.assertTrue(ok, msg)
        self.assertIn("Added", msg)
        v = screens.market_view(self.root)
        self.assertEqual([i["name"] for i in v["items"]], ["Test cable"])
        self.assertFalse(v["items"][0]["weight_needed"])
        item_id = v["items"][0]["id"]
        ok, msg = actions.market_action(self.cfg, self.root, "111", "bought", item_id)
        self.assertTrue(ok, msg)
        self.assertEqual(screens.market_view(self.root)["items"], [])
        ok, msg = actions.market_action(self.cfg, self.root, "111", "remove", item_id)
        self.assertFalse(ok)
        self.assertIn("no longer", msg)

    def test_add_rejections(self):
        c = (self.cfg, self.root, "111")
        for name, link, weight, want in [
                ("x", self.LINK, "", "2 to 80"),
                ("Cable", "no link here", "", "https://"),
                ("Cable", "https://unknown-store.example/item", "", "don't watch that store"),
                ("Cable", self.LINK + " https://www.amazon.com/dp/B000TEST02", "", "One link per store"),
                ("Cable", self.LINK, "heavy", "")]:
            ok, msg = actions.market_add(*c, name, link, weight)
            self.assertFalse(ok, (name, link, weight))
            self.assertIn(want, msg)
            self.assertNotIn("<", msg)
        self.assertEqual(screens.market_view(self.root)["items"], [])

    def test_action_validates(self):
        for action, i in [("delete", "1"), ("bought", "../x"), ("bought", ""), ("bought", "a" * 21)]:
            self.assertEqual(actions.market_action(self.cfg, self.root, "111", action, i),
                             (False, "Bad request."))

    def test_busy_list_is_a_sentence_not_a_crash(self):
        from market import state

        def busy(root):
            raise state.Busy("The watch list is busy (another change is saving) — try again in a minute.")
        with mock.patch.object(state, "write_lock", busy):
            ok, msg = actions.market_action(self.cfg, self.root, "111", "bought", "1")
        self.assertFalse(ok)
        self.assertIn("busy", msg)


class FakeSvc:
    """What the endpoints call; records requests."""

    def __init__(self):
        self.calls = []
        self.run_ok = (True, "Sent to the bot.")

    def plan_page(self, chat_id, name):
        self.calls.append(("plan", chat_id, name))
        return {"title": f"{name} page", "blocks": []} if name != "week" else None

    def market_view(self):
        return {"items": [], "stores": ["Amazon US"], "note": "n"}

    def basket_view(self, kind):
        return {"empty": True, "kind": kind} if kind in ("weekly", "monthly") else None

    def travel_view(self):
        return {"scan": None, "trips": [], "stays": [], "run_date": None, "unavailable": True}

    def china_status(self, chat_id):
        return {"running": False, "waiting": 0}

    def run(self, chat_id, job, args):
        self.calls.append(("run", chat_id, job, args))
        return self.run_ok

    def market_action(self, chat_id, action, item_id):
        self.calls.append(("maction", chat_id, action, item_id))
        return True, "✅ done"

    def market_add(self, chat_id, name, link, weight):
        self.calls.append(("madd", chat_id, name, link, weight))
        return True, "Added"


class Endpoints(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.svc = FakeSvc()
        cls.app._svc = cls.svc

    def setUp(self):
        self.svc.calls.clear()
        self.svc.run_ok = (True, "Sent to the bot.")
        self.app.run_limiter.hits.clear()

    def post(self, path, obj=None, uid=OWNER, raw=None, ctype="application/json"):
        body = raw if raw is not None else json.dumps(obj).encode()
        return self.req(path, "tma " + init_data(uid), "POST", body,
                        {"Content-Type": ctype} if ctype else {})

    def test_gets(self):
        for path, key in [("/api/plan/today", "title"), ("/api/market", "items"),
                          ("/api/basket/weekly", "empty"), ("/api/basket/monthly", "empty"),
                          ("/api/travel", "unavailable"), ("/api/china/status", "running")]:
            st, h, body = self.api(path)
            self.assertEqual(st, 200, path)
            self.assertIn(key, json.loads(body), path)
            self.assertEqual(h["Cache-Control"], "no-store")

    def test_plan_is_for_the_asking_person_and_unreadable_is_flagged(self):
        self.api("/api/plan/today", ADULT)
        self.assertEqual(self.svc.calls[-1], ("plan", str(ADULT), "today"))
        self.assertEqual(json.loads(self.api("/api/plan/week")[2]), {"unreadable": True})
        self.assertEqual(self.api("/api/plan/yesterday")[0], 404)

    def test_basket_kind_validated_by_route(self):
        self.assertEqual(self.api("/api/basket/yearly")[0], 404)

    def test_every_new_route_needs_a_known_signed_user_with_permission(self):
        routes = ["/api/plan/today", "/api/market", "/api/basket/weekly", "/api/travel",
                  "/api/china/status"]
        for path in routes:
            self.assertEqual(self.req(path)[0], 401, path)
            st, _, body = self.api(path, STRANGER)
            self.assertEqual((st, json.loads(body)), (403, {"error": "private"}), path)
        self.app.people[OWNER] = people.Person(OWNER, "Davit", "viewer")
        try:
            for path in routes:
                self.assertEqual(self.api(path)[0], 403, path)
            self.assertEqual(self.post("/api/run", {"job": "scan"})[0], 403)
            self.assertEqual(self.post("/api/market/add", {"name": "xx", "link": "https://a.b"})[0], 403)
        finally:
            self.app.people[OWNER] = people.Person(OWNER, "Davit", "owner")
        self.assertFalse([c for c in self.svc.calls if c[0] in ("run", "madd", "maction")])

    def test_run(self):
        st, _, body = self.post("/api/run", {"job": "basket", "args": "weekly"})
        self.assertEqual((st, json.loads(body)), (200, {"ok": True, "message": "Sent to the bot."}))
        self.assertEqual(self.svc.calls[-1], ("run", str(OWNER), "basket", "weekly"))
        self.post("/api/run", {"job": "scan"}, uid=ADULT)
        self.assertEqual(self.svc.calls[-1], ("run", str(ADULT), "scan", ""))

    def test_run_refusal_is_not_ok(self):
        self.svc.run_ok = (False, "I couldn't read the dates.")
        d = json.loads(self.post("/api/run", {"job": "flights", "args": "BUD"})[2])
        self.assertEqual(d, {"ok": False, "message": "I couldn't read the dates."})

    def test_run_bad_input(self):
        for obj in [{"job": "cancel"}, {"job": "scan", "x": "1"}, {"args": "x"}, {"job": 5},
                    {"job": "scan", "args": 5}, {"job": "price", "args": "a" * 301}, ["scan"]]:
            self.assertEqual(self.post("/api/run", obj)[0], 400, obj)
        self.assertEqual(self.post("/api/run", raw=b"{nope")[0], 400)
        self.assertEqual(self.post("/api/run", {"job": "scan"}, ctype="text/plain")[0], 415)
        self.assertEqual(self.svc.calls, [])

    def test_run_has_its_own_stricter_limit_per_user(self):
        sts = [self.post("/api/run", {"job": "scan"})[0] for _ in range(11)]
        self.assertEqual(sts, [200] * 10 + [429])
        self.assertEqual(self.post("/api/run", {"job": "scan"}, uid=ADULT)[0], 200)

    def test_market_edit_calls(self):
        st, _, body = self.post("/api/market/action", {"action": "bought", "id": "7"})
        self.assertEqual((st, json.loads(body)["ok"]), (200, True))
        self.assertEqual(self.svc.calls[-1], ("maction", str(OWNER), "bought", "7"))
        st, _, _ = self.post("/api/market/add", {"name": "Cable", "link": "https://a.b/x", "weight": "0.2 kg"})
        self.assertEqual(st, 200)
        self.assertEqual(self.svc.calls[-1], ("madd", str(OWNER), "Cable", "https://a.b/x", "0.2 kg"))
        self.post("/api/market/add", {"name": "Cable", "link": "https://a.b/x"})
        self.assertEqual(self.svc.calls[-1][-1], "")

    def test_market_edit_bad_input(self):
        for path, obj in [("/api/market/action", {"action": "delete", "id": "7"}),
                          ("/api/market/action", {"action": "bought", "id": "../7"}),
                          ("/api/market/action", {"action": "bought"}),
                          ("/api/market/add", {"name": "x"}),
                          ("/api/market/add", {"name": "x", "link": "y", "extra": "z"}),
                          ("/api/market/add", {"name": 1, "link": "y"})]:
            self.assertEqual(self.post(path, obj)[0], 400, (path, obj))
        self.assertEqual(self.svc.calls, [])

    def test_wrong_method(self):
        self.assertEqual(self.api("/api/run")[0], 405)
        self.assertEqual(self.post("/api/market", {})[0], 405)


if __name__ == "__main__":
    unittest.main()
