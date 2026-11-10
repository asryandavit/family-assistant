"""amazon/parse.py against the 12 real EU captures (tests/fixtures/amazon/, CLAUDE.md §8): 6 search
pages and 6 product pages of Amazon UK, DE, IT. The expected values were read off the fixtures
(and checked against the page text) - never guessed. Rejection paths: no price is "not read",
a price in the wrong currency is not used, a page without the field gives None."""
import json
import os
import unittest
from datetime import date

from amazon import parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "amazon")
TODAY = date(2026, 11, 10)
with open(os.path.join(ROOT, "config_amazon.json"), encoding="utf-8") as _f:
    NAMES = json.load(_f)["amazon_seller_names"]
SEARCH = [(s, q) for s in ("uk", "de", "it") for q in ("elec", "baby")]


def page(site, query, kind):
    with open(os.path.join(FIX, "%s_%s_%s.html" % (site, query, kind)), encoding="utf-8") as f:
        return f.read()


class Helpers(unittest.TestCase):
    def test_review_count_forms(self):
        for raw, n in (("2K", 2000), ("(2K)", 2000), ("2.9K", 2900), ("14.4K", 14400), ("3.6K", 3600),
                       ("2,061", 2061), ("150", 150), ("1,939 ratings", 1939), ("1.2M", 1200000)):
            self.assertEqual(parse.count(raw), n, raw)
        self.assertIsNone(parse.count("no reviews"))

    def test_money_rejects_wrong_currency_and_nonsense(self):
        self.assertEqual(parse.money("£16.14", "GBP"), (16.14, "GBP"))
        self.assertEqual(parse.money("€1,299.00", "EUR"), (1299.0, "EUR"))
        self.assertEqual(parse.money("$16.14", "GBP"), (None, "USD"))       # never a number in the wrong money
        self.assertEqual(parse.money("£0.00", "GBP")[0], None)
        self.assertEqual(parse.money("£999,999.00", "GBP")[0], None)
        self.assertEqual(parse.money("", "GBP"), (None, None))

    def test_delivery_fee_rules(self):
        self.assertEqual(parse.delivery("FREE delivery Fri 13 Nov", "EUR")[0], 0.0)
        fee, note = parse.delivery("FREE delivery Fri 13 Nov on your first eligible order to UK or Ireland", "GBP")
        self.assertIsNone(fee)                    # a condition is not a fee
        self.assertIn("first", note)
        self.assertEqual(parse.delivery("£8.89 delivery Tuesday", "GBP")[0], 8.89)
        self.assertIsNone(parse.delivery("", "GBP")[0])
        self.assertIsNone(parse.delivery("Delivery to your region", "GBP")[0])

    def test_eta_with_abbreviated_and_full_months(self):
        self.assertEqual(parse.eta("Fri 13 Nov", TODAY), (date(2026, 11, 13), date(2026, 11, 13)))
        self.assertEqual(parse.eta("Friday, 13 November", TODAY), (date(2026, 11, 13), date(2026, 11, 13)))
        self.assertEqual(parse.eta("17 - 19 November", TODAY), (date(2026, 11, 17), date(2026, 11, 19)))
        self.assertEqual(parse.eta("Tomorrow, 11 Nov", TODAY), (date(2026, 11, 11), date(2026, 11, 11)))
        self.assertIsNone(parse.eta("soon", TODAY))
        self.assertIsNone(parse.eta("", TODAY))

    def test_spec_tokens_found_by_code_in_the_persons_words(self):
        self.assertEqual(parse.spec_tokens("usb c charger 65w"), ["65w"])
        self.assertEqual(parse.spec_tokens("USB-C charger 65 W"), ["65w"])
        self.assertEqual(parse.spec_tokens("baby romper 6-12 months"), [])
        self.assertTrue(parse.has_tokens("UGREEN USB C Charger 65 W, 3-Port", ["65w"]))
        self.assertFalse(parse.has_tokens("Anker 30W charger", ["65w"]))


class SearchPages(unittest.TestCase):
    def test_all_six_search_pages_parse_eight_cards_in_the_stores_currency(self):
        for site, q in SEARCH:
            cards = parse.parse_cards(page(site, q, "search"), site, TODAY)
            self.assertEqual(len(cards), 8, (site, q))
            for c in cards:
                self.assertRegex(c["id"], r"^[A-Z0-9]{10}$")
                self.assertEqual(c["currency"], parse.CURRENCY[site])
                self.assertEqual(c["market"], "amazon")
                self.assertTrue(c["url"].endswith("/dp/" + c["id"]))
                self.assertTrue(c["title"])
                if c["price"] is None:
                    self.assertIn("price not read", c["notes"])         # never a guess
                else:
                    self.assertGreater(c["price"], 0)
                self.assertEqual(c["seller"]["class"], parse.UNREAD)    # cards never carry the seller

    def test_postcode_line_on_all_six(self):
        want = {"uk": "E17 4SX", "de": "82152", "it": "70122"}
        for site, q in SEARCH:
            line = parse.deliver_to(page(site, q, "search"))
            self.assertTrue(parse.postcode_ok(line, want[site]), (site, line))
            self.assertFalse(parse.postcode_ok(line, "19720"))
            self.assertFalse(parse.postcode_ok("Deliver to United States", want[site]))

    def test_uk_electronics_card_in_full(self):
        c = {x["id"]: x for x in parse.parse_cards(page("uk", "elec", "search"), "uk", TODAY)}
        a = c["B091KQ39FM"]                       # Anker Nano II, Amazon's Choice, 5K+ bought
        self.assertEqual((a["price"], a["list_price"], a["currency"]), (16.14, 24.99, "GBP"))
        self.assertEqual((a["rating"], a["reviews"]), (4.6, 3674))
        self.assertEqual(a["sales"], 5000)
        self.assertIn("amazons_choice", a["badges"])
        self.assertFalse(a["sponsored"])
        self.assertEqual(a["delivery_eta"], (date(2026, 11, 13), date(2026, 11, 13)))
        self.assertIsNone(a["delivery_fee"])      # "FREE ... on your first eligible order": not a fee
        self.assertIn("deal", c["B0BFVGHFR8"]["badges"])

    def test_sponsored_cards_are_marked_and_may_lack_a_price(self):
        cards = parse.parse_cards(page("de", "baby", "search"), "de", TODAY)
        by = {c["id"]: c for c in cards}
        self.assertTrue(by["B0BF5L2C5Z"]["sponsored"])
        self.assertIsNone(by["B0BF5L2C5Z"]["price"])          # the trimmed capture cuts before the price
        self.assertFalse(by["B01C4GXARW"]["sponsored"])
        self.assertEqual(by["B01C4GXARW"]["reviews"], 2904)    # exact count, not "(2.9K)"
        self.assertEqual(by["B01CD3YY6W"]["reviews"], 2024)    # not the abbreviation "2K"

    def test_title_is_brand_plus_title_when_the_card_has_two_headings(self):
        it = {c["id"]: c for c in parse.parse_cards(page("it", "baby", "search"), "it", TODAY)}
        self.assertEqual(it["B09256R1N9"]["title"],
                         "Gerber 4 Pack Sleep 'N Play Footie Sleepers for Babies and Children Girl 0-24 (Pack of 4)")
        self.assertTrue(it["B08GHBMPZP"]["title"].startswith("Gerber Baby-Boys 4-Pack"))      # sponsored: no ad prefix
        self.assertNotIn("Sponsored", it["B08GHBMPZP"]["title"])
        uk = {c["id"]: c for c in parse.parse_cards(page("uk", "baby", "search"), "uk", TODAY)}
        self.assertIn("Halloween", uk["B0HCTXFX9P"]["title"])                                   # was just "Lilcutie"
        de = {c["id"]: c for c in parse.parse_cards(page("de", "elec", "search"), "de", TODAY)}
        self.assertTrue(de["B09LLRNGSD"]["title"].startswith("Anker Nano 65W"))               # one heading: unchanged

    def test_voucher_and_unit_price_are_not_taken_for_the_price(self):
        de = {c["id"]: c for c in parse.parse_cards(page("de", "elec", "search"), "de", TODAY)}
        v = de["B0HDNPCJCB"]
        self.assertEqual(v["price"], 11.99)                    # not the €11.03 after the voucher
        self.assertEqual(v["price_kind"], "voucher_available")
        baby = {c["id"]: c for c in parse.parse_cards(page("de", "baby", "search"), "de", TODAY)}
        self.assertEqual(baby["B0FLFWB16N"]["price"], 25.0)    # not €8.33/count

    def test_card_priced_in_the_wrong_currency_is_not_used(self):
        html = page("uk", "elec", "search").replace("£16.14", "$16.14")
        c = {x["id"]: x for x in parse.parse_cards(html, "uk", TODAY)}["B091KQ39FM"]
        self.assertIsNone(c["price"])
        self.assertTrue(any("expected GBP" in n for n in c["notes"]))

    def test_garbage_and_card_without_asin(self):
        self.assertEqual(parse.parse_cards("", "uk", TODAY), [])
        self.assertEqual(parse.parse_cards("<html>nothing here</html>", "uk", TODAY), [])
        self.assertIsNone(parse.parse_card('<div data-component-type="s-search-result" data-asin="">', "uk", TODAY))

    def test_a_repeated_asin_is_kept_once(self):
        html = page("it", "elec", "search")
        cards = parse.parse_cards(html + html, "it", TODAY)
        self.assertEqual(len(cards), len({c["id"] for c in cards}))


class ProductPages(unittest.TestCase):
    def prod(self, site, q):
        return parse.parse_product(page(site, q, "dp"), site, TODAY, NAMES)

    def test_seller_classes_on_all_six_product_pages(self):
        want = {("uk", "elec"): (parse.DISPATCHED, "UGREEN GROUP LIMITED UK"),
                ("uk", "baby"): (parse.THIRD, "JJLC Trading Ltd"),
                ("de", "elec"): (parse.DISPATCHED, "TOPADRE Tech EU"),
                ("de", "baby"): (parse.DISPATCHED, "lanqier Group Holding Limited - EU"),
                ("it", "elec"): (parse.DISPATCHED, "CUKTECH Direct"),
                ("it", "baby"): (parse.AMAZON, "Amazon")}
        for key, (cls, name) in want.items():
            s = self.prod(*key)["seller"]
            self.assertEqual((s["class"], s["name"]), (cls, name), key)
            self.assertTrue(s["evidence"])

    def test_product_fields(self):
        p = self.prod("de", "elec")
        self.assertEqual((p["price"], p["currency"], p["rating"], p["reviews"]), (19.99, "EUR", 4.3, 2061))
        self.assertEqual(p["fulfilment"], "Amazon")
        self.assertEqual(p["delivery_eta"], (date(2026, 11, 13), date(2026, 11, 13)))
        self.assertIsNone(p["delivery_fee"])
        self.assertIn("first", p["delivery_note"])
        self.assertIn("82152", p["deliver_to"])
        self.assertTrue(p["in_stock"])
        uk = self.prod("uk", "baby")
        self.assertEqual(uk["delivery_eta"], (date(2026, 11, 17), date(2026, 11, 19)))
        self.assertIsNone(uk["reviews"])                       # no reviews block: None, not 0
        self.assertEqual(self.prod("it", "baby")["reviews"], 4730)

    def test_no_price_block_means_not_read(self):
        html = page("uk", "elec", "dp").replace("apex-pricetopay-value", "other-price")
        p = parse.parse_product(html, "uk", TODAY, NAMES)
        self.assertIsNone(p["price"])
        self.assertIn("price not read", p["notes"])

    def test_page_without_a_seller_block_is_unread(self):
        p = parse.parse_product("<html><span id='productTitle'>x</span></html>", "uk", TODAY, NAMES)
        self.assertEqual(p["seller"]["class"], parse.UNREAD)
        self.assertIsNone(p["price"])

    def test_unavailable_page(self):
        html = page("uk", "elec", "dp")
        self.assertTrue(parse.parse_product(html, "uk", TODAY, NAMES)["in_stock"])
        gone = html.replace("In stock", "Currently unavailable.", 1)
        self.assertIn("Currently unavailable.", gone)
        self.assertFalse(parse.parse_product(gone, "uk", TODAY, NAMES)["in_stock"])
        self.assertFalse(parse.parse_product(html + '<div id="outOfStock">x</div>', "uk", TODAY, NAMES)["in_stock"])

    def test_the_words_currently_unavailable_in_a_script_do_not_make_it_unavailable(self):
        # live run 2026-11-10: these words sit in script strings of in-stock pages
        with open(os.path.join(FIX, "uk_elec_dp_live_excerpt.html"), encoding="utf-8") as f:
            excerpt = f.read()
        self.assertIn("Currently unavailable.", excerpt)
        self.assertFalse(parse.out_of_stock(excerpt))

    def test_seller_rules(self):
        s = parse.seller_of(("Sold by", "Foo Ltd"), ("Dispatches from", "Amazon"), NAMES)
        self.assertEqual(s["class"], parse.DISPATCHED)
        s = parse.seller_of(("Sold by", "Foo Ltd"), ("Dispatches from", "Foo Ltd"), NAMES)
        self.assertEqual(s["class"], parse.THIRD)
        s = parse.seller_of(("Sold by", "Foo Ltd"), (None, None), NAMES)
        self.assertEqual(s["class"], parse.THIRD)
        self.assertIn("dispatch not shown", s["evidence"])
        self.assertEqual(parse.seller_of(("Sold by", "Amazon EU S.à r.l."), (None, None), NAMES)["class"], parse.AMAZON)
        self.assertEqual(parse.seller_of(("Shipper / Seller", "Amazon"), (None, None), NAMES)["class"], parse.AMAZON)
        # used goods sold by "Amazon Warehouse" are not Amazon-new
        self.assertEqual(parse.seller_of(("Sold by", "Amazon Warehouse"), (None, None), NAMES)["class"], parse.THIRD)
        self.assertEqual(parse.seller_of((None, None), (None, None), NAMES)["class"], parse.UNREAD)

    def test_weight_and_size_from_a_full_details_table(self):
        # the Airfryer capture of tests/fixtures/market keeps the details table
        with open(os.path.join(ROOT, "tests", "fixtures", "market", "amazon_uk_dp.html"), encoding="utf-8") as f:
            p = parse.parse_product(f.read(), "uk", TODAY, NAMES)
        self.assertEqual(p["weight_kg"], 4.55)
        self.assertEqual(p["dims_cm"], (12.0, 35.0, 45.0))


if __name__ == "__main__":
    unittest.main()
