"""miniapp.server over real HTTP on 127.0.0.1 (docs/briefs/MINI_APP.md §6, §8): auth on /api,
path traversal, security headers, 403 for unknown users, 429, GET only, nothing secret in
the log. Plus miniapp.setup_bot with a fake Bot API. Raw paths go out via http.client,
which sends them exactly as written."""
import http.client
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from typing import ClassVar
from unittest import mock

from miniapp import auth, people, server, setup_bot

TOKEN = "123456:TEST-token-not-real"
OWNER, ADULT, STRANGER = 111222333, 444555666, 777888999
CFG = {"port": 0, "max_age_hours": 24, "rate_limit_per_min": 60,
       "people": [{"env": "A", "name": "Davit", "role": "owner"},
                  {"env": "B", "name": "Karine", "role": "adult"}],
       "menu_button_text": "🏠 Family",
       "tabs": ["Today", "China", "Market", "Basket", "Travel"]}
PERSONS = people.load(CFG, {"A": str(OWNER), "B": str(ADULT)})
SECRET = "do-not-serve-this-file"


def init_data(uid, auth_date=None):
    return auth.sign({"query_id": "AAHtest", "auth_date": str(auth_date or int(time.time())),
                      "user": json.dumps({"id": uid, "first_name": "T"})}, TOKEN)


class Base(unittest.TestCase):
    cfg = CFG

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.dist = os.path.join(cls.tmp, "dist")
        os.makedirs(os.path.join(cls.dist, "assets"))
        with open(os.path.join(cls.dist, "index.html"), "w", encoding="utf-8") as f:
            f.write("<!doctype html><title>Family</title>")
        with open(os.path.join(cls.dist, "assets", "app-abc123.js"), "w") as f:
            f.write("console.log(1)")
        # a file next to dist that traversal would reach
        with open(os.path.join(cls.tmp, "config.json"), "w") as f:
            f.write(SECRET)
        cls.app = server.App(cls.cfg, TOKEN, PERSONS, dist=cls.dist)
        cls.srv = server.Server(("127.0.0.1", 0), cls.app)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def req(self, path, header=None, method="GET"):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(method, path, headers={"Authorization": header} if header else {})
        r = c.getresponse()
        body = r.read()
        c.close()
        return r.status, dict(r.getheaders()), body

    def api(self, path, uid=OWNER, raw=None):
        hdr = "tma " + (raw if raw is not None else init_data(uid))
        return self.req(path, hdr)


class Api(Base):
    def test_me_owner(self):
        st, _, body = self.api("/api/me")
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(body), {"name": "Davit", "role": "owner",
                                            "tabs": CFG["tabs"]})

    def test_me_adult(self):
        st, _, body = self.api("/api/me", ADULT)
        self.assertEqual((st, json.loads(body)["role"]), (200, "adult"))

    def test_status(self):
        st, _, body = self.api("/api/status")
        d = json.loads(body)
        self.assertEqual((st, d["ok"], d["tz"]), (200, True, "Asia/Yerevan"))
        self.assertRegex(d["time_local"], r"^\d{4}-\d\d-\d\d \d\d:\d\d$")

    def test_absent_auth(self):
        st, _, body = self.req("/api/me")
        self.assertEqual((st, json.loads(body)), (401, {"error": "unauthorized"}))

    def test_invalid_auth(self):
        raw = init_data(OWNER).replace("Davit", "x")[:-4] + "0000"
        st, _, body = self.api("/api/me", raw=raw)
        self.assertEqual((st, json.loads(body)), (401, {"error": "unauthorized"}))

    def test_wrong_scheme(self):
        st, _, _ = self.req("/api/me", "Bearer " + init_data(OWNER))
        self.assertEqual(st, 401)

    def test_expired(self):
        st, _, _ = self.api("/api/me", raw=init_data(OWNER, int(time.time()) - 25 * 3600))
        self.assertEqual(st, 401)

    def test_unknown_user_403_no_data(self):
        st, _, body = self.api("/api/me", STRANGER)
        self.assertEqual(st, 403)
        self.assertEqual(json.loads(body), {"error": "private"})
        st, _, body = self.api("/api/status", STRANGER)
        self.assertEqual((st, json.loads(body)), (403, {"error": "private"}))

    def test_unknown_api_path(self):
        self.assertEqual(self.api("/api/nope")[0], 404)

    def test_unknown_api_path_needs_auth_first(self):
        self.assertEqual(self.req("/api/nope")[0], 401)


class Headers(Base):
    COMMON = ("X-Content-Type-Options", "Referrer-Policy", "Content-Security-Policy")

    def test_api_headers(self):
        _, h, _ = self.api("/api/me")
        self.assertEqual(h["Cache-Control"], "no-store")
        self.assertEqual(h["X-Content-Type-Options"], "nosniff")
        self.assertEqual(h["Referrer-Policy"], "no-referrer")
        self.assertEqual(h["Content-Type"], "application/json")
        csp = h["Content-Security-Policy"]
        self.assertIn("script-src 'self' https://telegram.org", csp)
        self.assertIn("frame-ancestors https://web.telegram.org", csp)
        self.assertIn("default-src 'self'", csp)

    def test_error_responses_carry_headers(self):
        for st, h, _ in (self.req("/api/me"), self.api("/api/me", STRANGER),
                         self.req("/nope.js")):
            for k in self.COMMON:
                self.assertIn(k, h, (st, k))
        self.assertEqual(self.req("/api/me")[1]["Cache-Control"], "no-store")

    def test_static_headers(self):
        st, h, body = self.req("/")
        self.assertEqual(st, 200)
        self.assertIn(b"<title>Family</title>", body)
        self.assertEqual(h["Content-Type"], "text/html; charset=utf-8")
        self.assertEqual(h["Cache-Control"], "no-cache")
        for k in self.COMMON:
            self.assertIn(k, h)
        st, h, _ = self.req("/assets/app-abc123.js")
        self.assertEqual(st, 200)
        self.assertIn("immutable", h["Cache-Control"])
        self.assertTrue(h["Content-Type"].startswith("text/javascript"))

    def test_server_header_has_no_version(self):
        _, h, _ = self.req("/")
        self.assertEqual(h["Server"], "miniapp")


class Traversal(Base):
    PATHS = ("/../config.json", "/%2e%2e/config.json", "/%2E%2E/config.json",
             "/..%2fconfig.json", "/..%2Fconfig.json", "/%2e%2e%2fconfig.json",
             "/..%5cconfig.json", "/..\\config.json", "/assets/../../config.json",
             "/assets/%2e%2e/%2e%2e/config.json", "/%252e%252e/config.json",
             "//../config.json", "/./../config.json", "/C:/Windows/win.ini",
             "/index.html%00.js", "/%c0%ae%c0%ae/config.json", "/assets", "/missing.js")

    def test_all_404(self):
        for p in self.PATHS:
            st, _, body = self.req(p)
            self.assertEqual(st, 404, p)
            self.assertNotIn(SECRET.encode(), body, p)

    def test_query_string_ignored(self):
        self.assertEqual(self.req("/?x=../config.json")[0], 200)


class Methods(Base):
    def test_get_only(self):
        for m in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"):
            st, h, _ = self.req("/api/me", "tma " + init_data(OWNER), method=m)
            self.assertEqual(st, 405, m)
            self.assertEqual(h["Allow"], "GET")


class RateLimit(Base):
    cfg: ClassVar[dict] = {**CFG, "rate_limit_per_min": 3}

    def test_429_after_limit_per_user(self):
        sts = [self.api("/api/me")[0] for _ in range(4)]
        self.assertEqual(sts, [200, 200, 200, 429])
        self.assertEqual(self.api("/api/me", ADULT)[0], 200)   # per user id

    def test_unknown_user_limited_too(self):
        sts = [self.api("/api/me", STRANGER)[0] for _ in range(4)]
        self.assertEqual(sts, [403, 403, 403, 429])

    def test_limiter_window(self):
        rl = server.RateLimiter(2)
        self.assertEqual([rl.allow("u", t) for t in (0, 1, 2)], [True, True, False])
        self.assertTrue(rl.allow("u", 60.5))


class Logging(Base):
    def test_no_secrets_in_log(self):
        raw = init_data(OWNER)
        h = raw.rsplit("hash=", 1)[1]
        with self.assertLogs("miniapp", level="INFO") as cm:
            self.api("/api/me", raw=raw)
            self.api("/api/me", raw=raw[:-4] + "0000")
            time.sleep(0.2)   # the access line is written after the response
        text = "\n".join(cm.output)
        for secret in (h, h[:-4], raw, TOKEN, str(OWNER), "query_id"):
            self.assertNotIn(secret, text)
        self.assertIn("…333 /api/me 200", text)
        self.assertIn("auth rejected: bad hash", text)


class Capture(unittest.TestCase):
    def test_captures_once_valid_known_only(self):
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "sub", "cap.txt")
            app = server.App(CFG, TOKEN, PERSONS, dist=tmp, capture_path=path)
            app.api("/api/me", "tma " + init_data(STRANGER))
            self.assertFalse(os.path.exists(path))
            app.api("/api/me", "tma garbage")
            self.assertFalse(os.path.exists(path))
            first = init_data(OWNER)
            app.api("/api/me", "tma " + first)
            app.api("/api/me", "tma " + init_data(ADULT))
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), first)
            self.assertIsNone(app.capture_path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Resp:
    def __init__(self, d):
        self.d = d

    def json(self):
        return self.d


class SetupBot(unittest.TestCase):
    URL = "https://pc.example.ts.net/"

    def test_menu_button_shape(self):
        self.assertEqual(setup_bot.menu_button("🏠 Family", self.URL),
                         {"type": "web_app", "text": "🏠 Family", "web_app": {"url": self.URL}})

    def test_call_never_echoes_token(self):
        import requests

        def boom(url, json=None, timeout=None):
            raise requests.ConnectionError(f"failed for {url}")
        ok, detail = setup_bot.call(TOKEN, "getMe", {}, post=boom)
        self.assertFalse(ok)
        self.assertNotIn("TEST-token", detail)
        self.assertEqual(detail, "ConnectionError")

    def test_check_all(self):
        answers = {OWNER: {"ok": True, "result": setup_bot.menu_button("🏠 Family", self.URL)},
                   ADULT: {"ok": True, "result": {"type": "commands"}}}
        calls = []

        def post(url, json=None, timeout=None):
            calls.append(url.rsplit("/", 1)[1])
            return Resp(answers[json["chat_id"]])
        with mock.patch.dict(os.environ, {"A": str(OWNER), "B": str(ADULT)}):
            res = setup_bot.check_all(CFG, TOKEN, self.URL, post=post)
        self.assertEqual([(p.name, ok, d) for p, ok, d in res],
                         [("Davit", True, "set"), ("Karine", False, "is commands")])
        self.assertEqual(calls, ["getChatMenuButton", "getChatMenuButton"])


if __name__ == "__main__":
    unittest.main()
