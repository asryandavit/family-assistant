"""Mini App review, 2026-11-10 (decision 099): request framing.

Raw sockets, because the point is what the server does with bytes a browser never sends but
an attacker who knows the public URL can: a body on a GET, a body that never arrives. Behind
Tailscale Funnel the proxy reuses one connection to this server for several clients, so a
request that leaves unread bytes behind is a request-smuggling primitive."""
import socket
import time
import unittest

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


if __name__ == "__main__":
    unittest.main()
