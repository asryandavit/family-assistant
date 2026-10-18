"""Travel messages (lib/fmt.py) in the docs/TELEGRAM_UX.md template: the same
content as before (city labels, prices, links), with long parts folded."""
import unittest

from lib import config, fmt


def _trip(i, kind="return"):
    t = {"id": "T%06d" % i, "kind": kind, "out_date": "2026-11-%02d" % (3 + i),
         "back_date": "2026-11-%02d" % (10 + i), "nights": 7, "pax": "2A",
         "total": 400 + 10 * i, "wdc": "-", "currency": "USD"}
    if kind == "return":
        t.update(route="BUD", out_city="BUD", in_city="BUD")
    else:
        t.update(route="FCO>NAP", out_city="FCO", in_city="NAP")
    return t


class Alert(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load()

    def test_content_kept_and_trips_folded(self):
        drops = [{"o": "EVN", "d": "FCO", "month": "2026-11", "prev": 60, "now": 45,
                  "pct": -25, "atl": True}]
        new_routes = [{"o": "NAP", "d": "EVN", "month": "2026-12", "price": 39}]
        trip_drops = [dict(_trip(0, "openjaw"), prev_total=600)]
        trip_new = [_trip(i) for i in range(1, 6)]
        m = fmt.build_alert(self.cfg, drops, new_routes, trip_new, trip_drops, "Rome keeps dropping.")
        self.assertTrue(m.startswith("✈️ <b>Travel deals</b>"))
        above, _, folded = m.partition("<blockquote expandable>")
        self.assertIn("Rome (FCO)", above)
        self.assertIn("all-time low", above)
        self.assertIn("Naples (NAP)</b> ←", above)
        self.assertIn("was $600", above)
        self.assertIn("Rome keeps dropping.", above)
        self.assertEqual(above.count("<code>T"), 3)          # 3 trips visible
        self.assertIn("3 more trips", folded)
        self.assertEqual(folded.count("<code>T"), 3)          # the other 3 folded
        self.assertIn("docs.google.com/spreadsheets", m)
        self.assertLess(len(m), 4096)

    def test_few_trips_no_fold(self):
        m = fmt.build_alert(self.cfg, [], [], [_trip(1)], [], "")
        self.assertNotIn("blockquote", m)


class Digest(unittest.TestCase):
    def test_trips_visible_legs_folded(self):
        cfg = config.load()
        legs = [{"origin": "EVN", "destination": "BUD", "out_date": "2026-11-10",
                 "regular": 55, "currency": "USD"}]
        m = fmt.build_digest(cfg, [_trip(i) for i in range(5)], legs, "note here")
        self.assertTrue(m.startswith("✈️ <b>Weekly digest</b>"))
        above, _, folded = m.partition("<blockquote expandable>")
        self.assertEqual(above.count("<code>T"), 3)
        self.assertIn("note here", above)
        self.assertIn("2 more trips · cheapest legs", folded)
        self.assertIn("Yerevan (EVN)→Budapest (BUD)", folded)

    def test_empty_digest_still_renders(self):
        m = fmt.build_digest(config.load(), [], [], "")
        self.assertIn("Weekly digest", m)
        self.assertNotIn("blockquote", m)


class Stays(unittest.TestCase):
    def test_top3_then_fold_and_links(self):
        cfg = config.load()
        q = {"checkin": "2026-11-04", "checkout": "2026-11-11", "nights": 7,
             "child_age": 1, "flags": ["sea"], "budget": 90}
        ranked = [{"source": "booking", "name": "Hotel %d" % i, "price_night": 80 + i,
                   "true_nightly": 85 + i, "cost_note": "+ breakfast", "price_total": 600,
                   "rating": 8.5, "currency": "USD", "url": "https://example.com/%d" % i,
                   "loc_why": "near the beach"} for i in range(8)]
        m = fmt.build_stays(cfg, q, "Larnaca", ranked, {"booking": "https://booking.example"},
                            blocked=["airbnb"])
        self.assertTrue(m.startswith("\U0001f3e8 <b>Stays</b> · <i>Larnaca</i>"))
        self.assertIn("sea, budget 90", m)
        above, _, folded = m.partition("<blockquote expandable>")
        self.assertIn("Hotel 0", above)
        self.assertNotIn("Hotel 3", above)
        self.assertIn("Airbnb unavailable", above)
        self.assertIn("more stays", folded)
        self.assertIn("more in the sheet", folded)            # 8 found, 6 shown
        self.assertIn("Booking</a>", m)

    def test_nothing_matched(self):
        q = {"checkin": "2026-11-04", "checkout": "2026-11-11", "nights": 7, "child_age": 3}
        m = fmt.build_stays(config.load(), q, "Larnaca", [], {})
        self.assertIn("Nothing matched", m)
        self.assertIn("2 adults + child", m)


if __name__ == "__main__":
    unittest.main()
