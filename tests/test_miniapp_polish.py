"""Mini App improvement pass, stage A (decision 105): the server-side parts.

Travel says how old its data is (the page must not do date arithmetic); the China view sends the
sort orders ready-made so the page only re-orders cards (review §14.4: numbers are code)."""
import json
import os
import unittest
from datetime import date
from unittest import mock

from china import pricing, report, search
from miniapp import china_view, screens

F = os.path.join(os.path.dirname(__file__), "fixtures", "miniapp")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fixture(name):
    with open(os.path.join(F, name), encoding="utf-8") as f:
        return json.load(f)


def current():
    last = fixture("china_last.json")
    allp = [p for s in last["sites"] for p in s.get("ranked") or []]
    pricing.apply_trust(allp, last.get("category") or "other", search.load_cfg(ROOT).get("brands"))
    return last


class TravelAge(unittest.TestCase):
    def view(self, today):
        rows = fixture("travel_rows.json")
        with mock.patch("lib.tasks.query", return_value={"exists": False}):
            return screens.travel_view({}, rows_fn=lambda tab: rows[tab], today=today)

    def test_fresh_data_has_no_note(self):
        v = self.view(date(2026, 11, 10))
        self.assertEqual(v["run_date"], "2026-11-10")
        self.assertIsNone(v["trips_note"])

    def test_old_data_says_how_old_in_words(self):
        v = self.view(date(2026, 11, 15))
        self.assertEqual(v["trips_note"], "5 days old — Scan now for fresh prices")
        self.assertEqual(v["stays_note"], "15 days old — Search stays for fresh prices")

    def test_yesterday_is_not_stale(self):
        self.assertIsNone(self.view(date(2026, 11, 11))["trips_note"])
        self.assertIsNone(self.view(date(2026, 11, 12))["trips_note"])
        self.assertIsNotNone(self.view(date(2026, 11, 13))["trips_note"])      # 3 days

    def test_one_day_old_wording(self):
        self.assertEqual(screens.age_note(date(2026, 11, 9), date(2026, 11, 14), "Scan now").split(" ")[0], "5")
        self.assertTrue(screens.age_note(date(2026, 11, 13), date(2026, 11, 14), "x") is None)

    def test_bad_date_is_no_note(self):
        self.assertIsNone(screens.age_note(None, date(2026, 11, 14), "x"))


class ChinaOrders(unittest.TestCase):
    def test_orders_are_permutations_of_the_numbers(self):
        v = china_view.view(current())
        n = [r["n"] for r in v["results"]]
        for k in ("trust", "delivered"):
            self.assertEqual(sorted(v["orders"][k]), sorted(n), k)

    def test_delivered_is_cheapest_first_unpriced_last(self):
        last = current()
        last["sites"][0]["ranked"][1]["total_amd"] = None                 # one unpriced result
        v = china_view.view(last)
        totals = {n: p.get("total_amd") for n, p in report.numbered(last["sites"])}
        order = v["orders"]["delivered"]
        priced = [totals[n] for n in order if totals[n] is not None]
        self.assertEqual(priced, sorted(priced))
        self.assertIsNone(totals[order[-1]])
        self.assertEqual(order[-1], v["orders"]["trust"][-1])             # both end with the unpriced

    def test_trust_order_is_the_chats_ranking_across_sites(self):
        last = current()
        v = china_view.view(last)
        by_n = dict(report.numbered(last["sites"]))
        keys = [pricing.order_key(by_n[n]) for n in v["orders"]["trust"]]
        self.assertEqual(keys, sorted(keys))

    def test_old_results_without_trust_still_get_orders(self):
        v = china_view.view(fixture("china_last.json"))
        self.assertEqual(len(v["orders"]["trust"]), len(v["results"]))

    def test_empty_has_no_orders(self):
        self.assertEqual(china_view.view(None), {"empty": True})


if __name__ == "__main__":
    unittest.main()
