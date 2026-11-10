"""Mini App step 1 — China results screen (docs/briefs/MINI_APP.md §12).

miniapp.china_view on a real saved /china result (tests/fixtures/miniapp/china_last.json,
captured 2026-11-09, product data only, the large rich/plain copies removed). That result was
saved before the trust score (decision 092), so `current()` runs the real
china/pricing.apply_trust over it to get today's shape. The endpoints run over real HTTP with
the fake China loader/action from test_miniapp_server.Base."""
import json
import os
import unittest
import unittest.mock

from china import pricing, report, search
from miniapp import china_view, people
from tests.test_china_report import RATES
from tests.test_miniapp_server import ADULT, OWNER, STRANGER, Base, init_data

F = os.path.join(os.path.dirname(__file__), "fixtures", "miniapp")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fixture():
    with open(os.path.join(F, "china_last.json"), encoding="utf-8") as f:
        return json.load(f)


def current():
    """The fixture as the pipeline saves it today: trust applied by the real code."""
    last = fixture()
    allp = [p for s in last["sites"] for p in s.get("ranked") or []]
    pricing.apply_trust(allp, last.get("category") or "other",
                        search.load_cfg(ROOT).get("brands"))
    return last


class View(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(china_view.view(None), {"empty": True})
        self.assertEqual(china_view.view({"sites": []}), {"empty": True})

    def test_shape_and_numbering_match_the_chat(self):
        last = fixture()
        v = china_view.view(last)
        self.assertEqual(v["job"], "0323fe44")
        self.assertEqual([r["n"] for r in v["results"]], list(range(1, 11)))
        chat_order = [p["title_en"] for _, p in report.numbered(last["sites"])]
        self.assertEqual([r["title"] for r in v["results"]],
                         [report.short(t, 120) for t in chat_order])
        self.assertEqual([s["status"] for s in v["sites"]], ["ok", "link", "ok"])
        self.assertIn("not read automatically", v["sites"][1]["line"])
        self.assertEqual(v["sites"][0]["line"], "5 results")

    def test_numbers_are_the_report_helpers(self):
        last = fixture()
        p = last["sites"][0]["ranked"][0]
        c = china_view.view(last)["results"][0]
        self.assertEqual(c["price"], "¥69.10 → 3,733 AMD · $10.36")
        self.assertEqual(c["price"], china_view.plain(report.price_line(p))[0])
        self.assertTrue(c["total"].startswith(report.amd(p["total_amd"]) + " AMD"))
        self.assertEqual(len(c["routes"]), len(p["quote"]["lines"]))

    def test_no_html_left(self):
        def strings(x):
            if isinstance(x, str):
                yield x
            elif isinstance(x, dict):
                for v in x.values():
                    yield from strings(v)
            elif isinstance(x, list):
                for v in x:
                    yield from strings(v)
        for s in strings(china_view.view(current())):
            self.assertNotRegex(s, r"<(b|i|br|a|code)\b|&amp;|&lt;", s)

    def test_warnings_once(self):
        c = china_view.view(fixture())["results"][0]
        self.assertTrue(any("cheaper variant" in n for n in c["notes"]))
        self.assertNotIn(report.NO_WEIGHT, c["notes"])          # it lives in weight only
        self.assertIn(report.NO_WEIGHT, c["weight"])

    def test_old_result_has_no_pick(self):
        v = china_view.view(fixture())          # saved before the trust score
        self.assertIsNone(v["pick"])
        self.assertFalse(any(r["pick"] for r in v["results"]))

    def test_current_result_pick_matches_pricing(self):
        last = current()
        v = china_view.view(last)
        numbered = report.numbered(last["sites"])
        best, why = pricing.best_pick([p for _, p in numbered])
        n = next(n for n, p in numbered if p is best)
        self.assertEqual((v["pick"], v["pick_reason"]), (n, why))
        self.assertEqual([r["n"] for r in v["results"] if r["pick"]], [n])
        c = v["results"][n - 1]
        self.assertTrue(c["trust_line"].startswith("🛡 Trust "))
        self.assertIsInstance(c["trust"], (int, float))

    def test_links_only_https(self):
        last = fixture()
        last["sites"][0]["ranked"][0]["link"] = "javascript:alert(1)"
        c = china_view.view(last)["results"][0]
        self.assertIsNone(c["link"])
        self.assertFalse(c["can_watch"])

    def test_reviews_read(self):
        last = fixture()
        p = last["sites"][0]["ranked"][0]
        p.update(reviews_read=True, reviews=1234, liked=["fast"], complaints=["hot"])
        c = china_view.view(last)["results"][0]
        self.assertEqual(c["reviews"], {"read": True, "count": "1,234", "liked": ["fast"],
                                        "complaints": ["hot"]})
        self.assertFalse(c["can_reviews"])

    def test_plain(self):
        self.assertEqual(china_view.plain("a<br>b &amp; <b>c</b><br/>"), ["a", "b & c"])


class Permission(unittest.TestCase):
    def test_can(self):
        self.assertTrue(people.can(people.Person(1, "D", "owner"), "china"))
        self.assertTrue(people.can(people.Person(2, "K", "adult"), "china"))
        self.assertFalse(people.can(people.Person(3, "V", "viewer"), "china"))
        self.assertFalse(people.can(None, "china"))
        self.assertFalse(people.can(people.Person(1, "D", "owner"), "unknown-module"))


class Endpoints(Base):
    def setUp(self):
        self.saved.clear()
        self.actions.clear()
        type(self).reply = "👁 Added to 🌍 Market watch: <b>X</b> at ¥9."

    def post(self, obj=None, uid=OWNER, raw_body=None, ctype="application/json", header=None):
        body = raw_body if raw_body is not None else json.dumps(obj).encode()
        return self.req("/api/china/action", header or "tma " + init_data(uid), "POST", body,
                        {"Content-Type": ctype} if ctype else {})

    # ---- GET /api/china
    def test_empty(self):
        st, h, body = self.api("/api/china")
        self.assertEqual((st, json.loads(body)), (200, {"empty": True}))
        self.assertEqual(h["Cache-Control"], "no-store")

    def test_own_chat_only(self):
        self.saved[str(OWNER)] = fixture()
        self.assertEqual(json.loads(self.api("/api/china")[2])["job"], "0323fe44")
        self.assertEqual(json.loads(self.api("/api/china", ADULT)[2]), {"empty": True})

    def test_needs_auth_and_known_user(self):
        self.saved[str(STRANGER)] = fixture()
        self.assertEqual(self.req("/api/china")[0], 401)
        st, _, body = self.api("/api/china", STRANGER)
        self.assertEqual((st, json.loads(body)), (403, {"error": "private"}))

    def test_role_without_permission(self):
        self.app.people[OWNER] = people.Person(OWNER, "Davit", "viewer")
        try:
            st, _, body = self.api("/api/china")
            self.assertEqual((st, json.loads(body)), (403, {"error": "not allowed"}))
            self.assertEqual(self.post({"action": "watch", "job": "0323fe44", "n": 1})[0], 403)
            self.assertEqual(self.actions, [])
        finally:
            self.app.people[OWNER] = people.Person(OWNER, "Davit", "owner")

    # ---- POST /api/china/action
    def test_watch_goes_through_the_chat_button_path(self):
        st, _, body = self.post({"action": "watch", "job": "0323fe44", "n": 3})
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(body), {"ok": True,
                                            "message": "👁 Added to 🌍 Market watch: X at ¥9."})
        self.assertEqual(self.actions, [(str(OWNER), "watch", "0323fe44", 3)])

    def test_reviews_maps_to_rev(self):
        type(self).reply = "⏳ Reading the reviews of 2. Charger… (~2 min)"
        st, _, body = self.post({"action": "reviews", "job": "0323fe44", "n": 2}, uid=ADULT)
        self.assertEqual((st, json.loads(body)["ok"]), (200, True))
        self.assertEqual(self.actions, [(str(ADULT), "rev", "0323fe44", 2)])

    def test_refusal_is_not_ok(self):
        type(self).reply = "That result is gone (older than 24 h) or has no price — run /china again."
        d = json.loads(self.post({"action": "watch", "job": "0323fe44", "n": 3})[2])
        self.assertFalse(d["ok"])
        self.assertIn("older than 24 h", d["message"])

    def test_bad_inputs(self):
        cases = [{"action": "delete", "job": "0323fe44", "n": 1},
                 {"action": "watch", "job": "../x", "n": 1},
                 {"action": "watch", "job": "0323FE44", "n": 1},
                 {"action": "watch", "job": "0323fe44", "n": 0},
                 {"action": "watch", "job": "0323fe44", "n": 100},
                 {"action": "watch", "job": "0323fe44", "n": "1"},
                 {"action": "watch", "job": "0323fe44", "n": True},
                 {"action": "watch", "job": "0323fe44"},
                 {"action": "watch", "job": "0323fe44", "n": 1, "chat_id": "1"},
                 [1, 2]]
        for c in cases:
            self.assertEqual(self.post(c)[0], 400, c)
        self.assertEqual(self.post(raw_body=b"{not json")[0], 400)
        self.assertEqual(self.post(raw_body=b"\xff\xfe")[0], 400)
        self.assertEqual(self.actions, [])

    def test_content_type(self):
        st = self.post({"action": "watch", "job": "0323fe44", "n": 1}, ctype="text/plain")[0]
        self.assertEqual(st, 415)
        st = self.post({"action": "watch", "job": "0323fe44", "n": 1},
                       ctype="application/json; charset=utf-8")[0]
        self.assertEqual(st, 200)

    def test_body_too_large(self):
        st, _, body = self.post(raw_body=b"{" + b" " * 2000 + b"}")
        self.assertEqual((st, json.loads(body)), (413, {"error": "body too large"}))
        self.assertEqual(self.actions, [])

    def test_post_needs_auth(self):
        st = self.post({"action": "watch", "job": "0323fe44", "n": 1}, header="Bearer x")[0]
        self.assertEqual(st, 401)
        self.assertEqual(self.post({"action": "watch", "job": "0323fe44", "n": 1},
                                   uid=STRANGER)[0], 403)
        self.assertEqual(self.actions, [])

    def test_connection_reusable_after_post(self):
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        hdr = {"Authorization": "tma " + init_data(OWNER), "Content-Type": "application/json"}
        c.request("POST", "/api/china/action",
                  json.dumps({"action": "watch", "job": "0323fe44", "n": 1}), hdr)
        self.assertEqual(c.getresponse().read() and 200, 200)
        c.request("GET", "/api/me", headers={"Authorization": hdr["Authorization"]})
        r = c.getresponse()
        self.assertEqual((r.status, json.loads(r.read())["role"]), (200, "owner"))
        c.close()


class AppButton(unittest.TestCase):
    """china/report: the 📱 row on every /china answer (rich and plain)."""
    URL = "https://app.example.ts.net/?screen=china"

    def test_rich_button_matches_the_captured_syntax(self):
        with open(os.path.join(F, "rich_web_app_button.json"), encoding="utf-8") as f:
            cap = json.load(f)
        got = report.rich_button("📱 Open in app", {"web_app": "https://<app>/?screen=china"})
        self.assertEqual(got, cap["sent_html_button"].replace("<app>", "&lt;app&gt;"))
        self.assertEqual(report.rich_button("💬 Reviews 1", "cn:rev:0323fe44:1"),
                         '<tg-button type="callback_data" data="cn:rev:0323fe44:1">'
                         '💬 Reviews 1</tg-button>')

    def test_rows(self):
        shown = report.numbered(fixture()["sites"])
        with_app = report.buttons("0323fe44", ["pinduoduo", "1688"], shown, self.URL)
        without = report.buttons("0323fe44", ["pinduoduo", "1688"], shown)
        self.assertEqual(with_app[0], [(report.APP_LABEL, {"web_app": self.URL})])
        self.assertEqual(with_app[1:], without)                  # nothing else changes

    def test_build_rich_and_plain(self):
        last = fixture()
        rich, _plain, btns = report.build("0323fe44", "charger", last["sites"], None, "", [],
                                          RATES, "2026-11-09", "other",
                                          app_url=self.URL)
        self.assertIn(f'<tg-button type="web_app" url="{self.URL}">📱 Open in app</tg-button>',
                      rich)
        self.assertEqual(btns[0], [(report.APP_LABEL, {"web_app": self.URL})])
        from lib import telegram
        markup = json.loads(telegram.reply_markup(buttons=btns))
        self.assertEqual(markup["inline_keyboard"][0],
                         [{"text": report.APP_LABEL, "web_app": {"url": self.URL}}])

    def test_no_app_no_button(self):
        with unittest.mock.patch("miniapp.public_url", return_value=""):
            self.assertIsNone(search.app_url())
        with unittest.mock.patch("miniapp.public_url", return_value="https://x.ts.net/"):
            self.assertEqual(search.app_url(), "https://x.ts.net/?screen=china")


class ViewFixtureIsClean(unittest.TestCase):
    def test_no_chat_ids_or_html_copies(self):
        d = fixture()
        self.assertFalse({"rich", "plain", "usage"} & set(d))
        self.assertNotIn("chat", json.dumps(d))


if __name__ == "__main__":
    unittest.main()
