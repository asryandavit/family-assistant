"""Store page readers and block detection against real captures (2026-10-29, bot profile
.browser/market, Armenian IP). Amazon pages trimmed by tests/fixtures/market/trim_page.py."""
import os
import unittest
from datetime import date

from market import readers
from scrapers.market import blocked_reason

F = os.path.join(os.path.dirname(__file__), "fixtures", "market")
TODAY = date(2026, 10, 29)


def page(name):
    with open(os.path.join(F, name), encoding="utf-8") as f:
        return f.read()


def amazon(name):
    return readers.parse("amazon", page(name), TODAY)


class Amazon(unittest.TestCase):
    def test_us(self):
        r = amazon("amazon_us_dp.html")
        self.assertEqual((r["price"], r["currency"]), (17.99, "USD"))   # not the $9.00 per-count
        self.assertEqual(r["shipping"], 0.0)                            # FREE to 19720
        self.assertEqual(r["delivery"], (date(2026, 11, 4), date(2026, 11, 6)))
        self.assertTrue(r["in_stock"])
        self.assertEqual(r["weight_kg"], 0.25)
        self.assertIsNone(r["dims_cm"])                                 # '10.75"W x 4.5"H' is 2-D
        self.assertEqual(r["deliver_to"], "Deliver to New Castle 19720")
        self.assertTrue(r["title"].startswith("Mintra Home Plastic Bowls"))

    def test_uk_paid_delivery(self):
        r = amazon("amazon_uk_dp.html")
        self.assertEqual((r["price"], r["currency"], r["shipping"]), (131.99, "GBP", 28.74))
        self.assertEqual(r["delivery"], (date(2026, 11, 21), date(2026, 11, 24)))
        self.assertEqual(r["dims_cm"], (12.0, 35.0, 45.0))
        self.assertEqual(r["weight_kg"], 4.55)
        self.assertEqual(r["stock_text"], "Usually dispatched within 7 to 8 days")
        self.assertIn("E174SX", r["deliver_to"])

    def test_de_first_order_free_is_not_free(self):
        r = amazon("amazon_de_dp.html")
        self.assertEqual((r["price"], r["currency"]), (144.95, "EUR"))
        self.assertIsNone(r["shipping"])
        self.assertIn("first order", r["shipping_note"])
        self.assertEqual(r["stock_text"], "Only 3 left in stock.")
        self.assertIn("82152", r["deliver_to"])

    def test_it(self):
        r = amazon("amazon_it_dp.html")
        self.assertEqual((r["price"], r["currency"]), (124.73, "EUR"))
        self.assertIsNone(r["shipping"])
        self.assertEqual(r["delivery"], (date(2026, 11, 17), date(2026, 11, 18)))
        self.assertIn("70122", r["deliver_to"])

    def test_gone(self):
        self.assertEqual(amazon("amazon_us_notfound.html"), {"status": "gone"})


class Vega(unittest.TestCase):
    def test_product(self):
        r = readers.parse("vega", page("vega_product.html"), TODAY)
        self.assertEqual((r["price"], r["currency"], r["in_stock"]), (16900.0, "AMD", True))
        self.assertEqual(r["title"], "H/b accessories PHILIPS HX6064/87 (FOR TOOTH CARE)")

    def test_no_product_block_is_not_read(self):
        r = readers.parse("vega", "<html></html>", TODAY)
        self.assertIsNone(r["price"])


class NoParserYet(unittest.TestCase):
    def test_wb_and_ozon(self):
        for fam in ("wildberries", "ozon"):
            self.assertEqual(readers.parse(fam, "<html/>", TODAY), {"status": "no_parser"})


class BlockPages(unittest.TestCase):
    def test_wildberries_check(self):
        html = page("wildberries_block.html")
        self.assertEqual(blocked_reason("https://www.wildberries.ru/", "Проверяем браузер", html),
                         "проверяем браузер")
        self.assertEqual(blocked_reason("https://www.wildberries.ru/", "", html),
                         "page /__wbaas/challenges/")

    def test_ozon_no_connection(self):
        html = page("ozon_block.html")
        text = "Похоже,\xa0нет\xa0соединения\nВыключите VPN"      # non-breaking spaces as served
        self.assertEqual(blocked_reason("https://am.ozon.com/?__rr=1", text, html), "нет соединения")
        self.assertEqual(blocked_reason("https://am.ozon.com/", "", html), "page abt-challenge")

    def test_amazon_checkpoint_url(self):
        self.assertEqual(blocked_reason("https://www.amazon.com/checkpoint/continue?token=x", "", ""),
                         "url /checkpoint")

    def test_real_product_pages_are_not_blocks(self):
        for name in ("amazon_us_dp.html", "amazon_uk_dp.html", "amazon_de_dp.html",
                     "amazon_it_dp.html", "vega_product.html", "amazon_us_notfound.html"):
            html = page(name)
            self.assertIsNone(blocked_reason("https://x/dp/1", readers._text(html), html), name)


class Parsing(unittest.TestCase):
    def test_money(self):
        self.assertEqual(readers.parse_money("$1,234.56"), (1234.56, "USD"))
        self.assertEqual(readers.parse_money("144,95 €"), (144.95, "EUR"))
        self.assertEqual(readers.parse_money("1.234,50 €"), (1234.5, "EUR"))
        self.assertEqual(readers.parse_money("16 900 ֏"), (16900.0, "AMD"))
        self.assertEqual(readers.parse_money("9 890 ₽"), (9890.0, "RUB"))
        self.assertEqual(readers.parse_money(" "), (None, None))

    def test_delivery_forms(self):
        d = readers.parse_delivery
        self.assertEqual(d("November 4 - 6", TODAY), (date(2026, 11, 4), date(2026, 11, 6)))
        self.assertEqual(d("21 - 24 November", TODAY), (date(2026, 11, 21), date(2026, 11, 24)))
        self.assertEqual(d("Tuesday, 3 November", TODAY), (date(2026, 11, 3),) * 2)
        self.assertEqual(d("Monday, November 2", TODAY), (date(2026, 11, 2),) * 2)
        self.assertEqual(d("October 30 - November 2", TODAY), (date(2026, 10, 30), date(2026, 11, 2)))
        self.assertEqual(d("30 December - 2 January", date(2026, 12, 20)),
                         (date(2026, 12, 30), date(2027, 1, 2)))
        self.assertIsNone(d("", TODAY))

    def test_weight(self):
        self.assertEqual(readers.parse_weight_kg("4.55 Kilograms"), 4.55)
        self.assertEqual(readers.parse_weight_kg("2.2 Pounds"), 0.998)
        self.assertEqual(readers.parse_weight_kg("12.8 ounces"), 0.363)
        self.assertEqual(readers.parse_weight_kg("450 g"), 0.45)
        self.assertIsNone(readers.parse_weight_kg("heavy"))

    def test_dims(self):
        self.assertEqual(readers.parse_dims_cm("12D x 35W x 45H centimetres"), (12.0, 35.0, 45.0))
        self.assertEqual(readers.parse_dims_cm("14 x 10 x 5 inches; 2 Pounds"), (35.6, 25.4, 12.7))
        self.assertIsNone(readers.parse_dims_cm('10.75"W x 4.5"H'))


if __name__ == "__main__":
    unittest.main()
