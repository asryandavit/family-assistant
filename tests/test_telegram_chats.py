"""Two-person chat targeting in lib/telegram.py (decision 082), with fake ids in
a patched environment. Nothing is sent: _post is replaced by a recorder."""
import os
import unittest
from unittest import mock

from lib import config, telegram

OWNER, SECOND = "111", "222"
BASE = {"TELEGRAM_BOT_TOKEN": "x", "TELEGRAM_CHAT_ID": OWNER}


class Chats(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load()
        self.posts = []
        self._post = telegram._post
        telegram._post = lambda tok, payload: self.posts.append(payload)

    def tearDown(self):
        telegram._post = self._post

    def _env(self, **extra):
        env = {k: v for k, v in os.environ.items()
               if k not in ("TELEGRAM_CHAT_ID_2", telegram.REPLY_CHAT_ENV)}
        env.update(BASE, **extra)
        return mock.patch.dict(os.environ, env, clear=True)

    def test_allowed_chats(self):
        with self._env():
            self.assertEqual(telegram.allowed_chats(self.cfg), [OWNER])
        with self._env(TELEGRAM_CHAT_ID_2=SECOND):
            self.assertEqual(telegram.allowed_chats(self.cfg), [OWNER, SECOND])
        with self._env(TELEGRAM_CHAT_ID_2=OWNER):            # no duplicates
            self.assertEqual(telegram.allowed_chats(self.cfg), [OWNER])

    def test_default_target_unchanged(self):
        with self._env(TELEGRAM_CHAT_ID_2=SECOND):
            telegram.send_html(self.cfg, "hi")
        self.assertEqual(self.posts[-1]["chat_id"], OWNER)

    def test_explicit_target(self):
        with self._env(TELEGRAM_CHAT_ID_2=SECOND):
            telegram.send_html(self.cfg, "hi", chat_id=SECOND)
        self.assertEqual(self.posts[-1]["chat_id"], SECOND)

    def test_job_launched_for_someone_replies_to_them(self):
        with self._env(TELEGRAM_CHAT_ID_2=SECOND, **{telegram.REPLY_CHAT_ENV: SECOND}):
            telegram.send_html(self.cfg, "price result")
            telegram.notify(self.cfg, "SYSTEM: something failed")
        self.assertEqual(self.posts[0]["chat_id"], SECOND)   # the asker
        self.assertEqual(self.posts[1]["chat_id"], OWNER)    # system: owner only

    def test_send_family_reaches_both(self):
        with self._env(TELEGRAM_CHAT_ID_2=SECOND):
            telegram.send_family(self.cfg, "daily plan", silent=True)
        self.assertEqual([p["chat_id"] for p in self.posts], [OWNER, SECOND])
        self.assertTrue(all(p["disable_notification"] for p in self.posts))


if __name__ == "__main__":
    unittest.main()
