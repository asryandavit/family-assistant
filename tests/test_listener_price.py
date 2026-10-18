"""/price routing in listener.py, plus a regression check that the existing
travel commands still route exactly as before. A fake runner records launches,
so nothing runs and nothing is sent."""
import unittest

import listener
from lib import config


class FakeRunner:
    def __init__(self):
        self.calls = []

    def launch(self, name, extra_args=None, ack=None):
        self.calls.append((name, list(extra_args or []), ack))
        return "launched " + name

    def cancel(self):
        return "cancelled"


class Price(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load()
        self.r = FakeRunner()

    def _launch(self, text):
        out = listener.handle_text(self.cfg, self.r, text)
        return out, (self.r.calls[-1] if self.r.calls else None)

    def test_basic_query(self):
        out, call = self._launch("/price lentils")
        self.assertEqual(out, "launched price")
        name, args, ack = call
        self.assertEqual(name, "price")
        self.assertEqual(args, ["--sort", "cheap", "--", "lentils"])
        self.assertIn("lentils", ack)
        self.assertIn("Parma + Yerevan City", ack)

    def test_shop_and_sort_words(self):
        _, (_, args, ack) = self._launch("/price olive oil parma")
        self.assertEqual(args, ["--sort", "cheap", "--shop", "parma", "--", "olive", "oil"])
        self.assertIn("at Parma", ack)
        _, (_, args, _) = self._launch("/price chicken breast yc match")
        self.assertEqual(args, ["--sort", "match", "--shop", "yc", "--", "chicken", "breast"])

    def test_armenian_query_is_accepted(self):
        out, call = self._launch("/price ոսպ")
        self.assertEqual(out, "launched price")
        self.assertEqual(call[1], ["--sort", "cheap", "--", "ոսպ"])
        _, (_, args, _) = self._launch("/price հավի կրծքամիս yc")
        self.assertEqual(args, ["--sort", "cheap", "--shop", "yc", "--", "հավի", "կրծքամիս"])

    def test_empty_query_asks_instead_of_launching(self):
        out, call = self._launch("/price")
        self.assertIsNone(call)
        self.assertIn("/price lentils", out)
        out, call = self._launch("/price parma")
        self.assertIsNone(call)

    def test_options_cannot_be_injected(self):
        _, (_, args, _) = self._launch("/price --limit 999 milk")
        # the user's words all come after "--"
        self.assertEqual(args[:3], ["--sort", "cheap", "--"])
        self.assertNotIn("--limit", args[:args.index("--")])

    def test_rejects_odd_input(self):
        out, call = self._launch("/price <script>alert(1)</script>")
        self.assertIsNone(call)
        out, call = self._launch("/price " + "x" * 60)
        self.assertIsNone(call)

    def test_price_job_is_whitelisted_with_send(self):
        self.assertIn("price", listener.JOBS)
        self.assertTrue(listener.JOBS["price"]["args"][0].endswith("grocery_search.py"))
        self.assertIn("--send", listener.JOBS["price"]["args"])


class TravelRegression(unittest.TestCase):
    """The existing commands must behave exactly as before /price was added."""

    def setUp(self):
        self.cfg = config.load()
        self.r = FakeRunner()

    def test_flights_still_routes(self):
        listener.handle_text(self.cfg, self.r, "/flights BUD 01-30.11 7")
        name, args, ack = self.r.calls[-1]
        self.assertEqual(name, "flights")
        self.assertEqual(args[0], "BUD")
        self.assertIn("Budapest (BUD)", ack)

    def test_stays_still_routes(self):
        listener.handle_text(self.cfg, self.r, "/stays LCA 04-11.11 sea")
        name, args, _ = self.r.calls[-1]
        self.assertEqual(name, "stays")
        self.assertEqual(args[0], "LCA")

    def test_plain_jobs_and_help(self):
        listener.handle_text(self.cfg, self.r, "/scan")
        self.assertEqual(self.r.calls[-1][0], "scan")
        helptext = listener.handle_text(self.cfg, self.r, "/help")
        for c in ("/scan", "/digest", "/stays", "/flights", "/auto", "/price"):
            self.assertIn(c, helptext)
        self.assertIsNone(listener.handle_text(self.cfg, self.r, "hello there"))


if __name__ == "__main__":
    unittest.main()
