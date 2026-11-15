"""Mini App Stage B, Basket (decision 108): the shared tick list, the same state as /list.

The list itself is shopping/checklist.py (decision 106); these tests cover the app's view of it
(names instead of Telegram ids, local times, https links only), the endpoints (signature, per-module
permission, validation) and the real checklist on a temp household with the Telegram and Sheet
side effects replaced by recorders."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from miniapp import server, shopping_view
from shopping import checklist
from tests.test_miniapp_server import ADULT, OWNER, STRANGER, Base, init_data

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAMES = {OWNER: "Davit", ADULT: "Karine"}


def temp_root(with_last_run=True):
    root = tempfile.mkdtemp()
    os.makedirs(os.path.join(root, "plan", "meals"))
    shutil.copy(os.path.join(ROOT, "plan", "meals", "basket.md"), os.path.join(root, "plan", "meals"))
    if with_last_run:
        os.makedirs(os.path.join(root, ".browser"))
        shutil.copy(os.path.join(ROOT, "tests", "fixtures", "miniapp", "basket_weekly.json"),
                    os.path.join(root, ".browser"))
    return root


class Shape(unittest.TestCase):
    def setUp(self):
        self.root = temp_root()
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_view_of_the_real_list(self):
        v = shopping_view.view(self.root, "weekly", NAMES)
        self.assertEqual(v["kind"], "weekly")
        self.assertTrue(v["period_label"])
        self.assertEqual(v["total"], sum(len(g["items"]) for g in v["groups"]))
        self.assertEqual(v["done"], 0)
        self.assertTrue(all(g["aisle"] and g["items"] for g in v["groups"]))
        keys = [i["key"] for g in v["groups"] for i in g["items"]]
        self.assertEqual(len(keys), len(set(keys)))
        priced = [i for g in v["groups"] for i in g["items"] if i["shop_name"]]
        self.assertTrue(priced)                                  # the last basket run is shown per item

    def test_ticks_show_names_and_local_time_never_ids(self):
        key = shopping_view.view(self.root, "weekly", NAMES)["groups"][0]["items"][0]["key"]
        checklist.tick(self.root, "weekly", key, OWNER)
        v = shopping_view.view(self.root, "weekly", NAMES)
        item = next(i for g in v["groups"] for i in g["items"] if i["key"] == key)
        self.assertTrue(item["done"])
        self.assertEqual(item["by_name"], "Davit")
        self.assertRegex(item["at"], r"^\d\d \w{3} \d\d:\d\d$")
        self.assertEqual(v["last"]["by_name"], "Davit")
        self.assertEqual(v["done"], 1)
        self.assertNotIn(str(OWNER), json.dumps(v))

    def test_unknown_person_is_someone_not_an_id(self):
        key = shopping_view.view(self.root, "weekly", NAMES)["groups"][0]["items"][0]["key"]
        checklist.tick(self.root, "weekly", key, 555444333)
        v = shopping_view.view(self.root, "weekly", NAMES)
        self.assertEqual(v["last"]["by_name"], "someone")
        self.assertNotIn("555444333", json.dumps(v))

    def test_reset_is_attributed(self):
        checklist.reset(self.root, "weekly", ADULT)
        v = shopping_view.view(self.root, "weekly", NAMES)
        self.assertEqual(v["reset"]["by_name"], "Karine")

    def test_links_are_https_only_and_internal_fields_are_dropped(self):
        raw = {"kind": "weekly", "period_label": "Week 46", "version": "x", "done": 0, "total": 1,
               "last": None, "reset": None,
               "groups": [{"aisle": "Dairy", "items": [{
                   "key": "eggs", "item": "Eggs", "aisle": "Dairy", "amount": "6", "shop": "yc",
                   "shop_name": "Yerevan City", "buy": "1 pack", "product": "Eggs", "url": "javascript:alert(1)",
                   "app_url": "yc://x", "reason": "↳ fresh", "done": False, "by": None, "at_utc": None}]}],
               "items": []}
        with mock.patch.object(checklist, "load", return_value=raw):
            v = shopping_view.view(self.root, "weekly", NAMES)
        item = v["groups"][0]["items"][0]
        self.assertIsNone(item["url"])
        self.assertNotIn("app_url", item)
        self.assertEqual(item["reason"], "↳ fresh")

    def test_unknown_kind_and_malformed_list(self):
        self.assertIsNone(shopping_view.view(self.root, "yearly", NAMES))
        with mock.patch.object(checklist, "load", side_effect=ValueError("basket.md: bad row")):
            v = shopping_view.view(self.root, "weekly", NAMES)
        self.assertEqual(v, {"unavailable": True, "message": "basket.md: bad row"})


class Fake:
    """Services stand-in for the endpoint tests."""

    def __init__(self):
        self.calls = []
        self.ok = True

    def list_view(self, kind, names):
        return {"kind": kind, "groups": [], "total": 0, "done": 0} if kind in ("weekly", "monthly") else None

    def list_tick(self, user_id, kind, key, done, names):
        self.calls.append(("tick", user_id, kind, key, done))
        return self.ok, "" if self.ok else "That item is no longer on the list — refresh it.", \
            {"kind": kind, "groups": [], "total": 0, "done": 1}

    def list_reset(self, user_id, kind, names):
        self.calls.append(("reset", user_id, kind))
        return True, "", {"kind": kind, "groups": [], "total": 0, "done": 0}


class Endpoints(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fake = Fake()
        cls.app._svc = cls.fake

    def setUp(self):
        self.fake.calls.clear()
        self.fake.ok = True

    def post(self, path, obj, uid=OWNER, ctype="application/json"):
        return self.req(path, "tma " + init_data(uid), "POST", json.dumps(obj).encode(),
                        {"Content-Type": ctype})

    def test_get(self):
        for kind in ("weekly", "monthly"):
            st, h, body = self.api(f"/api/list/{kind}")
            self.assertEqual((st, json.loads(body)["kind"]), (200, kind))
            self.assertEqual(h["Cache-Control"], "no-store")
        self.assertEqual(self.api("/api/list/yearly")[0], 404)

    def test_tick_uses_the_signed_person_and_maps_done(self):
        for body, want in [({"kind": "weekly", "key": "eggs"}, None),
                           ({"kind": "weekly", "key": "eggs", "done": "toggle"}, None),
                           ({"kind": "monthly", "key": "olive-oil", "done": "1"}, True),
                           ({"kind": "weekly", "key": "eggs", "done": "0"}, False)]:
            st, _, out = self.post("/api/list/tick", body)
            self.assertEqual((st, json.loads(out)["ok"]), (200, True), body)
            self.assertEqual(self.fake.calls[-1], ("tick", OWNER, body["kind"], body["key"], want))
        self.post("/api/list/tick", {"kind": "weekly", "key": "eggs"}, uid=ADULT)
        self.assertEqual(self.fake.calls[-1][1], ADULT)

    def test_a_refused_tick_is_not_ok_and_says_why(self):
        self.fake.ok = False
        d = json.loads(self.post("/api/list/tick", {"kind": "weekly", "key": "gone"})[2])
        self.assertFalse(d["ok"])
        self.assertIn("no longer on the list", d["message"])

    def test_reset(self):
        st, _, out = self.post("/api/list/reset", {"kind": "weekly"}, uid=ADULT)
        self.assertEqual((st, json.loads(out)["ok"]), (200, True))
        self.assertEqual(self.fake.calls[-1], ("reset", ADULT, "weekly"))

    def test_bad_input_never_reaches_the_list(self):
        for path, obj in [("/api/list/tick", {"kind": "yearly", "key": "eggs"}),
                          ("/api/list/tick", {"kind": "weekly", "key": "../x"}),
                          ("/api/list/tick", {"kind": "weekly", "key": "A" * 41}),
                          ("/api/list/tick", {"kind": "weekly"}),
                          ("/api/list/tick", {"kind": "weekly", "key": "eggs", "done": "maybe"}),
                          ("/api/list/tick", {"kind": "weekly", "key": "eggs", "by": "1"}),
                          ("/api/list/reset", {"kind": "yearly"}),
                          ("/api/list/reset", {})]:
            self.assertEqual(self.post(path, obj)[0], 400, (path, obj))
        self.assertEqual(self.post("/api/list/tick", {"kind": "weekly", "key": "eggs"},
                                   ctype="text/plain")[0], 415)
        self.assertEqual(self.fake.calls, [])

    def test_signature_and_permission_on_every_route(self):
        self.assertEqual(self.req("/api/list/weekly")[0], 401)
        self.assertEqual(self.api("/api/list/weekly", STRANGER)[0], 403)
        self.assertEqual(self.post("/api/list/tick", {"kind": "weekly", "key": "eggs"}, uid=STRANGER)[0], 403)
        self.app.people[OWNER] = server.people.Person(OWNER, "Davit", "viewer")
        try:
            self.assertEqual(self.api("/api/list/weekly")[0], 403)
            self.assertEqual(self.post("/api/list/tick", {"kind": "weekly", "key": "eggs"})[0], 403)
            self.assertEqual(self.post("/api/list/reset", {"kind": "weekly"})[0], 403)
        finally:
            self.app.people[OWNER] = server.people.Person(OWNER, "Davit", "owner")
        self.assertEqual(self.fake.calls, [])

    def test_wrong_method(self):
        self.assertEqual(self.api("/api/list/tick")[0], 405)
        self.assertEqual(self.post("/api/list/weekly", {})[0], 405)


class RealServices(unittest.TestCase):
    """Services on a temp household: the checklist is real; Telegram and the Sheet are recorders."""

    def setUp(self):
        self.root = temp_root()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.svc = server.Services()
        self.svc.root = self.root
        self.svc._bg = lambda fn, *a: fn(*a)                     # run the follow-up work inline
        self.refresh = mock.patch("shopping.bot.refresh_messages").start()
        self.mirror = mock.patch("shopping.bot.mirror_to_sheet").start()
        self.addCleanup(mock.patch.stopall)
        self.key = shopping_view.view(self.root, "weekly", NAMES)["groups"][0]["items"][0]["key"]

    def test_tick_is_shared_state_and_updates_the_chats_and_the_sheet(self):
        ok, msg, view = self.svc.list_tick(OWNER, "weekly", self.key, None, NAMES)
        self.assertTrue(ok, msg)
        self.assertEqual(view["done"], 1)
        self.assertEqual(checklist.load(self.root, "weekly")["done"], 1)           # what /list shows
        self.refresh.assert_called_once()
        self.assertEqual(self.refresh.call_args.args[2], "weekly")
        (changes,) = [c.args[3] for c in self.mirror.call_args_list]
        self.assertEqual(list(changes.values()), [True])

    def test_untick_and_toggle(self):
        self.svc.list_tick(OWNER, "weekly", self.key, True, NAMES)
        self.svc.list_tick(ADULT, "weekly", self.key, None, NAMES)                 # toggles off
        self.assertEqual(checklist.load(self.root, "weekly")["done"], 0)

    def test_an_item_that_left_the_list_is_a_sentence(self):
        ok, msg, view = self.svc.list_tick(OWNER, "weekly", "no-such-item", None, NAMES)
        self.assertFalse(ok)
        self.assertIn("no longer on the list", msg)
        self.assertIsNone(view)
        self.refresh.assert_not_called()

    def test_busy_list_is_a_sentence(self):
        with mock.patch.object(checklist, "tick", side_effect=checklist.Busy("The list is busy — try again")):
            ok, msg, _ = self.svc.list_tick(OWNER, "weekly", self.key, None, NAMES)
        self.assertFalse(ok)
        self.assertIn("busy", msg)

    def test_reset_clears_and_mirrors_every_box(self):
        self.svc.list_tick(OWNER, "weekly", self.key, True, NAMES)
        ok, _, view = self.svc.list_reset(ADULT, "weekly", NAMES)
        self.assertTrue(ok)
        self.assertEqual(view["done"], 0)
        self.assertEqual(view["reset"]["by_name"], "Karine")
        changes = self.mirror.call_args_list[-1].args[3]
        self.assertTrue(changes and not any(changes.values()))

    def test_a_telegram_failure_does_not_undo_the_tick(self):
        self.refresh.side_effect = OSError("telegram down")
        ok, _, _ = self.svc.list_tick(OWNER, "weekly", self.key, True, NAMES)
        self.assertTrue(ok)
        self.assertEqual(checklist.load(self.root, "weekly")["done"], 1)


if __name__ == "__main__":
    unittest.main()
