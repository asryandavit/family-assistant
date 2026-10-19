"""Basket output: Telegram message layout and length, Shopping-list Sheet rows
(incl. the App column), the Sheet's checkbox requests, and the job's delivery to
both chats. Offline: real captured results, Telegram/Sheets replaced by recorders."""
import json
import os
import unittest
from datetime import datetime
from unittest import mock

from jobs import grocery_basket as gb
from lib import basket as bk
from lib import config, fmt_basket, sheets, sheets_checklist, telegram, ui
from tests.test_basket import ROWS, WORDS, priced

WHEN = datetime(2026, 10, 19, 14, 5, tzinfo=ui.YEREVAN)
BUDGET = (80000, 100000)
FIX = os.path.join(os.path.dirname(__file__), "fixtures", "grocery", "basket")
OWNER, KARINE = "111", "222"


def both():
    w, m = priced("weekly"), priced("monthly")
    return w, m, {"weekly": w["totals"]["all"], "monthly": m["totals"]["all"]}


class Message(unittest.TestCase):
    def test_layout_and_one_message(self):
        w, m, totals = both()
        msg = fmt_basket.build("weekly", w, WHEN, BUDGET, totals)
        self.assertTrue(msg.startswith("\U0001f9fa <b>Basket</b> · <i>weekly</i>"))
        self.assertLessEqual(len(msg), fmt_basket.MAX_CHARS)
        self.assertEqual(len(telegram._split(msg)), 1)
        above = msg.split("<blockquote")[0]
        self.assertIn("Total 15,521 ֏", above)
        self.assertIn("112,453 ֏", above)                     # month = 15,521 x 52/12 + 45,195
        self.assertIn("12,453 ֏ over", above)
        self.assertIn("22 items at both shops", above)
        # one fold per shop, Yerevan City first, then "Not priced"
        folds = msg.split("<blockquote expandable>")[1:]
        self.assertTrue(folds[0].startswith("<b>\U0001f534 Yerevan City"))
        self.assertTrue(folds[1].startswith("<b>\U0001f7e2 Parma"))
        self.assertIn("Scoolinary", folds[2])
        self.assertEqual(msg.count("<blockquote"), msg.count("</blockquote>"))
        # every Yerevan City line has its 📱 app link; Parma lines have none
        yc_lines = [ln for ln in folds[0].splitlines() if ln.startswith("•")]
        self.assertTrue(yc_lines and all("/shop/product-detail/" in ln for ln in yc_lines))
        self.assertNotIn("product-detail/", folds[1])

    def test_monthly_alone_and_weekly_alone(self):
        w, m, _ = both()
        msg = fmt_basket.build("monthly", m, WHEN, BUDGET, {"monthly": m["totals"]["all"]})
        self.assertIn("Staples <b>45,195 ֏</b>/month", msg)
        self.assertIn("Spices — skipped — as needed", msg)
        msg = fmt_basket.build("weekly", w, WHEN, BUDGET, {"weekly": w["totals"]["all"]})
        self.assertIn("Fresh ≈ <b>67,258 ֏</b>/month", msg)
        self.assertLess(len(msg), 4096)

    def test_long_names_shrink_before_splitting(self):
        w, _, totals = both()
        full = fmt_basket._build("weekly", w, WHEN, BUDGET, totals, 60)
        self.assertGreater(len(full), fmt_basket.MAX_CHARS)
        self.assertIn('Eggs "Arzni"', full)
        short = fmt_basket.build("weekly", w, WHEN, BUDGET, totals)
        self.assertNotIn('Eggs "Arzni"', short)                # product names left to the Sheet
        self.assertIn(">Eggs</a> 3 × 6 pcs · 1,440", short)

    def test_partial_warning(self):
        rows = [r for r in ROWS if r["item"] in ("Apples", "Pears")]
        rows.append(dict(rows[0], item="Dragonfruit", match=["dragonfruit"]))
        b = bk.price_basket(rows, {"apples": _fixture("apples"), "pears": _fixture("pears")}, WORDS)
        msg = fmt_basket.build("weekly", b, WHEN, BUDGET, {"weekly": b["totals"]["all"]})
        self.assertIn("⚠️ <b>Partial:</b> 1 item not priced, not in the total — Dragonfruit", msg)
        self.assertIn("Dragonfruit — no match at either shop", msg)


def _fixture(slug):
    with open(os.path.join(FIX, slug + ".json"), encoding="utf-8") as f:
        return json.load(f)


class SheetRows(unittest.TestCase):
    def setUp(self):
        w, m, totals = both()
        self.rows, self.boxes, self.bold = fmt_basket.sheet_rows("weekly", w, WHEN, BUDGET, totals)
        self.b = w

    def test_header_and_budget(self):
        self.assertIn("This week — priced Mon 19 Oct 14:05", self.rows[0][0])
        self.assertIn("112,453 ֏", self.rows[1][0])
        self.assertIn("12,453 ֏ OVER budget", self.rows[1][0])
        self.assertEqual(self.rows[3], fmt_basket.HEADER)
        self.assertIn(0, self.bold)
        self.assertIn(3, self.bold)

    def test_item_rows_have_checkboxes_links_and_costs(self):
        items = [self.rows[i] for i in self.boxes]
        self.assertEqual(len(items), 24)                       # 23 priced + Scoolinary (skipped)
        self.assertTrue(all(r[0] is False for r in items))
        priced_rows = [r for r in items if r[3]]
        self.assertEqual(sum(r[7] for r in priced_rows), self.b["totals"]["all"])
        for r in priced_rows:
            self.assertTrue(r[4].startswith('=HYPERLINK("https://'))
            if r[3] == "Yerevan City":
                self.assertTrue(r[5].startswith('=HYPERLINK("https://yerevan-city.am/shop/product-detail/'))
                self.assertTrue(r[5].endswith(',"\U0001f4f1")'))
            else:
                self.assertEqual(r[5], "")
        eggs = next(r for r in items if r[1] == "Eggs")
        self.assertEqual(eggs[2:4], ["3 × 6 pcs", "Yerevan City"])
        self.assertIn('Eggs ""Arzni"" havkirt', eggs[4])         # quotes doubled inside the formula
        garlic = next(r for r in items if r[1] == "Garlic")
        self.assertEqual(garlic[6], "1,185 ֏/kg")

    def test_groups_totals_and_not_priced(self):
        labels = [r[1] for r in self.rows if len(r) > 1]
        self.assertLess(labels.index("\U0001f534 Yerevan City"), labels.index("\U0001f7e2 Parma"))
        total = next(r for r in self.rows if len(r) > 1 and r[1] == "Total")
        self.assertEqual(total[7], self.b["totals"]["all"])
        yc_total = next(r for r in self.rows if len(r) > 1 and r[1] == "Yerevan City total")
        self.assertEqual(yc_total[7], self.b["totals"]["yc"])
        i = next(n for n, r in enumerate(self.rows) if r[1:2] == ["Not priced (not in the total)"])
        self.assertEqual(self.rows[i + 1][1], "Scoolinary project ingredients")
        self.assertNotIn(i, self.boxes)
        self.assertIn(i + 1, self.boxes)
        self.assertIn(i, self.bold)

    def test_link_escaping(self):
        self.assertEqual(sheets_checklist.link("https://a/b", 'Oil "C"'),
                         '=HYPERLINK("https://a/b","Oil ""C""")')


class ChecklistRequests(unittest.TestCase):
    def test_clear_then_checkboxes_bold_and_money(self):
        ws = mock.Mock(id=7)
        reqs = sheets_checklist.requests_for(ws, 10, 8, checkbox_rows=[4, 5], bold_rows=[0],
                                             money_cols=[7])
        self.assertEqual(reqs[0]["repeatCell"]["fields"], "userEnteredFormat")
        self.assertNotIn("rule", reqs[1]["setDataValidation"])         # old boxes removed first
        boxes = [r["setDataValidation"] for r in reqs[2:] if "setDataValidation" in r]
        self.assertEqual([b["range"]["startRowIndex"] for b in boxes], [4, 5])
        self.assertTrue(all(b["rule"]["condition"]["type"] == "BOOLEAN" for b in boxes))
        self.assertTrue(all(b["range"]["startColumnIndex"] == 0 and b["range"]["endColumnIndex"] == 1
                            for b in boxes))
        self.assertTrue(any(r.get("repeatCell", {}).get("fields") == "userEnteredFormat.numberFormat"
                            for r in reqs))


class Job(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load()
        self.posts, self.writes = [], []
        self._post, self._log = telegram._post, sheets.log_run
        telegram._post = lambda tok, payload: self.posts.append(payload)
        sheets.log_run = lambda *a, **k: None
        env = {k: v for k, v in os.environ.items() if k != telegram.REPLY_CHAT_ENV}
        env.update({"TELEGRAM_BOT_TOKEN": "x", "TELEGRAM_CHAT_ID": OWNER, "TELEGRAM_CHAT_ID_2": KARINE})
        self.env = mock.patch.dict(os.environ, env, clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        telegram._post, sheets.log_run = self._post, self._log

    def _run(self, **kw):
        kw.setdefault("writer", lambda *a: self.writes.append(a))
        return gb.run(self.cfg, ("weekly",), fixtures=FIX, now=WHEN, **kw)

    def test_result_goes_to_both_chats_silently_with_checklist_button(self):
        self._run(send=True)
        self.assertEqual([p["chat_id"] for p in self.posts], [OWNER, KARINE])
        for p in self.posts:
            self.assertTrue(p["disable_notification"])
            kb = json.loads(p["reply_markup"])["inline_keyboard"]
            self.assertEqual(kb[0][0]["text"], "\U0001f4cb Open checklist")
            self.assertTrue(kb[0][0]["url"].startswith("https://docs.google.com/spreadsheets/d/"))

    def test_sheet_written_after_sending(self):
        order = []
        telegram._post = lambda tok, payload: order.append("tg")
        self._run(send=True, writer=lambda *a: order.append("sheet:" + a[2]))
        self.assertEqual(order, ["tg", "tg", "sheet:This week"])

    def test_sheet_failure_tells_the_owner_only(self):
        def boom(*a):
            raise RuntimeError("quota")
        out = self._run(send=False, writer=boom)
        self.assertEqual(out["sheet_errors"], ["This week: quota"])
        self.assertEqual([p["chat_id"] for p in self.posts], [OWNER])
        self.assertIn("checklist not updated", self.posts[0]["text"])

    def test_one_search_per_distinct_text_with_pauses(self):
        calls, sleeps = [], []
        fake = lambda q: calls.append(q) or {"items": [], "status": {"yc": "ok", "parma": "ok"}}  # noqa: E731
        qs = gb.searches_for([r for r in ROWS if r["list"] == "monthly"])
        gb.fetch(qs, fake, sleep=sleeps.append)
        self.assertEqual(calls, qs)
        self.assertEqual(qs.count("lentils"), 1)                 # red + brown lentils share it
        self.assertEqual(sleeps, [gb.PAUSE] * (len(qs) - 1))


if __name__ == "__main__":
    unittest.main()
