"""market/state.write_lock (decision 097): items.json / owner_prices.json gained a second
writer (the Mini App server next to the listener). Two real processes each add items through
read-modify-write; with the lock no update is lost."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from market import state

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


if __name__ == "__main__":
    unittest.main()
