"""shopping/checklist.py + shopping/bot.py: one shared tick list per household
(decision 106). Each test works in a temporary root holding a copy of the real
plan/meals/basket.md; nothing is sent to Telegram or the Sheet."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import date

from shopping import bot, checklist

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAVIT, KARINE = "111", "222"
ENV = {"TELEGRAM_CHAT_ID": DAVIT, "TELEGRAM_CHAT_ID_2": KARINE}
SUN = date(2026, 11, 15)          # Sunday of ISO week 46
MON = date(2026, 11, 16)          # the next week


def make_root():
    d = tempfile.mkdtemp(prefix="shoplist-")
    os.makedirs(os.path.join(d, "plan", "meals"))
    shutil.copy(os.path.join(ROOT, "plan", "meals", "basket.md"), os.path.join(d, "plan", "meals"))
    with open(os.path.join(d, "config_miniapp.json"), "w", encoding="utf-8") as f:
        json.dump({"people": [{"env": "TELEGRAM_CHAT_ID", "name": "Davit", "role": "owner"},
                              {"env": "TELEGRAM_CHAT_ID_2", "name": "Karine", "role": "adult"}]}, f)
    return d


class Store(unittest.TestCase):
    def setUp(self):
        self.root = make_root()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_list_is_grouped_by_aisle_in_walking_order(self):
        v = checklist.load(self.root, "weekly", today=SUN)
        aisles = [g["aisle"] for g in v["groups"]]
        self.assertEqual(aisles[:5], ["Vegetables", "Greens", "Fruit", "Dairy & eggs", "Meat & fish"])
        self.assertEqual(len(aisles), len(set(aisles)))               # each aisle once
        self.assertEqual((v["done"], v["period"]), (0, "2026-W46"))
        self.assertEqual(v["total"], 24)                              # 23 priced + Scoolinary
        self.assertEqual(v["period_label"], "week 9 Nov – 15 Nov")
        json.dumps(v)                                                 # Mini App-ready

    def test_both_people_tick_the_same_list_and_ids_are_recorded(self):
        v = checklist.load(self.root, "weekly", today=SUN)
        eggs = next(i["key"] for i in v["items"] if i["item"] == "Eggs")
        checklist.tick(self.root, "weekly", eggs, DAVIT, today=SUN)
        v = checklist.tick(self.root, "weekly", "tomatoes", KARINE, today=SUN)
        got = {i["item"]: i["by"] for i in v["items"] if i["done"]}
        self.assertEqual(got, {"Eggs": int(DAVIT), "Tomatoes": int(KARINE)})
        self.assertEqual(v["done"], 2)
        # the state is on disk, per household
        self.assertTrue(os.path.exists(os.path.join(self.root, ".browser", "shopping", "family",
                                                    "checklist_weekly.json")))
        self.assertEqual(checklist.load(self.root, "weekly", today=SUN)["done"], 2)
        self.assertEqual(checklist.load(self.root, "weekly", household="other", today=SUN)["done"], 0)

    def test_toggle_untick_and_explicit_done(self):
        checklist.tick(self.root, "weekly", "eggs", DAVIT, today=SUN)
        v = checklist.tick(self.root, "weekly", "eggs", KARINE, today=SUN)    # toggle off
        self.assertEqual(v["done"], 0)
        checklist.tick(self.root, "weekly", "eggs", DAVIT, done=True, today=SUN)
        v = checklist.tick(self.root, "weekly", "eggs", DAVIT, done=True, today=SUN)
        self.assertEqual(v["done"], 1)

    def test_a_new_week_starts_empty_and_staples_keep_their_month(self):
        checklist.tick(self.root, "weekly", "eggs", DAVIT, today=SUN)
        checklist.tick(self.root, "monthly", "olive-oil", DAVIT, today=SUN)
        self.assertEqual(checklist.load(self.root, "weekly", today=MON)["done"], 0)
        self.assertEqual(checklist.load(self.root, "monthly", today=MON)["done"], 1)
        self.assertEqual(checklist.load(self.root, "monthly", today=date(2026, 12, 1))["done"], 0)

    def test_reset_clears_ticks_and_records_who(self):
        checklist.tick(self.root, "weekly", "eggs", DAVIT, today=SUN)
        v = checklist.reset(self.root, "weekly", KARINE, today=SUN)
        self.assertEqual(v["done"], 0)
        self.assertEqual(v["reset"]["by"], int(KARINE))

    def test_rejections(self):
        with self.assertRaises(ValueError):
            checklist.tick(self.root, "weekly", "caviar", DAVIT, today=SUN)
        for bad in (None, "", "abc", "-5", "0"):
            with self.assertRaises(ValueError):
                checklist.tick(self.root, "weekly", "eggs", bad, today=SUN)
        with self.assertRaises(ValueError):
            checklist.load(self.root, "yearly", today=SUN)
        with self.assertRaises(ValueError):
            checklist.load(self.root, "weekly", household="../x", today=SUN)

    def test_last_basket_run_fills_shop_and_product(self):
        os.makedirs(os.path.join(self.root, ".browser"), exist_ok=True)
        with open(os.path.join(self.root, ".browser", "basket_weekly.json"), "w", encoding="utf-8") as f:
            json.dump({"lines": [{"item": "Eggs", "status": "ok", "shop": "yc", "buy": "2 × 10 pcs",
                                  "product": 'Eggs "Arzni" 10pcs', "url": "https://y/1",
                                  "app_url": None, "reason": None}]}, f)
        eggs = next(i for i in checklist.load(self.root, "weekly", today=SUN)["items"] if i["item"] == "Eggs")
        self.assertEqual((eggs["shop_name"], eggs["buy"], eggs["url"]), ("Yerevan City", "2 × 10 pcs", "https://y/1"))


class FakeTg:
    def __init__(self):
        self.sent, self.edits, self.n = [], [], 100

    def send(self, chat, text, buttons):
        self.n += 1
        self.sent.append((chat, text, buttons))
        return self.n

    def edit(self, chat, mid, text, buttons):
        self.edits.append((str(chat), int(mid), text, buttons))


class Telegram(unittest.TestCase):
    def setUp(self):
        self.root = make_root()
        self.tg, self.mirrored = FakeTg(), []
        self.mirror = lambda cfg, root, kind, changes: self.mirrored.append((kind, changes))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def cb(self, data, chat, mid):
        return bot.callback({}, self.root, data, chat, mid, tg=self.tg, mirror=self.mirror, env=ENV)

    def buttons(self, chat):
        return next(b for c, _, b in reversed(self.tg.sent) if c == chat)

    def test_list_command_sends_and_every_button_fits(self):
        self.assertIsNone(bot.handle({}, self.root, "/list", DAVIT, tg=self.tg, env=ENV))
        _chat, text, rows = self.tg.sent[0]
        self.assertIn("Shopping list", text)
        self.assertIn("<b>Vegetables</b>", text)
        self.assertIn("0 of 24", text)
        for row in rows:
            for label, data in row:
                self.assertLessEqual(len(data.encode()), 64)
        self.assertEqual(checklist.messages(self.root, "weekly"), {DAVIT: 101})
        self.assertIn("/list", bot.handle({}, self.root, "/list yearly", DAVIT, tg=self.tg, env=ENV))

    def test_a_tick_updates_both_chats_and_the_sheet(self):
        bot.handle({}, self.root, "/list", DAVIT, tg=self.tg, env=ENV)
        bot.handle({}, self.root, "/list", KARINE, tg=self.tg, env=ENV)
        label, data = self.buttons(KARINE)[0][0]
        self.assertTrue(label.startswith("☐ "))
        self.assertIsNone(self.cb(data, KARINE, 102))
        chats = sorted(c for c, *_ in self.tg.edits)
        self.assertEqual(chats, [DAVIT, KARINE])                      # both messages edited
        for _, _, text, rows in self.tg.edits:
            self.assertIn("1 of 24", text)
            self.assertIn("last: Karine ticked", text)
            self.assertTrue(rows[0][0][0].startswith("✅ "))
        item = data.split(":")
        self.assertEqual(self.mirrored[-1][0], "weekly")
        self.assertEqual(list(self.mirrored[-1][1].values()), [True])
        self.assertEqual(len(item), 5)

    def test_a_button_from_an_old_list_is_refused_and_redrawn(self):
        out = self.cb("gl:t:w:000000:0", DAVIT, 55)
        self.assertIn("changed", out)
        self.assertEqual(checklist.load(self.root, "weekly")["done"], 0)
        self.assertEqual(self.tg.edits[-1][:2], (DAVIT, 55))

    def test_new_week_asks_first_then_clears(self):
        bot.handle({}, self.root, "/list", DAVIT, tg=self.tg, env=ENV)
        self.cb(self.buttons(DAVIT)[0][0][1], DAVIT, 101)
        self.assertIsNone(self.cb("gl:r:w", DAVIT, 101))
        self.assertIn("Clear all 1 ticks", self.tg.edits[-1][2])
        self.assertEqual(checklist.load(self.root, "weekly")["done"], 1)        # not yet
        self.cb("gl:R:w", DAVIT, 101)
        self.assertEqual(checklist.load(self.root, "weekly")["done"], 0)
        self.assertTrue(all(v is False for v in self.mirrored[-1][1].values()))

    def test_open_staples_and_unknown_buttons(self):
        self.assertIsNone(self.cb("gl:o:m", DAVIT, 9))
        self.assertIn("monthly staples", self.tg.sent[-1][1])
        for bad in ("gl", "gl:x:w", "gl:t:w", "gl:o:q", "gl:t:w:abc:x"):
            self.assertEqual(self.cb(bad, DAVIT, 9), "Unrecognised button.", bad)

    def test_broken_basket_md_answers_with_a_sentence(self):
        with open(os.path.join(self.root, "plan", "meals", "basket.md"), "a", encoding="utf-8") as f:
            f.write("| weekly | Bad | x | x | lots | kg | | | |\n")
        out = bot.handle({}, self.root, "/list", DAVIT, tg=self.tg, env=ENV)
        self.assertIn("couldn't be read", out)


class SheetMirror(unittest.TestCase):
    def test_updates_only_rows_whose_item_matches(self):
        col_b = ["\U0001f9fa Basket", "", "", "Item", "\U0001f534 Yerevan City", "Eggs", "Matsun",
                 "Yerevan City total", "Total"]
        self.assertEqual(bot.sheet_updates(col_b, {"Eggs": True, "Caviar": True}),
                         [{"range": "A6", "values": [[True]]}])


if __name__ == "__main__":
    unittest.main()
