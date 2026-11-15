"""Mini App Stage B in a real browser (decision 108): Today with the week under it, and the shared
tick list. Same harness as tests/test_miniapp_smoke.py (built app, production CSP, a stub of
Telegram's script). Here the plan pages are the REAL plan code on the repo's plan files (the
clock fixed to a Monday of plan week 4) and the tick list is the REAL checklist on a temp
household; only Telegram and the Sheet behind a tick are recorders."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from unittest import mock

from lib import ui
from miniapp import screens, server, shopping_view
from shopping import checklist
from tests.test_miniapp_screens import FakeSvc
from tests.test_miniapp_server import ADULT, OWNER
from tests.test_miniapp_smoke import SmokeBase

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MONDAY = datetime(2026, 11, 9, 12, 0, tzinfo=ui.YEREVAN)
REASON = "↳ fresh, +13% over Qualiko (limit 15%)"
NAMES = {OWNER: "Davit", ADULT: "Karine"}


def temp_household():
    root = tempfile.mkdtemp()
    os.makedirs(os.path.join(root, "plan", "meals"))
    os.makedirs(os.path.join(root, ".browser"))
    shutil.copy(os.path.join(ROOT, "plan", "meals", "basket.md"), os.path.join(root, "plan", "meals"))
    first = checklist.items_for(root, "weekly")[0]["item"]
    last_run = {"run_utc": "2026-11-15T10:00:00+00:00", "kind": "weekly", "partial": False,
                "totals": {"yc": 1000, "parma": 0, "all": 1000},
                "compare": {"n": 0, "yc": 0, "parma": 0, "cheapest": 0},
                "lines": [{"item": first, "status": "ok", "shop": "yc", "buy": "1 kg", "cost": 1000,
                           "product": "Test product", "url": "https://example.com/p", "reason": REASON}]}
    with open(os.path.join(root, ".browser", "basket_weekly.json"), "w", encoding="utf-8") as f:
        json.dump(last_run, f)
    return root, first


class Svc(FakeSvc):
    """Fake actions (as in the first smoke test) with the real plan pages and the real list."""
    real = None
    chat_root = ROOT

    def plan_page(self, chat_id, name):
        return screens.plan_page(self.chat_root, name, chat_id)

    def list_view(self, kind, names):
        return self.real.list_view(kind, names)

    def list_tick(self, user_id, kind, key, done, names):
        return self.real.list_tick(user_id, kind, key, done, names)

    def list_reset(self, user_id, kind, names):
        return self.real.list_reset(user_id, kind, names)


class StageB(SmokeBase):
    @classmethod
    def make_svc(cls):
        cls.root, cls.first = temp_household()
        real = server.Services()
        real.root = cls.root
        real._bg = lambda fn, *a: fn(*a)
        cls.refresh = mock.patch("shopping.bot.refresh_messages").start()
        cls.mirror = mock.patch("shopping.bot.mirror_to_sheet").start()
        cls.clock = mock.patch.object(ui, "now_local", return_value=MONDAY).start()
        svc = Svc()
        svc.real = real
        return svc

    @classmethod
    def tearDownClass(cls):
        mock.patch.stopall()
        super().tearDownClass()
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self):
        super().setUp()
        checklist.reset(self.root, "weekly", OWNER)
        self.refresh.reset_mock()
        self.mirror.reset_mock()

    def done_on_disk(self):
        return checklist.load(self.root, "weekly")["done"]

    # ---------------------------------------------------------------- Today

    def test_today_shows_meals_with_recipe_links_and_the_week_under_it(self):
        self.open("today")
        self.page.get_by_text("This week's menu").wait_for()
        for label in ("Breakfast", "Lunch", "Dinner"):
            self.assertTrue(self.page.get_by_text(label).first.is_visible(), label)
        self.page.locator("a[href^='https://']").first.wait_for()
        self.assertGreaterEqual(self.page.locator("a[href^='https://']").count(), 1)
        self.page.get_by_text("· today").first.wait_for()                 # today's day is the open one
        self.assertGreaterEqual(self.page.get_by_text("Lunch").count(), 2)  # on top and in its day

    def test_a_recipe_link_opens_outside_the_app(self):
        self.open("today")
        link = self.page.locator("a[href^='https://']").first
        link.wait_for()
        url = link.get_attribute("href")
        link.click()
        self.assertIn(url, self.tg("opened"))

    def test_next_week_is_its_own_page(self):
        self.open("today")
        self.page.get_by_text("Next week", exact=True).click()
        self.page.get_by_text("Next week's menu").wait_for()
        self.assertEqual(self.page.get_by_text("· today").count(), 0)

    # ---------------------------------------------------------------- Basket: the shared tick list

    def tick_row(self):
        return self.page.get_by_text(self.first, exact=True).first

    def test_tapping_a_row_ticks_it_for_the_household(self):
        self.open("basket")
        self.tick_row().wait_for()
        self.assertEqual(self.done_on_disk(), 0)
        self.tick_row().click()
        self.page.get_by_text("✓ Davit").first.wait_for()                  # the name, never an id
        self.assertEqual(self.done_on_disk(), 1)                           # the state /list shows
        self.refresh.assert_called_once()                                  # both chats are edited
        self.assertEqual(list(self.mirror.call_args.args[3].values()), [True])
        self.tick_row().click()
        self.page.locator(".box.on").first.wait_for(state="detached")
        self.assertEqual(self.done_on_disk(), 0)

    def test_the_other_persons_tick_is_shown_by_name(self):
        checklist.tick(self.root, "weekly", checklist.items_for(self.root, "weekly")[0]["key"], ADULT)
        self.open("basket")
        self.page.get_by_text("✓ Karine").first.wait_for()
        self.assertNotIn(str(ADULT), self.page.content())

    def test_the_info_button_shows_the_pick_and_why(self):
        self.open("basket")
        self.page.get_by_label(f"Why this pick: {self.first}").click()
        self.page.get_by_text(REASON).wait_for()
        self.page.get_by_text("Product: Test product").wait_for()
        self.page.get_by_role("button", name="Open the product").click()
        self.assertEqual(self.tg("opened")[-1], "https://example.com/p")
        self.assertEqual(self.done_on_disk(), 0)                           # opening details did not tick

    def test_new_week_asks_first_and_clears_the_ticks(self):
        checklist.tick(self.root, "weekly", checklist.items_for(self.root, "weekly")[0]["key"], OWNER)
        self.open("basket")
        self.page.get_by_text("✓ Davit").first.wait_for()
        self.page.get_by_role("button", name="New week").click()
        self.page.locator(".box.on").first.wait_for(state="detached")
        self.assertIn("Clear all 1 ticks", self.tg("confirms")[-1])
        self.assertEqual(self.done_on_disk(), 0)
        self.assertEqual(shopping_view.view(self.root, "weekly", NAMES)["reset"]["by_name"], "Davit")

    def test_monthly_staples_are_a_separate_list(self):
        self.open("basket")
        self.page.get_by_text("Monthly", exact=True).click()
        self.page.get_by_text("Tick list · ").first.wait_for()
        self.assertEqual(checklist.load(self.root, "monthly")["done"], 0)


if __name__ == "__main__":
    unittest.main()
