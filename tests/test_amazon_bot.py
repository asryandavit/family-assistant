"""amazon/bot.py: commands queue jobs (never run them), the one clothing question, 👁 Watch with the
exact /dp/ link through the Market add path (and its 'Already on the list' rule), /amazon last."""
import os
import shutil
import tempfile
import unittest
from datetime import date
from unittest import mock

from amazon import bot, queue, report, search
from tests.test_amazon_search import PLAN, RATES, TG, FakeSession

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Bot(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "market"))
        shutil.copy(os.path.join(ROOT, "config_amazon.json"), self.root)
        shutil.copy(os.path.join(ROOT, "market", "tariffs.json"), os.path.join(self.root, "market"))
        self.started = []
        self.patches = [mock.patch.object(queue, "start_worker", lambda root=None: self.started.append(1)),
                        mock.patch.object(bot.telegram, "send_html", lambda cfg, text, **kw: self.sent.append((text, kw)))]
        self.sent = []
        for p in self.patches:
            p.start()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.addCleanup(lambda: [p.stop() for p in self.patches])

    def test_usage_and_description_checks(self):
        self.assertIn("/amazon usb c charger 65w", bot.handle({}, self.root, "/amazon", "111"))
        self.assertIn("3–200 characters", bot.handle({}, self.root, "/amazon ab", "111"))
        self.assertIn("3–200 characters", bot.handle({}, self.root, "/amazon " + "x" * 201, "111"))

    def test_search_is_queued_not_run(self):
        r = bot.handle({}, self.root, "/amazon usb c charger 65w", "222")
        self.assertIn("Searching Amazon UK, Amazon DE, Amazon IT", r)
        job = queue.pop(self.root)
        self.assertEqual((job["chat_id"], job["description"], job["kind"], job["stores"]),
                         ("222", "usb c charger 65w", "search", ["uk", "de", "it"]))
        self.assertEqual(self.started, [1])

    def test_only_one_store(self):
        bot.handle({}, self.root, "/amazon only DE lego technic 42115", "111")
        job = queue.pop(self.root)
        self.assertEqual((job["stores"], job["description"]), (["de"], "lego technic 42115"))
        self.assertIn("Which store", bot.handle({}, self.root, "/amazon only fr lego technic", "111"))

    def test_place_in_line_and_cancel(self):
        bot.handle({}, self.root, "/amazon first item", "111")
        self.assertIn("2nd in line", bot.handle({}, self.root, "/amazon second item", "222"))
        self.assertIn("Removed 1", bot.handle({}, self.root, "/amazon cancel", "222"))
        self.assertIn("Nothing of yours", bot.handle({}, self.root, "/amazon cancel", "222"))

    def test_last_without_a_search(self):
        self.assertIn("No Amazon search", bot.handle({}, self.root, "/amazon last", "222"))

    def test_command_words_are_not_searched(self):
        # 'last' / 'cancel' never become a description (decision 099 for the China form)
        bot.handle({}, self.root, "/amazon last", "222")
        bot.handle({}, self.root, "/amazon cancel", "222")
        self.assertIsNone(queue.pop(self.root))

    def test_question_button_replans_with_the_answer_and_reads_it_back(self):
        plan = dict(PLAN, vague=True, questions=[{"q": "How old is the baby?", "options": ["0-3 months", "6-12 months"]}])
        search.write_json(self.root, "pending_j9.json", {"job": "j9", "chat_id": "222",
                                                         "description": "baby romper", "plan": plan,
                                                         "stores": ["uk", "de", "it"], "answers": []})
        r = bot.callback({}, self.root, "am:q:j9:0:1", "222")
        self.assertIn("Searching", r)
        job = queue.pop(self.root)
        self.assertEqual(job["answers"], ["How old is the baby 6-12 months"])
        self.assertNotIn("plan", job)                                # planned again, with the age in the words
        self.assertFalse(os.path.exists(os.path.join(search.data_dir(self.root), "pending_j9.json")))

    def test_skip_searches_as_is_without_asking_again(self):
        plan = dict(PLAN, vague=True, questions=[{"q": "How old is the baby?", "options": ["0-3 months", "6-12 months"]}])
        search.write_json(self.root, "pending_j8.json", {"job": "j8", "chat_id": "222",
                                                         "description": "baby romper", "plan": plan,
                                                         "stores": ["uk"], "answers": []})
        bot.callback({}, self.root, "am:q:j8:0:-1", "222")
        job = queue.pop(self.root)
        self.assertTrue(job["no_questions"])
        self.assertNotIn("answers", job)

    def test_question_of_another_chat_or_expired(self):
        self.assertIn("expired", bot.callback({}, self.root, "am:q:nope:0:0", "222"))
        search.write_json(self.root, "pending_j7.json", {"job": "j7", "chat_id": "111", "description": "x y z",
                                                         "plan": dict(PLAN, questions=[{"q": "A?", "options": ["a", "b"]}]),
                                                         "stores": None, "answers": []})
        self.assertIn("expired", bot.callback({}, self.root, "am:q:j7:0:0", "222"))

    def test_unknown_button(self):
        self.assertEqual(bot.callback({}, self.root, "am:zzz", "222"), "Unrecognised button.")

    def test_prompt_reply_routes(self):
        self.assertEqual(bot.route_reply("usb c charger", bot.PROMPT), "/amazon usb c charger")
        self.assertEqual(bot.route_reply("/help", bot.PROMPT), "/help")
        self.assertEqual(bot.route_reply("hello", "something else"), "hello")

    # ---- 👁 Watch through the Market add path

    def _answered(self):
        tg = TG()
        j = {"job": "ab12cd34", "kind": "search", "chat_id": "222", "description": "usb c charger 65w"}
        search.run_search(j, {}, self.root, tg, date(2026, 11, 10), log=lambda m: None,
                          plan_fn=lambda *a: (PLAN, {}), reason_fn=lambda *a: ("ok", {}),
                          session_factory=lambda a, lg: FakeSession(), rates_get=lambda r, d: RATES)
        return search.load_last(self.root, "222")

    def test_watch_adds_the_exact_dp_link_once(self):
        last = self._answered()
        from market import state
        first = last["sites"][0]["ranked"][0]
        with mock.patch.object(state, "data_dir", lambda root: os.path.join(self.root, "md")), \
                mock.patch("market.bot.sheet_id", lambda root: None):
            os.makedirs(os.path.join(self.root, "md"), exist_ok=True)
            r = bot.callback({}, self.root, "am:watch:ab12cd34:1", "222")
            self.assertIn("Added to 🌍 Market watch", r)
            items = state.load_items(self.root)
            self.assertEqual(items[0]["links"], [first["url"]])
            self.assertRegex(items[0]["links"][0], r"^https://www\.amazon\.co\.uk/dp/[A-Z0-9]{10}$")
            again = bot.callback({}, self.root, "am:watch:ab12cd34:1", "222")
            self.assertTrue(again.startswith("👁 Already on 🌍 Market watch"), again)
            self.assertEqual(len(state.load_items(self.root)), 1)
            other = bot.callback({}, self.root, "am:watch:ab12cd34:2", "222")
            self.assertIn("Added to 🌍 Market watch", other)

    def test_watch_old_or_unknown_result(self):
        self.assertIn("gone", bot.callback({}, self.root, "am:watch:zzzz:1", "222"))
        self._answered()
        self.assertIn("gone", bot.callback({}, self.root, "am:watch:ab12cd34:99", "222"))

    def test_last_resends_the_saved_answer(self):
        self._answered()
        sent = []
        with mock.patch.object(bot.telegram, "send_rich", lambda cfg, rich, plain, **kw: sent.append((rich, kw))):
            self.assertIsNone(bot.handle({}, self.root, "/amazon last", "222"))
        self.assertIn("🏆", sent[0][0])
        self.assertEqual(sent[0][1]["chat_id"], "222")


class MarketMenu(unittest.TestCase):
    def test_market_menu_has_the_amazon_button_next_to_china(self):
        from market import bot as mbot
        with mock.patch.object(mbot, "sheet_id", lambda root: None):
            _text, rows = mbot.list_view(tempfile.mkdtemp())
        flat = [d for row in rows for _lbl, d in row]
        self.assertIn("am:ask", flat)
        self.assertIn("cn:ask", flat)


class Report(unittest.TestCase):
    def test_buttons_are_ids_only_and_under_the_64_byte_cap(self):
        shown = [(i, {"price": 1.0}) for i in range(1, 10)]
        rows = report.buttons("ab12cd34", shown)
        for row in rows:
            for _, data in row:
                self.assertLessEqual(len(data.encode()), 64)
        self.assertEqual(sum(len(r) for r in rows), 9)


if __name__ == "__main__":
    unittest.main()
