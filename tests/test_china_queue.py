"""china/queue.py: FIFO, place in line, one worker, stale lock cleared, /cancel per chat."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from china import queue


class Queue(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_fifo_and_place(self):
        self.assertEqual(queue.enqueue({"chat_id": "1", "kind": "search", "q": "a"}, self.root), 1)
        self.assertEqual(queue.enqueue({"chat_id": "2", "kind": "search", "q": "b"}, self.root), 2)
        self.assertEqual(queue.enqueue({"chat_id": "1", "kind": "login_check"}, self.root), 3)
        self.assertEqual([queue.pop(self.root)["q"] for _ in range(2)], ["a", "b"])
        self.assertEqual(queue.pop(self.root)["kind"], "login_check")
        self.assertIsNone(queue.pop(self.root))

    def test_unreadable_job_dropped(self):
        with open(os.path.join(queue.qdir(self.root), "0_bad.json"), "w") as f:
            f.write("{not json")
        queue.enqueue({"chat_id": "1", "q": "ok"}, self.root)
        self.assertEqual(queue.pop(self.root)["q"], "ok")
        self.assertEqual(queue.pending(self.root), [])

    def test_cancel_only_own_chat(self):
        queue.enqueue({"chat_id": "1"}, self.root)
        queue.enqueue({"chat_id": "2"}, self.root)
        queue.enqueue({"chat_id": "1"}, self.root)
        self.assertEqual(queue.remove_for_chat("1", self.root), 2)
        self.assertEqual(queue.pop(self.root)["chat_id"], "2")

    def test_single_worker_and_stale_lock(self):
        self.assertTrue(queue.acquire(self.root))
        self.assertFalse(queue.acquire(self.root))                 # we are alive
        self.assertIsNotNone(queue.running(self.root))
        with open(queue.lock_path(self.root), "w") as f:
            json.dump({"pid": 999999999, "since": 0}, f)            # dead pid
        self.assertIsNone(queue.running(self.root))
        self.assertTrue(queue.acquire(self.root))                  # stale lock cleared
        queue.release(self.root)
        self.assertFalse(os.path.exists(queue.lock_path(self.root)))

    def test_start_worker_only_when_none_runs(self):
        calls = []
        self.assertTrue(queue.start_worker(self.root, popen=lambda *a, **k: calls.append(a)))
        self.assertIn("china_search.py", calls[0][0][1])
        queue.acquire(self.root)
        self.assertFalse(queue.start_worker(self.root, popen=lambda *a, **k: calls.append(a)))
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
