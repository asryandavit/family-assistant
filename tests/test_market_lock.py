"""market/state.write_lock (decision 097): items.json / owner_prices.json gained a second
writer (the Mini App server next to the listener). Two real processes each add items through
read-modify-write; with the lock no update is lost."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from jobs import market_watch
from market import sheet, state

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WORKER = r"""
import sys, time
sys.path.insert(0, sys.argv[1])
from market import state
root, tag, n = sys.argv[2], sys.argv[3], int(sys.argv[4])
for i in range(n):
    with state.write_lock(root):
        items = state.load_items(root)
        time.sleep(0.005)                       # widen the race window
        items.append({"id": f"{tag}{i}"})
        state.save_items(root, items)
"""


class WriteLock(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def lock_file(self):
        return os.path.join(state.data_dir(self.root), state.LOCK)

    def test_released_after_use_and_after_error(self):
        with state.write_lock(self.root):
            self.assertTrue(os.path.exists(self.lock_file()))
        self.assertFalse(os.path.exists(self.lock_file()))
        with self.assertRaises(RuntimeError), state.write_lock(self.root):
            raise RuntimeError("boom")
        self.assertFalse(os.path.exists(self.lock_file()))

    def test_busy_when_held(self):
        with state.write_lock(self.root):
            t0 = time.monotonic()
            with self.assertRaises(state.Busy) as cm, state.write_lock(self.root, wait_s=0.3):
                pass
            self.assertGreaterEqual(time.monotonic() - t0, 0.3)
        self.assertIsInstance(cm.exception, ValueError)     # china/bot shows ValueError text
        self.assertIn("try again", str(cm.exception))

    def test_stale_lock_taken_over(self):
        with open(self.lock_file(), "w") as f:
            f.write("99999")
        old = time.time() - 600
        os.utime(self.lock_file(), (old, old))
        with state.write_lock(self.root, wait_s=0.5):
            pass
        self.assertFalse(os.path.exists(self.lock_file()))

    def test_owner_price_under_lock(self):
        with state.write_lock(self.root), self.assertRaises(state.Busy):
            orig = state.write_lock
            try:
                state.write_lock = lambda root: orig(root, wait_s=0.2)
                from datetime import date
                state.set_owner_price(self.root, "a", "s", 1.0, "CNY", date(2026, 11, 10))
            finally:
                state.write_lock = orig

    def test_two_processes_lose_nothing(self):
        script = os.path.join(self.root, "w.py")
        with open(script, "w") as f:
            f.write(WORKER)
        procs = [subprocess.Popen([sys.executable, script, ROOT, self.root, tag, "25"])
                 for tag in ("a", "b")]
        for p in procs:
            self.assertEqual(p.wait(timeout=120), 0)
        ids = {it["id"] for it in state.load_items(self.root)}
        self.assertEqual(len(ids), 50)
        with open(os.path.join(state.data_dir(self.root), "items.json"), encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)), 50)

class Release(unittest.TestCase):
    """Review 2026-11-10 (decision 099): a holder that outlived stale_s was taken over, and on
    its way out removed the NEW holder's lock file, letting a third writer in beside it."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def lock_file(self):
        return os.path.join(state.data_dir(self.root), state.LOCK)

    def test_slow_holder_leaves_the_next_holders_lock(self):
        with state.write_lock(self.root):
            os.remove(self.lock_file())                    # what a stale takeover does ...
            with open(self.lock_file(), "w") as f:         # ... then the new holder's own file
                f.write("someone-else")
        with open(self.lock_file()) as f:
            self.assertEqual(f.read(), "someone-else")
        with self.assertRaises(state.Busy), state.write_lock(self.root, wait_s=0.2):
            pass

    def test_lock_file_gone_meanwhile_is_not_an_error(self):
        with state.write_lock(self.root):
            os.remove(self.lock_file())
        self.assertFalse(os.path.exists(self.lock_file()))


class NightlyJob(unittest.TestCase):
    """The nightly job (and Check now) wrote items.json without the lock: an item added while
    it was between its read and its write was overwritten (decision 099)."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        state.save_items(self.root, [{"id": "1", "name": "old", "weight_kg": None,
                                      "size_cm": None, "status": "active"}])
        self.real_save = state.save_items

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def add_item_when(self, started):
        """What 👁 Watch does in the listener or the Mini App server, in another thread."""
        def adder():
            started.wait(5)
            with state.write_lock(self.root):
                items = state.load_items(self.root)
                items.append({"id": "2", "name": "added meanwhile", "status": "active"})
                self.real_save(self.root, items)
        t = threading.Thread(target=adder)
        t.start()
        return t

    def ids(self):
        return {it["id"] for it in state.load_items(self.root)}

    def test_page_weight_fill_keeps_a_concurrent_add(self):
        started = threading.Event()

        def slow_save(root, items):                 # the job between its read and its write
            started.set()
            time.sleep(0.3)
            self.real_save(root, items)
        t = self.add_item_when(started)
        with mock.patch.object(state, "save_items", slow_save):
            market_watch.apply_filled(self.root, [("1", 1.2, None, "product")], [], log=lambda m: None)
        t.join()
        self.assertEqual(self.ids(), {"1", "2"})
        self.assertEqual(state.load_items(self.root)[0]["weight_kg"], 1.2)

    def test_sheet_merge_keeps_a_concurrent_add(self):
        started = threading.Event()

        def slow_sheet(cfg, sheet_id):              # the Google Sheet read takes seconds
            started.set()
            time.sleep(0.3)
            return []
        t = self.add_item_when(started)
        with mock.patch.object(sheet, "read_items_tab", slow_sheet):
            _, problems = market_watch.sync_list({}, self.root, "sheet-id")
        t.join()
        self.assertEqual(problems, [])
        self.assertEqual(self.ids(), {"1", "2"})

    def test_busy_list_skips_the_fill_and_says_so(self):
        said = []
        with state.write_lock(self.root):
            market_watch.apply_filled(self.root, [("1", 1.2, None, "product")], [],
                                      log=said.append, wait_s=0.2)
        self.assertIsNone(state.load_items(self.root)[0]["weight_kg"])
        self.assertIn("busy", " ".join(said))

    def test_busy_list_uses_the_local_list_and_says_so(self):
        with state.write_lock(self.root), mock.patch.object(sheet, "read_items_tab") as read:
            items, problems = market_watch.sync_list({}, self.root, "sheet-id", wait_s=0.2)
        read.assert_not_called()
        self.assertEqual([it["id"] for it in items], ["1"])
        self.assertIn("busy", problems[0])


if __name__ == "__main__":
    unittest.main()
