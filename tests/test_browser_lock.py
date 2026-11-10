"""scrapers/browser_lock.py: one owner of the bot's browser profile at a time (decision 101).
The nightly market scan and the /amazon worker both open .browser/market through Session."""
import json
import os
import shutil
import tempfile
import unittest

from scrapers import browser_lock as bl


class BrowserLock(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_second_taker_waits_then_is_refused(self):
        bl.acquire("a", 0, self.root)
        with self.assertRaises(bl.BrowserBusy) as cm:
            bl.acquire("b", 0, self.root, log=lambda *_: None)
        self.assertIn("in use by a", str(cm.exception))

    def test_release_frees_it(self):
        bl.acquire("a", 0, self.root)
        bl.release(self.root)
        bl.acquire("b", 0, self.root)                  # no error
        self.assertEqual(bl.holder(self.root)["who"], "b")

    def test_lock_of_a_dead_process_is_cleared(self):
        with open(bl.path(self.root), "w", encoding="utf-8") as f:
            json.dump({"pid": 2 ** 22 + 12345, "since": 0, "who": "crashed"}, f)
        bl.acquire("b", 0, self.root)
        self.assertEqual(bl.holder(self.root)["pid"], os.getpid())

    def test_release_leaves_another_processes_lock(self):
        with open(bl.path(self.root), "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid() + 1, "since": 0, "who": "other"}, f)
        bl.release(self.root)
        self.assertTrue(os.path.exists(bl.path(self.root)))


if __name__ == "__main__":
    unittest.main()
