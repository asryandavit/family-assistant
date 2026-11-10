"""The China worker is kept alive and its failures are seen (decision 104, CLAUDE.md §5).

2026-11-10: a search queued at 00:45 sat for ~22 h: the worker the listener started died on
import (china/runner.py half-edited), its output went to DEVNULL, and nothing started it again.
1. Self-heal: queued jobs + no live worker -> start one (on enqueue and at listener start).
2. Crashes seen: worker stderr goes to worker.err; a worker that exits without finishing its job
   tells the person who asked and the owner in one plain line; a job that crashed the worker
   before it started is dropped (no crash loop).
3. Stranded jobs: queued before this worker started and older than stale_job_minutes are
   dropped with "didn't start — please send it again".
"""
import json
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

from china import bot, queue, watch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = {"telegram": {"bot_token_env": "TG_TOKEN_T", "chat_id_env": "TG_OWNER_T",
                    "chat_id_2_env": "TG_SECOND_T"}}


class TG:
    def __init__(self):
        self.html, self.owner = [], []

    def send_html(self, cfg, text, silent=False, chat_id=None, **kw):
        self.html.append((chat_id, text))

    def notify(self, cfg, text):
        self.owner.append(text)

    @staticmethod
    def esc(s):
        return s

    @staticmethod
    def allowed_chats(cfg):
        return ["111", "222"]


class FakeProc:
    def __init__(self, rc=0):
        self.rc = rc

    def wait(self):
        return self.rc

    def poll(self):
        return self.rc


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        shutil.copy(os.path.join(ROOT, "config_china.json"), self.root)
        self.popen_calls = []

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def popen(self, *a, **kw):
        self.popen_calls.append((a, kw))
        return FakeProc()


class SelfHeal(Base):
    def test_starts_worker_when_jobs_wait_and_none_runs(self):
        queue.enqueue({"chat_id": "222", "kind": "search", "description": "rinse aid"}, self.root)
        self.assertIsNotNone(watch.ensure_worker(CFG, self.root, popen=self.popen, thread=False))
        self.assertEqual(len(self.popen_calls), 1)

    def test_nothing_to_do(self):
        self.assertIsNone(watch.ensure_worker(CFG, self.root, popen=self.popen, thread=False))
        queue.enqueue({"chat_id": "222"}, self.root)
        queue.acquire(self.root)                                  # a live worker (us) holds the lock
        self.assertIsNone(watch.ensure_worker(CFG, self.root, popen=self.popen, thread=False))
        self.assertEqual(self.popen_calls, [])

    def test_enqueue_goes_through_ensure_worker(self):
        with mock.patch.object(watch, "ensure_worker") as ew, \
                mock.patch.object(bot.search, "load_cfg", return_value={"taobao_mode": "link"}):
            bot.start_search(CFG, self.root, "222", "rinse aid")
        ew.assert_called_once_with(CFG, self.root)


class CrashSeen(Base):
    def test_stderr_goes_to_a_log_file(self):
        queue.start_worker(self.root, popen=self.popen)
        kw = self.popen_calls[0][1]
        self.assertNotEqual(kw["stderr"], queue.subprocess.DEVNULL)
        self.assertTrue(kw["stderr"].name.endswith("worker.err"))

    def test_job_left_unfinished_is_told_to_asker_and_owner(self):
        queue.set_current({"job": "ab12cd34", "chat_id": "222", "kind": "search",
                           "description": "finish dishwasher rinse"}, self.root)
        tg = TG()
        watch.check_exit(CFG, self.root, -9, tg)
        self.assertEqual(len(tg.html), 1)
        chat, text = tg.html[0]
        self.assertEqual(chat, "222")
        self.assertIn("finish dishwasher rinse", text)
        self.assertIn("please send it again", text)
        self.assertEqual(len(tg.owner), 1)
        self.assertIsNone(queue.read_current(self.root))

    def test_owner_asking_gets_one_message(self):
        queue.set_current({"job": "ab12cd34", "chat_id": "111", "kind": "search",
                           "description": "x y z"}, self.root)
        tg = TG()
        watch.check_exit(CFG, self.root, 1, tg)
        self.assertEqual(len(tg.html) + len(tg.owner), 1)

    def test_crash_before_any_job_drops_the_first_job(self):
        queue.enqueue({"chat_id": "222", "kind": "search", "description": "finish dishwasher rinse"},
                      self.root)
        queue.enqueue({"chat_id": "111", "kind": "search", "description": "second"}, self.root)
        with open(os.path.join(queue.data_dir(self.root), "worker.err"), "w", encoding="utf-8") as f:
            f.write("Traceback...\nSyntaxError: unterminated string literal (detected at line 149)\n")
        tg = TG()
        watch.check_exit(CFG, self.root, 1, tg)
        self.assertEqual(len(queue.pending(self.root)), 1)          # only the culprit dropped
        self.assertIn("didn't start", tg.html[0][1])
        self.assertIn("SyntaxError", tg.owner[0])

    def test_clean_exit_says_nothing(self):
        queue.enqueue({"chat_id": "222", "description": "x"}, self.root)
        tg = TG()
        watch.check_exit(CFG, self.root, 0, tg)
        self.assertEqual((tg.html, tg.owner), ([], []))
        self.assertEqual(len(queue.pending(self.root)), 1)

    def test_watcher_reports_after_exit(self):
        queue.enqueue({"chat_id": "222", "description": "rinse aid"}, self.root)
        tg = TG()
        watch.watch_proc(FakeProc(rc=1), CFG, self.root, tg)
        self.assertIn("didn't start", tg.html[0][1])

    def test_dead_worker_found_at_startup(self):
        queue.set_current({"job": "ab12cd34", "chat_id": "222", "description": "rinse aid"}, self.root)
        tg = TG()
        watch.ensure_worker(CFG, self.root, popen=self.popen, tg=tg, thread=False)
        self.assertIn("rinse aid", tg.html[0][1])

    def test_real_worker_crash_is_reported(self):
        """A real process that dies at once (no jobs/china_search.py in this root), like the
        import crash of 2026-11-10: the watcher drops the job, tells the asker and the owner
        with the worker's own stderr line."""
        queue.enqueue({"chat_id": "222", "kind": "search", "description": "rinse aid"}, self.root)
        tg = TG()
        proc = watch.ensure_worker(CFG, self.root, tg=tg, thread=False)
        watch.watch_proc(proc, CFG, self.root, tg)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("didn't start", tg.html[0][1])
        self.assertIn("china_search.py", tg.owner[0])           # stderr reached the owner line
        self.assertEqual(queue.pending(self.root), [])

    def test_err_tail_hides_the_token(self):
        with open(os.path.join(queue.data_dir(self.root), "worker.err"), "w", encoding="utf-8") as f:
            f.write("ConnectionError: https://api.telegram.org/bot123456:AAH-x_y/sendMessage\n")
        tail = watch.err_tail(self.root)
        self.assertIn("ConnectionError", tail)
        self.assertNotIn("AAH-x_y", tail)


class Stranded(Base):
    def job(self, minutes_ago):
        t = time.gmtime(time.time() - minutes_ago * 60)
        return {"job": "ab12cd34", "chat_id": "222", "kind": "search", "description": "rinse aid",
                "queued_utc": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", t)}

    def test_is_stale(self):
        started = time.time()
        self.assertTrue(queue.is_stale(self.job(22 * 60), started, 30))
        self.assertFalse(queue.is_stale(self.job(5), started, 30))
        late = self.job(45)                       # waited 45 min behind a LIVE worker: not stale
        self.assertFalse(queue.is_stale(late, started - 3600, 30))
        self.assertFalse(queue.is_stale({"job": "x"}, started, 30))   # no time: never dropped

    def test_drop_stale_tells_the_chat(self):
        tg = TG()
        self.assertTrue(watch.drop_if_stale(CFG, self.root, self.job(22 * 60), time.time(), tg))
        chat, text = tg.html[0]
        self.assertEqual(chat, "222")
        self.assertIn("Your China search for “rinse aid” didn't start — please send it again.", text)
        self.assertFalse(watch.drop_if_stale(CFG, self.root, self.job(1), time.time(), tg))

    def test_config_has_the_limit(self):
        with open(os.path.join(ROOT, "config_china.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["stale_job_minutes"], 30)


class ListenerLog(unittest.TestCase):
    def test_tests_never_write_the_live_listener_log(self):
        import listener
        live = os.path.join(listener.ROOT, ".browser", "listener.log")
        before = os.path.getsize(live) if os.path.exists(live) else 0
        listener.log("china handle failed: disk full (test)")
        after = os.path.getsize(live) if os.path.exists(live) else 0
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
