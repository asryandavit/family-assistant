"""Nightly market watch run: pricing, the store fallback (§9) and alerts, offline on the
captured pages (tests/fixtures/market) in a temporary data folder."""
import os
import tempfile
import unittest
from datetime import date, timedelta

from jobs import market_watch as mw
from market import pricing, report, state, stores, tariffs

F = os.path.join(os.path.dirname(__file__), "fixtures", "market")
TODAY = date(2026, 10, 29)
UK = "https://www.amazon.co.uk/dp/B0B7RZBWLR"
DE = "https://www.amazon.de/dp/B0B7RZBWLR"
US = "https://www.amazon.com/dp/B07JW97H8Q"
VEGA = "https://vega.am/en/home-appliances/personal-care/hb-accessories/hb-accessories-philips-hx606487-for-tooth-care.html"
WB = "https://www.wildberries.ru/catalog/123456/detail.aspx"

with open(os.path.join(F, "cba_latest.xml"), encoding="utf-8") as _f:
    RATES = dict(tariffs.parse_cba(_f.read()), stale=False, note="")


def rates_get(root, today):
    return RATES


class Sender:
    def __init__(self):
        self.family, self.owner = [], []

    def send_family(self, cfg, text, silent=False, **kw):
        self.family.append((text, silent))

    def send_html(self, cfg, text, silent=False, **kw):
        self.owner.append((text, silent))


class Session:
    """Pages by URL; anything not listed -> the store's captured page (OfflineSession)."""

    def __init__(self, overrides=None):
        self.overrides = overrides or {}
        self.opened = []
        self.offline = mw.OfflineSession(stores.load())

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, url, wait_selector=None):
        self.opened.append(url)
        if url in self.overrides:
            name = self.overrides[url]
            with open(os.path.join(F, name), encoding="utf-8") as f:
                return {"status": "ok", "url": url, "final_url": url, "html": f.read(), "text": "", "detail": ""}
        return self.offline.read(url)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        items = []
        items.append(state.new_item(items, "Airfryer", [UK, DE], weight_kg=5.2, size_cm=[45, 35, 25]))
        items.append(state.new_item(items, "Bowls", [US]))
        items.append(state.new_item(items, "Brush heads", [VEGA]))
        items.append(state.new_item(items, "Boots", [WB], weight_kg=0.8))
        state.save_items(self.root, items)

    def tearDown(self):
        self.tmp.cleanup()

    def night(self, day=TODAY, session=None, send=True):
        self.sender = Sender()
        self.session = session or Session()
        return mw.run({}, day, lambda: self.session, root=self.root, send=send, write_sheet=False,
                      sender=self.sender, rates_get=rates_get, log=lambda m: None)


class FirstNight(Base):
    def test_report_and_state(self):
        out = self.night()
        text = out["text"]
        self.assertIn("<b>Airfryer</b> — best", text)
        self.assertIn("Amazon UK", text)
        self.assertIn("£131.99 + £28.74 to the warehouse", text)
        self.assertIn("Globbing air 6,000/kg · 7.9 kg → 47,400 (by volume)", text)   # 45×35×25/5000
        self.assertIn("16,900 ֏", text)
        self.assertIn("<b>Boots</b> — no price yet", text)
        self.assertIn("🚫 Wildberries blocked tonight — 1 item not re-read", text)
        self.assertIn("Rates CBA 28 Oct", text)
        # one report to both chats, silent; no alerts on a first night
        self.assertEqual(len(self.sender.family), 1)
        self.assertTrue(self.sender.family[0][1])
        self.assertEqual(out["alerts"], [])
        rt = state.load_runtime(self.root)
        self.assertEqual(rt["last"]["1|amazon_uk"]["price"], 131.99)
        self.assertEqual(rt["blocked"]["wildberries"]["nights"], 1)

    def test_weight_filled_from_page(self):
        self.night()
        bowls = state.load_items(self.root)[1]
        self.assertEqual(bowls["weight_kg"], 0.25)
        self.assertEqual(bowls["size_from"], "page (product)")

    def test_amazon_link_read_as_dp(self):
        self.night()
        self.assertIn("https://www.amazon.de/dp/B0B7RZBWLR", self.session.opened)

    def test_first_order_free_excluded_and_said(self):
        out = self.night()
        self.assertIn("store delivery unknown", out["text"])
        self.assertIn("free on a first order only", out["text"])


class Fallback(Base):
    def test_blocked_store_keeps_last_price_no_alert(self):
        rt = state.load_runtime(self.root)
        rt["last"]["4|wildberries"] = {"price": 9890, "currency": "RUB", "shipping": 0, "in_stock": False,
                                       "date_local": "2026-10-27", "source": "read", "delivery": None}
        rt["history"] = [{"date_local": "2026-10-28", "item_id": "4", "item": "Boots",
                          "best_total_amd": 99999, "store": "wildberries", "route": "x", "source": "read"}]
        state.save_runtime(self.root, rt)
        out = self.night()
        self.assertIn("⚠️ not re-read tonight (27 Oct)", out["text"])
        self.assertIn("1 item not re-read (1 on its last price)", out["text"])
        self.assertEqual(out["alerts"], [])                      # stale: no drop, no back-in-stock
        self.assertEqual(state.load_runtime(self.root)["last"]["4|wildberries"]["date_local"], "2026-10-27")

    def test_one_attempt_then_store_skipped(self):
        items = state.load_items(self.root)
        items.append(state.new_item(items, "Socks", ["https://www.wildberries.ru/catalog/999/detail.aspx"]))
        state.save_items(self.root, items)
        self.night()
        wb = [u for u in self.session.opened if "wildberries" in u]
        self.assertEqual(len(wb), 1)

    def test_owner_message_after_three_nights_once(self):
        for i in range(4):
            out = self.night(TODAY + timedelta(days=i))
            if i < 2:
                self.assertEqual(out["owner_msgs"], [], i)
            elif i == 2:
                self.assertEqual(len(out["owner_msgs"]), 1)
                self.assertIn("3 nights in a row", out["owner_msgs"][0])
                self.assertIn("/watch price", out["owner_msgs"][0])
                self.assertEqual(len(self.sender.owner), 1)
            else:
                self.assertEqual(out["owner_msgs"], [])

    def test_owner_price_used_and_marked(self):
        state.set_owner_price(self.root, "4", "wildberries", 9890, "RUB", TODAY)
        out = self.night()
        self.assertIn("9,890 ₽", out["text"])
        self.assertIn("owner, 29 Oct", out["text"])
        self.assertNotIn("<b>Boots</b> — no price yet", out["text"])

    def test_gone_product(self):
        s = Session({"https://www.amazon.com/dp/B07JW97H8Q": "amazon_us_notfound.html"})
        out = self.night(session=s)
        self.assertIn("product page gone", out["text"])


class Alerts(Base):
    def test_drop_alert_with_sound(self):
        rt = state.load_runtime(self.root)
        rt["history"] = [{"date_local": "2026-10-28", "item_id": "3", "item": "Brush heads",
                          "best_total_amd": 20000, "store": "vega", "route": "in Yerevan", "source": "read"}]
        state.save_runtime(self.root, rt)
        out = self.night()
        self.assertEqual(len(out["alerts"]), 1)
        self.assertIn("dropped 16%", out["alerts"][0])            # 16,900 vs 20,000
        self.assertFalse(self.sender.family[1][1])                 # with sound
        self.assertIn("📉 -16% vs yesterday", out["text"])

    def test_small_drop_no_alert(self):
        rt = state.load_runtime(self.root)
        rt["history"] = [{"date_local": "2026-10-28", "item_id": "3", "item": "Brush heads",
                          "best_total_amd": 17500, "store": "vega", "route": "in Yerevan", "source": "read"}]
        state.save_runtime(self.root, rt)
        self.assertEqual(self.night()["alerts"], [])

    def test_back_in_stock(self):
        rt = state.load_runtime(self.root)
        rt["last"]["3|vega"] = {"price": 16900, "currency": "AMD", "shipping": 0, "in_stock": False,
                                "date_local": "2026-10-28", "source": "read", "delivery": None}
        state.save_runtime(self.root, rt)
        out = self.night()
        self.assertEqual(len(out["alerts"]), 1)
        self.assertIn("back in stock", out["alerts"][0])

    def test_notify_before_persist(self):
        class Boom(Sender):
            def send_family(self, cfg, text, silent=False, **kw):
                raise RuntimeError("telegram down")
        with self.assertRaises(RuntimeError):
            mw.run({}, TODAY, lambda: Session(), root=self.root, send=True, write_sheet=False,
                   sender=Boom(), rates_get=rates_get, log=lambda m: None)
        self.assertEqual(state.load_runtime(self.root)["last"], {})


class PricingUnits(unittest.TestCase):
    ROUTES = (tariffs.parse_onex(open(os.path.join(F, "onex_tariff_en.json"), encoding="utf-8").read())
              + tariffs.parse_buyforyou(open(os.path.join(F, "buyforyou_home_hy.html"), encoding="utf-8").read()))
    US_STORE = stores.load()["amazon_us"]

    def offer(self, price=79.99, shipping=0.0):
        return {"price": price, "currency": "USD", "shipping": shipping, "delivery": None}

    def test_brief_example(self):
        item = {"qty": 1, "weight_kg": 2.4}
        q = pricing.quote(item, self.US_STORE, self.offer(), self.ROUTES, RATES, TODAY)
        onex_air = next(ln for ln in q["lines"] if ln["forwarder"] == "onex" and ln["mode"] == "air")
        bfy_air = next(ln for ln in q["lines"] if ln["forwarder"] == "buyforyou" and ln["mode"] == "air")
        self.assertEqual(onex_air["ship_amd"], 14400)
        self.assertEqual(bfy_air["ship_amd"], 9900)
        self.assertAlmostEqual(onex_air["total_amd"], 79.99 * 360.51 + 14400, places=2)
        self.assertEqual(onex_air["customs_amd"], 0)

    def test_customs_over_200_eur(self):
        item = {"qty": 1, "weight_kg": 2.4}
        q = pricing.quote(item, self.US_STORE, self.offer(price=400), self.ROUTES, RATES, TODAY)
        onex_air = next(ln for ln in q["lines"] if ln["forwarder"] == "onex" and ln["mode"] == "air")
        value_eur = 400 * 360.51 / 400.96
        self.assertAlmostEqual(onex_air["customs_amd"], (value_eur - 200) * 0.15 * 400.96, places=2)
        bfy = next(ln for ln in q["lines"] if ln["forwarder"] == "buyforyou" and ln["mode"] == "air")
        self.assertAlmostEqual(bfy["customs_amd"], (value_eur - 200) * 0.162 * 400.96, places=2)

    def test_qty_and_no_weight(self):
        q = pricing.quote({"qty": 2}, self.US_STORE, self.offer(), self.ROUTES, RATES, TODAY)
        self.assertIn("weight needed", q["notes"])
        self.assertTrue(all(ln["total_amd"] is None for ln in q["lines"]))
        self.assertAlmostEqual(q["price_amd"], 2 * 79.99 * 360.51, places=2)

    def test_unknown_rate_gives_no_amd(self):
        q = pricing.quote({"qty": 1, "weight_kg": 1}, self.US_STORE, self.offer(), self.ROUTES, None, TODAY)
        self.assertIsNone(q["base_amd"])
        self.assertIn("USD rate unavailable", q["notes"])

    def test_report_money(self):
        self.assertEqual(report.money(79.99, "USD"), "$79.99")
        self.assertEqual(report.money(80.0, "EUR"), "€80")
        self.assertEqual(report.money(9890, "RUB"), "9,890 ₽")


if __name__ == "__main__":
    unittest.main()
