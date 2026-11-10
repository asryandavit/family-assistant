"""Mini App hardening pass 2 (decision 102): the four items review §14.2 left, each tested first.

1. a request is refused, not silently dropped, when the listener's inbox thread is not alive;
2. the Travel screen's Sheet read is one refresh at a time with a bounded wait;
3. a composed command that the inbox would refuse says so clearly;
4. the server caps its connection threads and answers 503 over the cap."""
import http.client
import os
import shutil
import socket
import tempfile
import threading
import time
import unittest
from unittest import mock

import listener
from lib import config
from miniapp import actions, inbox, screens, server
from tests.test_listener_ux import FakeRunner, Recorder
from tests.test_miniapp_server import CFG, PERSONS, TOKEN


class Stop(Exception):
    pass


class ListenerAlive(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.cfg = config.load()
        self.addCleanup(shutil.rmtree, self.root, True)

    def queued(self):
        return [n for n in os.listdir(inbox.inbox_dir(self.root)) if n.endswith(".json")]

    def test_heartbeat_freshness(self):
        self.assertFalse(inbox.listener_alive(self.root))                 # never written
        inbox.heartbeat(self.root, now=1000.0)
        self.assertTrue(inbox.listener_alive(self.root, now=1000.0 + inbox.ALIVE_S - 1))
        self.assertFalse(inbox.listener_alive(self.root, now=1000.0 + inbox.ALIVE_S + 1))

    def test_unreadable_heartbeat_is_not_alive(self):
        with open(os.path.join(inbox.inbox_dir(self.root), inbox.ALIVE), "w") as f:
            f.write("not a number")
        self.assertFalse(inbox.listener_alive(self.root))

    def test_down_listener_refuses_and_queues_nothing(self):
        ok, msg = actions.run(self.root, self.cfg, 111, "basket", "weekly")
        self.assertFalse(ok)
        self.assertEqual(msg, "The bot is not running on the PC — nothing was sent.")
        self.assertEqual(self.queued(), [])

    def test_validation_errors_still_come_first(self):
        ok, msg = actions.run(self.root, self.cfg, 111, "flights", "BUD")
        self.assertFalse(ok)
        self.assertIn("dates", msg)                                        # the chat's own sentence

    def test_alive_listener_gets_the_request(self):
        inbox.heartbeat(self.root)
        ok, _ = actions.run(self.root, self.cfg, 111, "scan", "")
        self.assertTrue(ok)
        self.assertEqual(len(self.queued()), 1)

    def test_heartbeat_file_is_not_a_request(self):
        inbox.heartbeat(self.root)
        self.assertEqual(inbox.take(self.root, ["111"]), [])
        self.assertTrue(inbox.listener_alive(self.root))                   # take() leaves it alone

    def test_the_listener_thread_writes_it(self):
        with mock.patch.object(listener, "ROOT", self.root), \
                mock.patch.object(listener, "log"), \
                mock.patch.object(listener.time, "sleep", side_effect=Stop), \
                Recorder(), self.assertRaises(Stop):
            listener.inbox_loop(config.load(), FakeRunner(), {"111"})
        self.assertTrue(inbox.listener_alive(self.root))


class SheetRows(unittest.TestCase):
    def setUp(self):
        screens._cache.clear()
        screens._inflight.clear()
        self.addCleanup(screens._cache.clear)
        self.addCleanup(screens._inflight.clear)

    def slow(self, rows, delay, calls):
        def read(cfg, tab):
            calls.append(tab)
            time.sleep(delay)
            return rows
        return read

    def test_a_slow_read_is_bounded_and_fills_the_cache_afterwards(self):
        calls = []
        with mock.patch("lib.sheets.read_all", self.slow([["r"]], 0.8, calls)):
            t0 = time.monotonic()
            self.assertEqual(screens._sheet_rows({}, "Trips", wait_s=0.2), [])
            self.assertLess(time.monotonic() - t0, 0.6)
            time.sleep(1.0)                                               # the refresh finishes
            t0 = time.monotonic()
            self.assertEqual(screens._sheet_rows({}, "Trips", wait_s=0.2), [["r"]])
            self.assertLess(time.monotonic() - t0, 0.3)
        self.assertEqual(len(calls), 1)

    def test_the_last_copy_is_returned_while_a_refresh_runs(self):
        screens._cache["Trips"] = (time.time() - 10 * screens.CACHE_S, [["old"]])
        calls = []
        with mock.patch("lib.sheets.read_all", self.slow([["new"]], 0.8, calls)):
            t0 = time.monotonic()
            self.assertEqual(screens._sheet_rows({}, "Trips", wait_s=0.2), [["old"]])
            self.assertLess(time.monotonic() - t0, 0.6)
            time.sleep(1.0)
            self.assertEqual(screens._sheet_rows({}, "Trips", wait_s=0.2), [["new"]])

    def test_concurrent_callers_cause_one_read(self):
        calls = []
        out = []
        with mock.patch("lib.sheets.read_all", self.slow([["r"]], 0.5, calls)):
            ts = [threading.Thread(target=lambda: out.append(
                screens._sheet_rows({}, "Stays", wait_s=2.0))) for _ in range(6)]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
        self.assertEqual(len(calls), 1)
        self.assertEqual(out, [[["r"]]] * 6)

    def test_failed_and_raising_reads_do_not_wedge_it(self):
        with mock.patch("lib.sheets.read_all", side_effect=RuntimeError("boom")):
            self.assertEqual(screens._sheet_rows({}, "Trips", wait_s=1.0), [])
        self.assertNotIn("Trips", screens._inflight)
        with mock.patch("lib.sheets.read_all", return_value=[["ok"]]):
            self.assertEqual(screens._sheet_rows({}, "Trips", wait_s=1.0), [["ok"]])

    def test_fresh_cache_is_not_refetched(self):
        calls = []
        with mock.patch("lib.sheets.read_all", self.slow([["r"]], 0, calls)):
            screens._sheet_rows({}, "Trips", wait_s=1.0)
            screens._sheet_rows({}, "Trips", wait_s=1.0)
        self.assertEqual(len(calls), 1)


class CommandLength(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load()
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        inbox.heartbeat(self.root)

    def test_only_site_with_a_long_description_is_accepted_and_queued(self):
        desc = "x" * 195                                                  # valid for the chat (≤ 200)
        ok, msg = actions.run(self.root, self.cfg, 111, "china", "only pinduoduo " + desc)
        self.assertTrue(ok, msg)
        self.assertEqual(inbox.take(self.root, ["111"])[0][1], "/china only pinduoduo " + desc)

    def test_description_over_200_gets_the_clear_message(self):
        for args in ("x" * 201, "only 1688 " + "x" * 201):
            text, err = actions.compose("china", args, self.cfg)
            self.assertIsNone(text)
            self.assertIn("3–200 characters", err)

    def test_any_command_the_inbox_would_refuse_is_refused_clearly(self):
        text, err = actions.compose("stays", "LCA 04-11.11 " + "sea " * 60, self.cfg)
        self.assertIsNone(text)
        self.assertIn("too long", err)
        self.assertNotIn("not accepted", err)

    def test_composed_text_always_fits_the_inbox(self):
        for job, args in [("china", "only pinduoduo " + "x" * 200), ("price", "a" * 40),
                          ("flights", "BUD 01-30.11 7"), ("basket", "monthly")]:
            text, _err = actions.compose(job, args, self.cfg)
            if text:
                self.assertIsNotNone(inbox.check_text(text), (job, len(text)))


class ConnectionCap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.makedirs(os.path.join(self.tmp, "dist"))
        with open(os.path.join(self.tmp, "dist", "index.html"), "w") as f:
            f.write("<title>x</title>")
        cfg = dict(CFG, max_connections=3)
        self.app = server.App(cfg, TOKEN, PERSONS, dist=os.path.join(self.tmp, "dist"))
        self.srv = server.Server(("127.0.0.1", 0), self.app)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.idle = []
        self.addCleanup(self.stop)

    def stop(self):
        for s in self.idle:
            s.close()
        self.srv.shutdown()
        self.srv.server_close()

    def occupy(self, n):
        for _ in range(n):
            self.idle.append(socket.create_connection(("127.0.0.1", self.port), timeout=5))
        time.sleep(0.3)                                                    # let the threads start

    def get(self, timeout=5):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        c.request("GET", "/")
        r = c.getresponse()
        body = r.read()
        c.close()
        return r.status, dict(r.getheaders()), body

    def test_over_the_cap_is_a_quick_503(self):
        self.occupy(3)
        t0 = time.monotonic()
        st, h, _ = self.get()
        self.assertEqual(st, 503)
        self.assertLess(time.monotonic() - t0, 2.0)
        self.assertEqual(h.get("Retry-After"), "2")
        self.assertEqual(h.get("Connection"), "close")

    def test_under_the_cap_and_after_release_it_serves(self):
        self.occupy(2)
        self.assertEqual(self.get()[0], 200)
        self.occupy(1)
        self.assertEqual(self.get()[0], 503)
        for s in self.idle:
            s.close()
        self.idle.clear()
        time.sleep(0.5)
        self.assertEqual(self.get()[0], 200)                               # slots came back

    def test_finished_requests_free_their_slot(self):
        for _ in range(10):                                                # > cap, one after another
            self.assertEqual(self.get()[0], 200)

    def test_default_cap_is_32(self):
        s = server.Server(("127.0.0.1", 0), server.App(CFG, TOKEN, PERSONS))
        self.addCleanup(s.server_close)
        self.assertEqual(s.max_connections, 32)


if __name__ == "__main__":
    unittest.main()
