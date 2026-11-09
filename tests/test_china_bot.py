"""china/bot.py: commands queue jobs (never run them), buttons, questions, 👁 Watch."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import date
from unittest import mock

from china import bot, queue, search, validate
from tests.test_china_search import RATES, TG, pdd_answer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Bot(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "market"))
        shutil.copy(os.path.join(ROOT, "config_china.json"), self.root)
        shutil.copy(os.path.join(ROOT, "market", "tariffs.json"), os.path.join(self.root, "market"))
        self.started = []
        self.p1 = mock.patch.object(queue, "start_worker", lambda root=None: self.started.append(1))
        self.p1.start()
        self.sent = []
        self.p2 = mock.patch.object(bot.telegram, "send_html",
                                    lambda cfg, text, **kw: self.sent.append((text, kw)))
        self.p2.start()

    def tearDown(self):
        self.p1.stop()
        self.p2.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_search_is_queued_not_run(self):
        r = bot.handle({}, self.root, "/china GaN charger 65W", "222")
        self.assertIn("Searching Pinduoduo, Taobao, 1688", r)
        job = queue.pop(self.root)
        self.assertEqual((job["chat_id"], job["description"], job["kind"]), ("222", "GaN charger 65W", "search"))
        self.assertEqual(self.started, [1])

    def test_only_site(self):
        bot.handle({}, self.root, "/china only TMALL Grohe faucet", "111")
        self.assertEqual(queue.pop(self.root)["sites"], ["taobao"])
        self.assertIn("Which site", bot.handle({}, self.root, "/china only ebay x y", "111"))

    def test_place_in_line(self):
        bot.handle({}, self.root, "/china first item", "111")
        r = bot.handle({}, self.root, "/china second item", "222")
        self.assertIn("2nd in line", r)

    def test_bad_input(self):
        self.assertIn("China search", bot.handle({}, self.root, "/china", "1"))
        self.assertIn("3–200", bot.handle({}, self.root, "/china x", "1"))
        self.assertIn("3–200", bot.handle({}, self.root, "/china " + "a" * 201, "1"))

    def test_cancel_own(self):
        bot.handle({}, self.root, "/china one thing", "111")
        bot.handle({}, self.root, "/china other thing", "222")
        self.assertIn("Removed 1", bot.handle({}, self.root, "/china cancel", "111"))
        self.assertEqual(queue.pop(self.root)["chat_id"], "222")

    def test_route_reply(self):
        self.assertEqual(bot.route_reply("GaN 65W", bot.PROMPT), "/china GaN 65W")
        self.assertEqual(bot.route_reply("/help", bot.PROMPT), "/help")
        self.assertEqual(bot.route_reply("GaN", "something else"), "GaN")

    def _answered(self):
        def reader(cfg, ccfg, site, desc, q, log=print):
            return pdd_answer(), {}
        plan = {"query_cn": "氮化镓充电器 65W", "category": "electronics", "vague": False, "questions": []}
        search.run_search({"job": "ab12cd34", "chat_id": "222", "description": "GaN 65W",
                           "sites": ["pinduoduo"]}, {}, self.root, TG(), date(2026, 11, 9),
                          log=lambda m: None, read=reader, plan_fn=lambda *a: (plan, {}),
                          rates_get=lambda r, d: RATES)

    def test_only_button_reuses_plan(self):
        self._answered()
        r = bot.callback({}, self.root, "cn:only:1688:ab12cd34", "222")
        self.assertIn("Searching 1688", r)
        job = queue.pop(self.root)
        self.assertEqual((job["sites"], job["plan"]["query_cn"]), (["1688"], "氮化镓充电器 65W"))
        self.assertIn("older than 24 h", bot.callback({}, self.root, "cn:only:1688:ab12cd34", "111"))

    def test_reviews_button_queues(self):
        self._answered()
        bot.callback({}, self.root, "cn:rev:ab12cd34:2", "222")
        job = queue.pop(self.root)
        self.assertEqual((job["kind"], job["for_job"], job["n"]), ("reviews", "ab12cd34", 2))

    def test_watch_button_adds_market_item(self):
        self._answered()
        from market import state
        with mock.patch.object(state, "data_dir", lambda root: os.path.join(self.root, "md")), \
                mock.patch("market.bot.sheet_id", lambda root: None):
            os.makedirs(os.path.join(self.root, "md"), exist_ok=True)
            r = bot.callback({}, self.root, "cn:watch:ab12cd34:1", "222")
            items = state.load_items(self.root)
            prices = state.load_owner_prices(self.root)
        self.assertIn("Added to 🌍 Market watch", r)
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["links"][0].startswith("https://mobile.yangkeduo.com/goods.html?goods_id="))
        self.assertIsNone(items[0]["weight_kg"])                  # 1 kg was only an estimate
        key = "%s|pinduoduo" % items[0]["id"]
        self.assertEqual(prices[key]["currency"], "CNY")

    def test_questions_then_search(self):
        plan = {"query_cn": "跑鞋", "category": "shoes", "vague": True,
                "questions": [{"q": "Size?", "options": ["EU 42", "EU 43"]},
                              {"q": "Budget?", "options": ["< ¥300", "¥300+"]}]}
        search.write_json(self.root, "pending_j9.json", {"job": "j9", "chat_id": "222", "description": "running shoes",
                                                         "plan": plan, "sites": ["pinduoduo"], "answers": []})
        self.assertIsNone(bot.callback({}, self.root, "cn:q:j9:0:1", "222"))   # asks question 2
        self.assertIn("Budget?", self.sent[-1][0])
        self.assertIsNone(bot.callback({}, self.root, "cn:q:j9:0:0", "222"))   # old tap ignored
        r = bot.callback({}, self.root, "cn:q:j9:1:-1", "222")                # skip
        self.assertIn("Searching Pinduoduo", r)
        job = queue.pop(self.root)
        self.assertEqual(job["answers"], ["Size EU 43"])
        self.assertFalse(job["plan"]["vague"])

    def test_question_from_other_chat_refused(self):
        search.write_json(self.root, "pending_j8.json", {"job": "j8", "chat_id": "222", "description": "x",
                                                         "plan": {"questions": [{"q": "a", "options": ["1", "2"]}]},
                                                         "answers": []})
        self.assertIn("expired", bot.callback({}, self.root, "cn:q:j8:0:0", "111"))

    def test_unknown_buttons(self):
        for d in ("cn:only:ebay:x", "cn:rev:x:y", "cn:q:x:0:9", "cn:zzz"):
            self.assertIn(bot.callback({}, self.root, d, "1"), ("Unrecognised button.",
                                                               "That question has expired — send /china again."))


if __name__ == "__main__":
    unittest.main()
