"""Mini App review, 2026-11-10 (decision 099): request framing and session expiry.

Raw sockets, because the point is what the server does with bytes a browser never sends but
an attacker who knows the public URL can: a body on a GET, a body that never arrives. Behind
Tailscale Funnel the proxy reuses one connection to this server for several clients, so a
request that leaves unread bytes behind is a request-smuggling primitive."""
import json
import socket
import time
import unittest
from unittest import mock

from miniapp import server
from tests.test_miniapp_server import OWNER, Base, init_data


def exchange(port, payload, wait=1.0):
    """Send raw bytes; everything the server answers until it closes or goes quiet."""
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    s.sendall(payload)
    s.settimeout(wait)
    out, closed = b"", False
    try:
        while True:
            b = s.recv(65536)
            if not b:
                closed = True
                break
            out += b
    except TimeoutError:
        pass
    s.close()
    return out, closed


def owner_get(path=b"/api/me"):
    return (b"GET " + path + b" HTTP/1.1\r\nHost: x\r\nAuthorization: tma "
            + init_data(OWNER).encode() + b"\r\n\r\n")


class GetWithBody(Base):
    """A GET that carries a body: the body used to stay in the socket and run as a second
    request on the same connection (the smuggled /api/me below answered with the owner's
    name). Now it is a 400 and the connection is closed, so nothing is left to run."""

    def smuggle(self, first_line, extra=b""):
        inner = owner_get()
        return exchange(self.port, first_line + b"Host: x\r\n" + extra + b"Content-Length: "
                        + str(len(inner)).encode() + b"\r\n\r\n" + inner)

    def test_api_get_with_body_is_400_and_closed(self):
        out, closed = self.smuggle(b"GET /api/status HTTP/1.1\r\n")
        self.assertEqual(out.count(b"HTTP/1.1 "), 1, out[:200])
        self.assertTrue(out.startswith(b"HTTP/1.1 400 "))
        self.assertNotIn(b"Davit", out)
        self.assertTrue(closed)

    def test_static_get_with_body_is_400_and_closed(self):
        out, closed = self.smuggle(b"GET / HTTP/1.1\r\n")
        self.assertEqual(out.count(b"HTTP/1.1 "), 1, out[:200])
        self.assertTrue(out.startswith(b"HTTP/1.1 400 "))
        self.assertNotIn(b"Davit", out)
        self.assertTrue(closed)

    def test_chunked_get_is_400_and_closed(self):
        out, closed = exchange(self.port, b"GET /api/status HTTP/1.1\r\nHost: x\r\n"
                               b"Transfer-Encoding: chunked\r\n\r\n" + owner_get())
        self.assertEqual(out.count(b"HTTP/1.1 "), 1, out[:200])
        self.assertTrue(out.startswith(b"HTTP/1.1 400 "))
        self.assertTrue(closed)

    def test_content_length_zero_is_fine(self):
        out, _ = exchange(self.port, b"GET /api/status HTTP/1.1\r\nHost: x\r\nContent-Length: 0\r\n"
                          b"Authorization: tma " + init_data(OWNER).encode() + b"\r\n\r\n")
        self.assertTrue(out.startswith(b"HTTP/1.1 200 "))

    def test_honest_keep_alive_still_works(self):
        out, _ = exchange(self.port, owner_get(b"/api/status") + owner_get(b"/api/me"))
        self.assertEqual(out.count(b"HTTP/1.1 200 "), 2)

    def test_log_has_the_rejection(self):
        with self.assertLogs("miniapp", level="INFO") as cm:
            self.smuggle(b"GET /api/status HTTP/1.1\r\n")
            time.sleep(0.2)
        self.assertIn("- /api/status 400", "\n".join(cm.output))


class SlowBody(Base):
    """A POST whose body never arrives: 408 and the connection closed (it was a 500, and the
    dead socket was then read again)."""

    @classmethod
    def setUpClass(cls):
        cls.patch = mock.patch.object(server.Handler, "timeout", 0.5)
        cls.patch.start()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.patch.stop()

    def post(self, sent, length):
        return exchange(self.port, b"POST /api/china/action HTTP/1.1\r\nHost: x\r\n"
                        b"Authorization: tma " + init_data(OWNER).encode() + b"\r\n"
                        b"Content-Type: application/json\r\nContent-Length: "
                        + str(length).encode() + b"\r\n\r\n" + sent, wait=3)

    def test_body_never_arrives_408(self):
        before = len(self.actions)
        out, closed = self.post(b'{"action":', 100)
        self.assertTrue(out.startswith(b"HTTP/1.1 408 "), out[:80])
        self.assertEqual(json.loads(out.split(b"\r\n\r\n", 1)[1]), {"error": "body not received"})
        self.assertTrue(closed)
        self.assertEqual(len(self.actions), before)          # nothing ran

    def test_complete_body_still_runs(self):
        body = json.dumps({"action": "watch", "job": "0123abcd", "n": 1}).encode()
        out, _ = self.post(body, len(body))
        self.assertTrue(out.startswith(b"HTTP/1.1 200 "), out[:80])


class Expired(Base):
    """A session older than max_age_hours had a valid Telegram signature once: the page is told
    "expired" (so it can say "close and reopen"), never the family's data. A bad signature
    still learns nothing but "unauthorized"."""

    def test_expired_says_expired_and_no_data(self):
        old = init_data(OWNER, int(time.time()) - 25 * 3600)
        for path in ("/api/me", "/api/china"):
            st, h, body = self.api(path, raw=old)
            self.assertEqual((st, json.loads(body)), (401, {"error": "expired"}), path)
            self.assertEqual(h["Cache-Control"], "no-store")

    def test_expired_post_runs_nothing(self):
        before = len(self.actions)
        old = init_data(OWNER, int(time.time()) - 25 * 3600)
        st, _, body = self.req("/api/china/action", "tma " + old, method="POST",
                               body=json.dumps({"action": "watch", "job": "0123abcd", "n": 1}),
                               headers={"Content-Type": "application/json"})
        self.assertEqual((st, json.loads(body)), (401, {"error": "expired"}))
        self.assertEqual(len(self.actions), before)

    def test_tampered_expired_is_plain_unauthorized(self):
        old = init_data(OWNER, int(time.time()) - 25 * 3600)
        st, _, body = self.api("/api/me", raw=old[:-4] + "0000")
        self.assertEqual((st, json.loads(body)), (401, {"error": "unauthorized"}))

    def test_future_date_is_plain_unauthorized(self):
        st, _, body = self.api("/api/me", raw=init_data(OWNER, int(time.time()) + 3600))
        self.assertEqual((st, json.loads(body)), (401, {"error": "unauthorized"}))


class WatchReply(Base):
    """The page's ok / refused comes from the chat's reply text. A product already on the list
    is "done" for the page (the button becomes 👁 Watching); a full list is a refusal."""

    def act(self):
        st, _, body = self.req("/api/china/action", "tma " + init_data(OWNER), method="POST",
                               body=json.dumps({"action": "watch", "job": "0123abcd", "n": 1}),
                               headers={"Content-Type": "application/json"})
        return st, json.loads(body)

    def test_already_watching_is_ok(self):
        type(self).reply = "👁 Already on 🌍 Market watch: X &amp; Y — nothing added."
        self.assertEqual(self.act(), (200, {"ok": True, "message":
                                            "👁 Already on 🌍 Market watch: X & Y — nothing added."}))

    def test_full_list_is_refused(self):
        type(self).reply = "The list is full (20 items). Mark one bought or remove one first."
        st, d = self.act()
        self.assertEqual((st, d["ok"]), (200, False))


if __name__ == "__main__":
    unittest.main()
