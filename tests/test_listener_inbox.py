"""listener.inbox_loop (decision 098): a command the Mini App queued runs through handle_text
from the person's own chat, replies go to that chat, bad requests are dropped. Telegram and the
runner are stubs; the loop is run for one pass by making time.sleep raise."""
import shutil
import tempfile
import unittest
from unittest import mock

import listener
from lib import config
from miniapp import inbox
from tests.test_listener_ux import FakeRunner, Recorder


class Stop(Exception):
    pass


class InboxLoop(unittest.TestCase):
    def setUp(self):
        self.cfg, self.runner = config.load(), FakeRunner()
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)

    def one_pass(self, allowed=("111",)):
        with mock.patch.object(listener, "ROOT", self.root), \
                mock.patch.object(listener, "log"), \
                mock.patch.object(listener.time, "sleep", side_effect=Stop), \
                Recorder() as rec, self.assertRaises(Stop):
            listener.inbox_loop(self.cfg, self.runner, set(allowed))
        return rec

    def test_runs_command_as_the_chat_and_replies_there(self):
        inbox.put(self.root, "111", "/basket weekly")
        with mock.patch.object(listener, "handle_text", return_value="⏳ ok") as h:
            rec = self.one_pass()
        h.assert_called_once_with(self.cfg, self.runner, "/basket weekly", "111")
        self.assertEqual(rec.sent[-1][1]["chat_id"], "111")

    def test_no_reply_no_message(self):
        inbox.put(self.root, "111", "/scan")
        with mock.patch.object(listener, "handle_text", return_value=None):
            rec = self.one_pass()
        self.assertEqual(rec.sent, [])

    def test_foreign_and_bad_never_run(self):
        inbox.put(self.root, "999", "/scan")
        inbox.put(self.root, "111", "/scan")
        with mock.patch.object(listener, "handle_text", return_value=None) as h:
            self.one_pass(allowed=("222",))
        h.assert_not_called()

    def test_a_failing_command_does_not_kill_the_loop(self):
        inbox.put(self.root, "111", "/scan")
        with mock.patch.object(listener, "handle_text", side_effect=RuntimeError("boom")):
            self.one_pass()                      # reaches time.sleep -> Stop, so it survived


if __name__ == "__main__":
    unittest.main()
