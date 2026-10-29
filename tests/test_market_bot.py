"""/watch commands and the add dialog (market/bot.py), in a temporary data folder."""
import tempfile
import unittest
from datetime import date
from unittest import mock

from market import bot, state

CFG = {"telegram": {"bot_token_env": "X_TOKEN", "chat_id_env": "X_CHAT", "chat_id_2_env": "X_CHAT2"}}
DE = "https://www.amazon.de/dp/B0B7RZBWLR?th=1&psc=1"
WB = "https://www.wildberries.ru/catalog/123456/detail.aspx"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.sent = []
        p = mock.patch("lib.telegram.send_html",
                       side_effect=lambda cfg, text, **kw: self.sent.append((text, kw)))
        p.start()
        self.addCleanup(p.stop)
        e = mock.patch.dict("os.environ", {"X_CHAT": "111", "X_CHAT2": "222"})
        e.start()
        self.addCleanup(e.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def say(self, text, chat="111"):
        if not text.startswith("/"):
            text = bot.route_reply(text, "🌍 Market · add\n…")
        return bot.handle(CFG, self.root, text, chat, today=date(2026, 10, 29))


class AddDialog(Base):
    def test_happy_path(self):
        self.assertIsNone(self.say("/watch add"))
        self.assertIn("1/4", self.sent[-1][0])
        self.assertEqual(self.sent[-1][1]["force_reply"], "Airfryer Philips HD9252")
        self.assertIsNone(self.say("Airfryer"))
        self.assertIn("2/4", self.sent[-1][0])
        self.assertIsNone(self.say(DE))
        self.assertIsNone(self.say("1"))
        reply = self.say("4,6 kg 45x35x25")
        self.assertIn("✅ Added <b>1. Airfryer</b>", reply)
        it = state.load_items(self.root)[0]
        self.assertEqual((it["weight_kg"], it["size_cm"], it["qty"], it["added_by"]),
                         (4.6, [45.0, 35.0, 25.0], 1, "Davit"))
        self.assertEqual(it["links"], [DE])

    def test_skip_weight_says_needed(self):
        for t in ("/watch add", "Boots", WB, "2"):
            self.say(t, chat="222")
        reply = self.say("skip", chat="222")
        self.assertIn("No weight yet", reply)
        self.assertEqual(state.load_items(self.root)[0]["added_by"], "Karine")

    def test_unknown_store_rejected_and_asked_again(self):
        self.say("/watch add")
        self.say("Lamp")
        reply = self.say("https://www.ebay.com/itm/1")
        self.assertIn("I don't watch that store yet (www.ebay.com)", reply)
        self.assertIn("2/4", self.sent[-1][0])                 # same question again
        self.assertEqual(state.load_items(self.root), [])

    def test_bad_qty_and_weight(self):
        for t in ("/watch add", "Lamp", DE):
            self.say(t)
        self.assertIn("whole number", self.say("lots"))
        self.say("1")
        self.assertIn("weight like", self.say("heavy"))
        self.assertEqual(state.load_items(self.root), [])

    def test_stop(self):
        self.say("/watch add")
        self.assertIn("nothing was added", self.say("stop"))
        self.assertIn("expired", self.say("Lamp"))

    def test_china_template(self):
        with mock.patch("market.stores.load", return_value={
                "taobao": {"key": "taobao", "name": "Taobao", "host": "item.taobao.com", "reader": "none",
                           "origin": "china", "currency": "CNY", "modes": ["air"], "postcode": ""}}):
            for t in ("/watch add", "Lamp", "https://item.taobao.com/item.htm?id=1", "1"):
                self.say(t)
            reply = self.say("skip")
        self.assertIn(bot.CHINESE_TEMPLATE, reply)

    def test_slash_command_as_reply_left_alone(self):
        self.assertIsNone(bot.route_reply("/watch", "🌍 Market · add"))
        self.assertIsNone(bot.route_reply("hello", "Which product?"))


class Commands(Base):
    def setUp(self):
        super().setUp()
        items = []
        items.append(state.new_item(items, "Airfryer", [DE], weight_kg=4.6))
        items.append(state.new_item(items, "Boots", [WB]))
        state.save_items(self.root, items)

    def test_list(self):
        self.assertIsNone(self.say("/watch"))
        text, kw = self.sent[-1]
        self.assertIn("1. <b>Airfryer</b> · Amazon DE", text)
        self.assertIn("2. <b>Boots</b> · Wildberries · ⚖️ weight needed", text)
        self.assertEqual(kw["buttons"][0], [("🔄 Check now", "cmd:market"), ("➕ Add", "mk:add")])

    def test_bought_and_remove(self):
        self.assertIn("marked bought", self.say("/watch bought 1"))
        self.assertIn("removed", self.say("/watch remove 1"))        # Boots is now number 1
        self.assertEqual(state.active(state.load_items(self.root)), [])
        self.assertIn("No active item 5", self.say("/watch bought 5"))

    def test_owner_price(self):
        reply = self.say("/watch price 2 9 890")
        self.assertIn("9,890 ₽ (owner, 29 Oct)", reply)
        self.assertEqual(state.load_owner_prices(self.root)["2|wildberries"]["price"], 9890)

    def test_owner_price_wrong_currency(self):
        self.assertIn("type the amount in RUB", self.say("/watch price 2 $50"))

    def test_owner_price_needs_store_when_several(self):
        items = state.load_items(self.root)
        items[1]["links"].append("https://am.ozon.com/product/x-1/")
        state.save_items(self.root, items)
        self.assertIn("add the store", self.say("/watch price 2 9890"))
        self.assertIn("(owner", self.say("/watch price 2 9890 ozon"))

    def test_weight(self):
        self.assertIn("1.2 kg · 30x20x10 cm", self.say("/watch weight 2 1,2 30x20x10"))
        self.assertIn("weight like", self.say("/watch weight 2 lots"))

    def test_help(self):
        self.assertIn("/watch add", self.say("/watch what"))

    def test_section_rows(self):
        text, rows = bot.section(self.root)
        self.assertIn("Market watch", text)
        for row in rows:
            for label, data in row:
                self.assertLessEqual(len(data.encode()), 64)


if __name__ == "__main__":
    unittest.main()
