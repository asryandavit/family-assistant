"""lib/telegram.send_rich: rich first, plain fallback on refusal. Nothing is sent: the HTTP
post is a fake. Response shapes from tests/fixtures/china/telegram_rich_sent.json (a real
sendRichMessage answer, 2026-11-09) and the real refusal seen the same day."""
import json
import os
import unittest
from unittest import mock

from lib import config, telegram

F = os.path.join(os.path.dirname(__file__), "fixtures", "china")
BASE = {"TELEGRAM_BOT_TOKEN": "x", "TELEGRAM_CHAT_ID": "111"}


class Resp:
    def __init__(self, d):
        self.d = d

    def json(self):
        return self.d


class SendRich(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load()
        self.calls, self.plain = [], []
        self._post = telegram._post
        telegram._post = lambda tok, payload: self.plain.append(payload)

    def tearDown(self):
        telegram._post = self._post

    def env(self):
        env = {k: v for k, v in os.environ.items() if k != telegram.REPLY_CHAT_ENV}
        env.update(BASE)
        return mock.patch.dict(os.environ, env, clear=True)

    def fake(self, answer):
        def post(url, json=None, timeout=None):
            self.calls.append((url, json))
            if isinstance(answer, Exception):
                raise answer
            return Resp(answer)
        return post

    def test_rich_ok(self):
        with open(os.path.join(F, "telegram_rich_sent.json"), encoding="utf-8") as f:
            sent = json.load(f)
        with self.env():
            kind, mid = telegram.send_rich(self.cfg, "<p>x</p>", "x", post=self.fake(sent))
        self.assertEqual((kind, mid), ("rich", 267))
        url, payload = self.calls[0]
        self.assertTrue(url.endswith("/sendRichMessage"))
        self.assertEqual(payload["rich_message"], {"html": "<p>x</p>"})
        self.assertEqual(payload["chat_id"], "111")
        self.assertTrue(payload["disable_notification"])
        self.assertEqual(self.plain, [])

    def test_refused_falls_back_to_plain(self):
        bad = {"ok": False, "error_code": 400, "description": "Bad Request: BUTTON_DATA_INVALID"}
        with self.env():
            kind, mid = telegram.send_rich(self.cfg, "<p>x</p>", "<b>plain</b>",
                                           buttons=[[("A", "cn:x")]], chat_id="222",
                                           post=self.fake(bad))
        self.assertEqual((kind, mid), ("plain", None))
        self.assertEqual(self.plain[0]["text"], "<b>plain</b>")
        self.assertEqual(self.plain[0]["chat_id"], "222")
        self.assertIn("inline_keyboard", self.plain[0]["reply_markup"])

    def test_network_error_without_fallback(self):
        import requests
        with self.env():
            kind, _ = telegram.send_rich(self.cfg, "<p>x</p>",
                                         post=self.fake(requests.ConnectionError("down")))
        self.assertEqual(kind, "failed")
        self.assertEqual(self.plain, [])

    def test_send_html_unchanged(self):
        with self.env():
            telegram.send_html(self.cfg, "hi")
        self.assertEqual(self.plain[-1]["text"], "hi")
        self.assertEqual(self.plain[-1]["parse_mode"], "HTML")


if __name__ == "__main__":
    unittest.main()
