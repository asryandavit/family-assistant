"""miniapp.inbox: the Mini App -> listener command hand-over (decision 098)."""
import os
import shutil
import tempfile
import time
import unittest

from miniapp import inbox


class Check(unittest.TestCase):
    def test_allowed(self):
        for t, want in [("/basket weekly", ("basket", "weekly")), ("/scan", ("scan", "")),
                        ("/digest", ("digest", "")), ("/flights BUD 01-30.11 7", ("flights", "BUD 01-30.11 7")),
                        ("/stays LCA 04-11.11 sea", ("stays", "LCA 04-11.11 sea")),
                        ("/price olive oil parma", ("price", "olive oil parma")),
                        ("/watch check", ("watch", "check")),
                        ("/china only 1688 socks", ("china", "only 1688 socks"))]:
            self.assertEqual(inbox.check_text(t), want, t)

    def test_refused(self):
        for t in ["", None, "scan", "/china", "/price", "/basket", "/watch add", "/watch", "/scan now", "/cancel",
                  "/basket\nweekly", "/basket weekly\x00", "/start", "/x" * 5, "/" + "a" * 300,
                  "/price " + "a" * 201, "//scan", "/SCAN", "/auto"]:
            self.assertIsNone(inbox.check_text(t), t)


class Queue(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_put_take_order_and_removal(self):
        t0 = time.time()
        self.assertTrue(inbox.put(self.root, 111, "/scan", t0))
        self.assertTrue(inbox.put(self.root, 222, "/basket weekly", t0 + 1))
        self.assertEqual(inbox.take(self.root, ["111", "222"], t0 + 2),
                         [("111", "/scan"), ("222", "/basket weekly")])
        self.assertEqual(os.listdir(inbox.inbox_dir(self.root)), [])
        self.assertEqual(inbox.take(self.root, ["111", "222"], t0 + 3), [])      # at most once

    def test_put_refuses_bad_input(self):
        self.assertFalse(inbox.put(self.root, 111, "/cancel"))
        self.assertFalse(inbox.put(self.root, "abc", "/scan"))
        self.assertFalse(inbox.put(self.root, "1; rm", "/scan"))
        self.assertEqual(os.listdir(inbox.inbox_dir(self.root)), [])

    def test_stale_dropped(self):
        t0 = time.time()
        inbox.put(self.root, 111, "/scan", t0)
        self.assertEqual(inbox.take(self.root, ["111"], t0 + inbox.MAX_AGE_S + 1), [])
        self.assertEqual(os.listdir(inbox.inbox_dir(self.root)), [])

    def test_foreign_chat_dropped(self):
        inbox.put(self.root, 999, "/scan")
        self.assertEqual(inbox.take(self.root, ["111", "222"]), [])
        self.assertEqual(os.listdir(inbox.inbox_dir(self.root)), [])

    def test_hand_written_file_rechecked(self):
        d = inbox.inbox_dir(self.root)
        name = f"{int(time.time() * 1000):015d}-aaaaaaaa.json"
        with open(os.path.join(d, name), "w", encoding="utf-8") as f:
            f.write('{"chat_id": "111", "text": "/cancel"}')
        with open(os.path.join(d, "junk.json"), "w", encoding="utf-8") as f:
            f.write("{not json")
        with open(os.path.join(d, "x.tmp"), "w", encoding="utf-8") as f:
            f.write("x")
        self.assertEqual(inbox.take(self.root, ["111"]), [])
        self.assertEqual(os.listdir(d), ["x.tmp"])             # in-flight temp files are left alone


if __name__ == "__main__":
    unittest.main()
