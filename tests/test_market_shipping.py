"""Market watch maths against the forwarders' own calculators (tests/fixtures/market/).

Oracles: onex_calculator.json (Onex's calculator API, P0), globbing_calculator.json and
buyforyou_calculator.json (their own JS run by oracle_calculators.js), easytrans_calculator.json
(its calculate-price API). Every answer in every file is checked, not a sample.
"""
import json
import os
import unittest
from datetime import date

from market import customs, shipping, tariffs, workdays

F = os.path.join(os.path.dirname(__file__), "fixtures", "market")


def read(name):
    with open(os.path.join(F, name), encoding="utf-8") as f:
        return f.read()


ONEX = tariffs.parse_onex(read("onex_tariff_en.json"))
GLOBBING = tariffs.parse_globbing(read("globbing_home_en.html"))
BUYFORYOU = tariffs.parse_buyforyou(read("buyforyou_home_hy.html"))
EASYTRANS = tariffs.parse_easytrans(read("easytrans_address_all-available-simple.json"))
CALC_ORIGIN = {"usa": "usa", "russia": "russia", "uk": "uk", "germany": "germany",
               "china": "china", "uae": "uae", "greece": "greece", "italy": "italy",
               "spain": "spain", "poland": "poland"}
CALC_MODE = {"air": "air", "sea": "sea", "ground": "truck"}


def find(routes, origin, mode):
    return next((r for r in routes if r["origin"] == origin and r["mode"] == mode), None)


class OnexCalculator(unittest.TestCase):
    def test_every_answer(self):
        answers = json.loads(read("onex_calculator.json"))
        self.assertEqual(len(answers), 90)
        ok = 0
        for key, ans in answers.items():
            country, mode, kg = key.split("|")
            route = find(ONEX, CALC_ORIGIN[country], CALC_MODE[mode])
            with self.subTest(key=key):
                if ans["status"] != 1:
                    self.assertIsNone(route, "calculator refuses this route")
                    continue
                ok += 1
                data = ans["data"]
                q = shipping.quote(route, float(kg))
                chosen = data["tariffs"][data["current_tariff"]]
                self.assertEqual(q["band"], data["current_tariff"])
                self.assertEqual(q["cost_amd"], chosen["cost"])
                self.assertAlmostEqual(q["chargeable_kg"], chosen["weight"])
                for name, t in data["tariffs"].items():
                    self.assertEqual(shipping.onex_band(route, name, float(kg))["cost_amd"],
                                     t["cost"], name)
        self.assertEqual(ok, 75)

    def test_band_edge(self):
        usa = find(ONEX, "usa", "air")
        self.assertEqual(shipping.quote(usa, 1.0)["cost_amd"], 4900)      # ≤1 kg mini
        self.assertEqual(shipping.quote(usa, 1.05)["cost_amd"], 6600)     # 1.1 kg standard

    def test_volume_only_on_sea(self):
        # Onex rules page: sea = max(actual, L×W×H/5000); air/ground = actual weight only
        sea, air = find(ONEX, "usa", "sea"), find(ONEX, "usa", "air")
        self.assertTrue(sea["volume"])
        self.assertFalse(air["volume"])
        q = shipping.quote(sea, 2.4, (60, 40, 30))           # 14.4 kg volume
        self.assertEqual(q["chargeable_kg"], 14.4)
        self.assertEqual(q["cost_amd"], 150 * 144)
        self.assertEqual(shipping.quote(air, 2.4, (60, 40, 30))["cost_amd"], 14400)


class GlobbingCalculator(unittest.TestCase):
    def test_every_answer(self):
        answers = json.loads(read("globbing_calculator.json"))["answers"]
        self.assertEqual(len(answers), 600)
        by_id = {r["condition_id"]: r for r in GLOBBING}
        eur = by_id[44]["site_eur_rate"]                   # 408 AMD per € on that page
        for key, ans in answers.items():
            route = by_id[ans["condition_id"]]
            inp = ans["input"]
            dims = (inp["l"], inp["w"], inp["h"]) if inp["l"] else None
            with self.subTest(key=key):
                q = shipping.quote(route, inp["weight"], dims)
                self.assertAlmostEqual(q["cost_amd"], ans["shipping"], places=2)
                c = customs.default_rule(inp["price"] / eur, inp["weight"], route["customs"]) * eur
                self.assertAlmostEqual(c, ans["customs"], delta=0.02)

    def test_tolerance_rounding(self):
        uk = find(GLOBBING, "uk", "air")
        self.assertEqual(shipping.quote(uk, 1.005)["cost_amd"], 6000)   # 5 g < 7 g: down
        self.assertEqual(shipping.quote(uk, 1.008)["cost_amd"], 6600)   # 8 g: up to 1.1 kg

    def test_air_compares_volume(self):
        uk = find(GLOBBING, "uk", "air")
        self.assertEqual(shipping.quote(uk, 2.4, (60, 40, 30))["cost_amd"], 86400)
        self.assertEqual(shipping.quote(find(GLOBBING, "germany", "air"), 2.4,
                                        (60, 40, 30))["cost_amd"], 14400)

    def test_russia_has_no_customs(self):
        self.assertEqual(find(GLOBBING, "russia", "air")["customs"]["combine"], "none")


class BuyForYouCalculator(unittest.TestCase):
    # the page's own fallback rates (EUR base) used when its rate fetch fails
    EUR_BASE = {"AMD": 428.15618417, "USD": 1.16343548, "Yuan": 7.89449673}

    def test_every_answer(self):
        answers = json.loads(read("buyforyou_calculator.json"))["answers"]
        self.assertEqual(len(answers), 140)
        for key, ans in answers.items():
            inp = ans["input"]
            origin = inp["country"].lower()
            route = find(BUYFORYOU, origin, inp["method"])
            with self.subTest(key=key):
                if inp["method"] == "sea" and origin == "china":
                    self.assertIsNone(route)   # the page hides sea for China
                    continue
                q = shipping.quote(route, inp["weight"], tuple(inp["dims"]) if inp["dims"] else None)
                self.assertEqual(q["cost_amd"], ans["shipping"])
                per_eur = 1.0 if inp["currency"] == "AMD" else self.EUR_BASE[inp["currency"]]
                value_eur = inp["price"] / (self.EUR_BASE["AMD"] if inp["currency"] == "AMD" else per_eur)
                c = customs.default_rule(value_eur, inp["weight"], route["customs"]) * self.EUR_BASE["AMD"]
                self.assertAlmostEqual(c, ans["customs"], delta=0.5)

    def test_constants(self):
        usa = find(BUYFORYOU, "usa", "air")
        self.assertEqual((usa["rate"], usa["min_cost"], usa["divisor"], usa["side_over_cm"]),
                         (4100, 1400, 6000, 60))
        self.assertEqual(usa["customs"]["pct"], 16.2)
        self.assertEqual(shipping.quote(usa, 2.4)["cost_amd"], 9900)     # brief's example line


class EasyTransCalculator(unittest.TestCase):
    def test_every_answer(self):
        answers = json.loads(read("easytrans_calculator.json"))["answers"]
        self.assertEqual(len(answers), 16)
        by_ids = {(r["country_id"], r["method_id"]): r for r in EASYTRANS}
        for key, ans in answers.items():
            c, m, kg, dims = key.split("|")
            route = by_ids[(int(c), int(m))]
            d = tuple(int(x) for x in dims.split("x")) if dims else None
            with self.subTest(key=key):
                self.assertTrue(ans["isSuccess"])
                self.assertEqual(shipping.quote(route, float(kg), d)["cost_amd"],
                                 ans["data"]["weightPrice"])


class Quote(unittest.TestCase):
    def test_no_weight_is_no_quote(self):
        self.assertIsNone(shipping.quote(find(ONEX, "usa", "air"), None))
        self.assertEqual(shipping.per_kg(find(ONEX, "usa", "air")), 6000)
        self.assertEqual(shipping.per_kg(find(GLOBBING, "usa", "sea")), 1500)

    def test_rejects_zero(self):
        with self.assertRaises(ValueError):
            shipping.quote(find(ONEX, "usa", "air"), 0)


class Customs(unittest.TestCase):
    ONEX_RULE = tariffs.CUSTOMS_ONEX

    def test_under_limit_free(self):
        self.assertEqual(customs.default_rule(199.99, 5, self.ONEX_RULE), 0)
        self.assertEqual(customs.default_rule(200, 31, self.ONEX_RULE), 0)

    def test_over_value(self):
        self.assertAlmostEqual(customs.default_rule(300, 2, self.ONEX_RULE), 15.0)

    def test_over_weight_onex(self):
        # FAQ point 3: 15% of the whole value + €2 per kg over 31
        self.assertAlmostEqual(customs.default_rule(100, 33, self.ONEX_RULE), 15 + 4)

    def test_globbing_takes_the_larger(self):
        rule = find(GLOBBING, "uk", "air")["customs"]
        self.assertAlmostEqual(customs.default_rule(300, 35, rule), 15.0)    # 15 vs 10
        self.assertAlmostEqual(customs.default_rule(210, 35, rule), 10.0)    # 1.5 vs 10

    def test_eaeu_switch(self):
        self.assertAlmostEqual(customs.eaeu_2026(100, 2), 5.0)
        self.assertAlmostEqual(customs.eaeu_2026(100, 10), 10.0)              # €1/kg floor
        self.assertAlmostEqual(customs.eaeu_2026(300, 2), 15 + 20)
        self.assertEqual(customs.estimate(100, 2, which="eaeu_2026")["rule"], "eaeu_2026")

    def test_near_limit_flag(self):
        self.assertTrue(customs.estimate(185, 1)["near_limit"])
        self.assertTrue(customs.estimate(215, 1)["near_limit"])
        self.assertFalse(customs.estimate(150, 1)["near_limit"])
        self.assertIsNone(customs.estimate(None, 1))


class WorkingDays(unittest.TestCase):
    HOL = workdays.load_holidays()

    def test_holidays_file(self):
        self.assertIn(date(2026, 12, 31), self.HOL)
        self.assertIn(date(2027, 1, 6), self.HOL)

    def test_skips_weekend(self):
        # Fri 30 Oct 2026 + 1 working day = Mon 2 Nov
        self.assertEqual(workdays.add_working_days(date(2026, 10, 30), 1, self.HOL), date(2026, 11, 2))

    def test_holiday_inside_range(self):
        # Wed 30 Dec + 3 wd: Thu 31 (holiday), Fri 1 (holiday), Mon 4, Tue 5, Wed 6 (holiday) -> Thu 7
        self.assertEqual(workdays.add_working_days(date(2026, 12, 30), 3, self.HOL), date(2027, 1, 7))

    def test_month_end(self):
        self.assertEqual(workdays.add_working_days(date(2026, 11, 27), 5, self.HOL), date(2026, 12, 4))

    def test_calendar_and_months(self):
        self.assertEqual(workdays.add_days(date(2026, 10, 30), 10, "calendar"), date(2026, 11, 9))
        self.assertEqual(workdays.add_days(date(2026, 10, 30), 3.5, "months"), date(2027, 2, 14))

    def test_arrival_from_store_date(self):
        days = {"min": 5, "max": 10, "unit": "working", "from": "arrival"}
        a = workdays.arrival(date(2026, 10, 30), days, store_arrival=date(2026, 11, 3), hol=self.HOL)
        self.assertEqual((a["earliest"], a["latest"]), (date(2026, 11, 10), date(2026, 11, 17)))
        self.assertEqual(a["notes"], [])
        self.assertEqual(workdays.date_text(a), "~Tue 10 – Tue 17 Nov")

    def test_arrival_unknowns_are_said(self):
        days = {"min": 35, "max": 35, "unit": "working", "from": "dispatch", "up_to": True}
        a = workdays.arrival(date(2026, 10, 30), days, hol=self.HOL)
        self.assertEqual(a["notes"], ["store time unknown", "after dispatch"])
        self.assertEqual(workdays.range_text(days), "≤35 wd")
        self.assertIsNone(workdays.arrival(date(2026, 10, 30), None))

    def test_range_text(self):
        self.assertEqual(workdays.range_text({"min": 5, "max": 10, "unit": "working"}), "5–10 wd")
        self.assertEqual(workdays.range_text({"min": 3.5, "max": 3.5, "unit": "months"}), "~3.5 months")
        self.assertEqual(workdays.range_text(None), "time not published")


class Cba(unittest.TestCase):
    def test_rates(self):
        r = tariffs.parse_cba(read("cba_latest.xml"))
        self.assertEqual(r["date"], "2026-10-28")
        self.assertEqual(r["amd_per"]["USD"], 360.51)
        self.assertAlmostEqual(r["amd_per"]["IRR"], 0.019377 / 100)    # rate ÷ Amount

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            tariffs.parse_cba('<a xmlns="http://www.cba.am/"></a>')


if __name__ == "__main__":
    unittest.main()
