"""Weekly tariff refresh: parses the captured sources, keeps last week's routes on failure,
reports changes (jobs/market_tariffs.py)."""
import copy
import os
import unittest

from jobs import market_tariffs as job
from market import tariffs

F = os.path.join(os.path.dirname(__file__), "fixtures", "market")


def from_fixtures(name, url, fixture):
    with open(os.path.join(F, fixture), encoding="utf-8") as f:
        return f.read()


class Refresh(unittest.TestCase):
    def setUp(self):
        self.table, self.rep = job.refresh({"routes": []}, from_fixtures, when="2026-10-29T10:00:00+00:00")

    def test_all_sources(self):
        s = self.table["sources"]
        self.assertTrue(all(v["ok"] for v in s.values()))
        self.assertEqual({k: v["routes"] for k, v in s.items()},
                         {"onex": 15, "globbing": 15, "buyforyou": 3, "easytrans": 2})
        self.assertTrue(self.rep["first"])

    def test_failed_source_keeps_last_week(self):
        def broken(name, url, fixture):
            if name == "globbing":
                raise OSError("timeout")
            return from_fixtures(name, url, fixture)
        table, rep = job.refresh(self.table, broken, when="2026-11-01T10:00:00+00:00")
        g = [r for r in table["routes"] if r["forwarder"] == "globbing"]
        self.assertEqual(len(g), 15)
        self.assertEqual(g[0]["read_utc"], "2026-10-29T10:00:00+00:00")
        self.assertFalse(table["sources"]["globbing"]["ok"])
        self.assertEqual(rep["failed"][0][0], "globbing")
        self.assertIn("keeping the tariffs read 2026-10-29", job.report_text(table, rep))

    def test_parse_garbage_is_a_failure_not_empty(self):
        def garbage(name, url, fixture):
            return "<html>maintenance</html>" if name == "buyforyou" else from_fixtures(name, url, fixture)
        table, rep = job.refresh(self.table, garbage)
        self.assertEqual(table["sources"]["buyforyou"]["routes"], 3)
        self.assertEqual([f[0] for f in rep["failed"]], ["buyforyou"])

    def test_changes_reported(self):
        old = copy.deepcopy(self.table)
        usa = next(r for r in old["routes"] if tariffs.route_key(r) == "globbing|usa|air")
        usa["price_per_kg"] = 5500
        old["routes"] = [r for r in old["routes"] if tariffs.route_key(r) != "easytrans|poland|air"]
        table, rep = job.refresh(old, from_fixtures)
        self.assertIn("globbing usa air: price_per_kg changed", rep["changes"])
        self.assertIn("new route easytrans poland air", rep["changes"])
        self.assertIn("Changed since last week", job.report_text(table, rep))

    def test_no_change(self):
        table, rep = job.refresh(self.table, from_fixtures)
        self.assertEqual(rep["changes"], [])
        self.assertIn("No change since last week.", job.report_text(table, rep))


if __name__ == "__main__":
    unittest.main()
