"""amazon/search.py end to end, offline: a fake browser Session serving the real captures
(tests/fixtures/amazon/), a fake plan, a fake Telegram. Checks the order: questions when vague;
one progress line per store; one answer to the asking chat; a forced check page skips ONE store
and the others still answer; a wrong delivery postcode skips that store; the daily cap; the
cool-down; the answer is sent before it is saved."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import date

from amazon import limits, report, search, validate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "amazon")
RATES = {"date": "2026-11-10", "amd_per": {"GBP": 510.0, "EUR": 440.0, "USD": 390.0}}
TODAY = date(2026, 11, 10)
PLAN = validate.plan({"query_en": "usb c charger 65w",
                      "queries": {"uk": "usb c charger 65w", "de": "usb c ladegerät 65w",
                                  "it": "caricatore usb c 65w"},
                      "category": "electronics", "vague": False, "questions": []})
HOSTS = {"www.amazon.co.uk": "uk", "www.amazon.de": "de", "www.amazon.it": "it"}


class TG:
    def __init__(self, rich_ok=True):
        self.sent, self.rich_ok = [], rich_ok

    def send_html(self, cfg, text, silent=False, buttons=None, chat_id=None, **kw):
        self.sent.append(("html", chat_id, text, buttons))

    def send_rich(self, cfg, rich, plain, silent=True, buttons=None, chat_id=None):
        self.sent.append(("rich", chat_id, rich, buttons))
        return ("rich", 1) if self.rich_ok else ("plain", None)

    @staticmethod
    def esc(s):
        return s


def fixture(site, kind, q="elec"):
    with open(os.path.join(FIX, "%s_%s_%s.html" % (site, q, kind)), encoding="utf-8") as f:
        return f.read()


class FakeSession:
    """Serves captures; `block` = sites whose search page is a check page, `wrong` = sites whose
    delivery address is wrong; `block_dp` = sites whose product pages are a check page."""

    def __init__(self, block=(), wrong=(), block_dp=()):
        self.urls, self.block, self.wrong, self.block_dp = [], set(block), set(wrong), set(block_dp)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.exited = True

    def scroll_html(self):
        return ""

    def read(self, url, wait_selector=None):
        self.urls.append(url)
        site = HOSTS[url.split("/")[2]]
        is_search = "/s?k=" in url
        if site in self.block and (is_search or site in self.block_dp) or (site in self.block_dp and not is_search):
            return {"status": "blocked", "url": url, "final_url": url, "html": "", "text": "",
                    "detail": "enter the characters you see below"}
        html = fixture(site, "search" if is_search else "dp")
        if site in self.wrong and is_search:
            html = html.replace("London E174SX", "United States").replace("Krailling 82152", "United States") \
                       .replace("70122", "United States")
        return {"status": "ok", "url": url, "final_url": url, "html": html, "text": "", "detail": ""}


class Search(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "market"))
        shutil.copy(os.path.join(ROOT, "config_amazon.json"), self.root)
        shutil.copy(os.path.join(ROOT, "market", "tariffs.json"), os.path.join(self.root, "market"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.session = FakeSession()

    def run_job(self, tg, session=None, plan=PLAN, reason=None, **job):
        sess = session or self.session
        j = {"job": "ab12cd34", "kind": "search", "chat_id": "222", "description": "usb c charger 65w"}
        j.update(job)
        return search.run_search(
            j, {}, self.root, tg, TODAY, log=lambda m: None,
            plan_fn=lambda cfg, acfg, desc: (plan, {"out": 1}),
            reason_fn=reason or (lambda cfg, acfg, pick, ru: ("Sold by Amazon with many good reviews.", {"out": 2})),
            session_factory=lambda acfg, log: sess, rates_get=lambda root, d: RATES)

    def test_full_answer_for_three_stores(self):
        tg = TG()
        self.assertEqual(self.run_job(tg), "rich")
        progress = [t for k, c, t, b in tg.sent if k == "html"]
        self.assertEqual(len(progress), 3)
        self.assertIn("Amazon UK done (1/3)", progress[0])
        self.assertIn("Amazon IT done (3/3)", progress[2])
        kind, chat, rich, btns = tg.sent[-1]
        self.assertEqual((kind, chat), ("rich", "222"))                  # to the asking chat only
        for needle in ("Amazon UK", "Amazon DE", "Amazon IT", "🏆", "Why: Sold by Amazon with many good reviews.",
                       "AMD", "Seller:", "Trust", "usb c ladegerät 65w", "caricatore usb c 65w", "/dp/"):
            self.assertIn(needle, rich)
        self.assertTrue(any(lbl.startswith("👁 Watch") for row in btns for lbl, _ in row))
        self.assertTrue(self.session.exited)                             # browser always released
        last = search.load_last(self.root, "222")
        self.assertEqual(last["job"], "ab12cd34")
        self.assertEqual([s["status"] for s in last["sites"]], ["ok", "ok", "ok"])
        for s in last["sites"]:
            self.assertEqual(len(s["ranked"]), 3)                        # top 3 per store were read
            self.assertTrue(all(p["total_amd"] for p in s["ranked"]))
            self.assertTrue(all(p["seller"]["class"] != "unread" for p in s["ranked"]))

    def test_only_the_top_three_per_store_get_a_product_page(self):
        self.run_job(TG())
        dp = [u for u in self.session.urls if "/dp/" in u]
        self.assertEqual(len(dp), 9)
        self.assertEqual(len([u for u in self.session.urls if "/s?k=" in u]), 3)

    def test_65w_filter_keeps_titles_that_say_65w(self):
        self.run_job(TG())
        last = search.load_last(self.root, "222")
        for s in last["sites"]:
            for p in s["ranked"]:
                self.assertRegex(p["title"].lower().replace(" w", "w"), "65w")

    def test_forced_check_page_degrades_to_one_skipped_store(self):
        tg = TG()
        sess = FakeSession(block={"de"})
        self.assertEqual(self.run_job(tg, session=sess), "rich")
        rich = tg.sent[-1][2]
        self.assertIn("Amazon DE showed a check page", rich)
        self.assertIn("not bypassed", rich)
        last = search.load_last(self.root, "222")
        self.assertEqual({s["site"]: s["status"] for s in last["sites"]}, {"uk": "ok", "de": "check", "it": "ok"})
        self.assertTrue(last["sites"][0]["ranked"] and last["sites"][2]["ranked"])
        de = [u for u in sess.urls if "amazon.de" in u]
        self.assertEqual(len(de), 1)                                                  # only the one search page
        self.assertIn("/s?k=", de[0])
        self.assertGreater(limits.cooling(self.root, "de", 24), 23.9)

    def test_a_store_in_cooldown_is_not_opened(self):
        limits.mark_blocked(self.root, "it")
        tg = TG()
        self.run_job(tg)
        self.assertFalse([u for u in self.session.urls if "amazon.it" in u])
        self.assertIn("Amazon IT skipped", tg.sent[-1][2])

    def test_a_product_page_check_stops_that_store_only(self):
        sess = FakeSession(block_dp={"uk"})
        tg = TG()
        self.run_job(tg, session=sess)
        self.assertEqual(len([u for u in sess.urls if "amazon.co.uk" in u and "/dp/" in u]), 1)
        last = search.load_last(self.root, "222")
        uk = last["sites"][0]
        self.assertEqual(uk["status"], "ok")
        self.assertIn("check page", uk["notice"])
        self.assertTrue(all(p["seller"]["class"] == "unread" for p in uk["ranked"]))   # seller not read, said so
        self.assertEqual(len(last["sites"][1]["ranked"]), 3)

    def test_wrong_delivery_postcode_skips_that_store_with_a_message(self):
        sess = FakeSession(wrong={"uk"})
        tg = TG()
        self.run_job(tg, session=sess)
        self.assertIn("not set to the warehouse address", tg.sent[-1][2])
        uk = [u for u in sess.urls if "amazon.co.uk" in u]
        self.assertEqual(len(uk), 1)                                                  # no product page opened
        self.assertIn("/s?k=", uk[0])
        last = search.load_last(self.root, "222")
        self.assertEqual(last["sites"][0]["status"], "setup")

    def test_daily_cap_stops_before_the_browser(self):
        for _ in range(10):
            limits.count_run(self.root, TODAY)
        tg = TG()
        self.assertEqual(self.run_job(tg), "limit")
        self.assertEqual(self.session.urls, [])
        self.assertIn("10 times today", tg.sent[-1][2])

    def test_a_run_counts_once_against_the_cap(self):
        self.run_job(TG())
        self.assertEqual(limits.runs_today(self.root, TODAY), 1)

    def test_vague_plan_asks_one_question_and_reads_nothing(self):
        vague = dict(PLAN, vague=True, questions=[{"q": "How old is the baby?", "options": ["0-3 months", "6-12 months"]}])
        tg = TG()
        self.assertEqual(self.run_job(tg, plan=vague, description="baby romper"), "asked")
        kind, chat, text, btns = tg.sent[-1]
        self.assertIn("How old is the baby?", text)
        self.assertEqual(btns[0][0], ("0-3 months", "am:q:ab12cd34:0:0"))
        self.assertEqual(self.session.urls, [])
        self.assertTrue(search.read_json(self.root, "pending_ab12cd34.json"))
        self.assertEqual(limits.runs_today(self.root, TODAY), 0)                    # asking costs nothing

    def test_answers_are_part_of_the_planned_description(self):
        seen = []
        def plan_fn(cfg, acfg, desc):
            seen.append(desc)
            return PLAN, {}
        j = {"job": "cd34ef56", "kind": "search", "chat_id": "222", "description": "baby romper",
             "answers": ["How old is the baby 6-12 months"]}
        search.run_search(j, {}, self.root, TG(), TODAY, log=lambda m: None, plan_fn=plan_fn,
                          reason_fn=lambda *a: ("ok", {}), session_factory=lambda a, lg: self.session,
                          rates_get=lambda r, d: RATES)
        self.assertEqual(seen, ["baby romper; How old is the baby 6-12 months"])

    def test_plan_failure_is_told_to_the_asker(self):
        tg = TG()
        def boom(cfg, acfg, desc):
            raise ValueError("category 'x' not allowed")
        j = {"job": "ab12cd34", "kind": "search", "chat_id": "222", "description": "xx yy"}
        self.assertEqual(search.run_search(j, {}, self.root, tg, TODAY, log=lambda m: None, plan_fn=boom), "plan_failed")
        self.assertIn("could not understand", tg.sent[-1][2])

    def test_plain_fallback_when_rich_does_not_fit(self):
        tg = TG()
        orig = report.fits
        report.fits = lambda rich: False
        self.addCleanup(setattr, report, "fits", orig)
        self.assertEqual(self.run_job(tg), "plain")
        self.assertEqual(tg.sent[-1][0], "html")

    def test_costume_listings_are_left_out_unless_asked_for(self):
        from amazon import parse
        with open(os.path.join(ROOT, "config_amazon.json"), encoding="utf-8") as f:
            acfg = json.load(f)
        cards = parse.parse_cards(fixture("de", "search", "baby"), "de", TODAY)
        priced = [c for c in cards if c["price"] is not None]
        priced[0]["title"] = "Baby Halloween Pumpkin Costume Romper"
        chosen, notes = search.choose(priced, "baby romper 6-12 months", acfg)
        self.assertNotIn(priced[0]["id"], [c["id"] for c in chosen])
        self.assertTrue(any("costume" in n for n in notes))
        _, asked_notes = search.choose(priced, "baby halloween costume", acfg)   # asked for: not filtered
        self.assertFalse(any("costume" in n for n in asked_notes))

    def test_merge_product_rules(self):
        from amazon import parse
        card = parse.parse_cards(fixture("uk", "search"), "uk", TODAY)[0]
        info = parse.parse_product(fixture("uk", "dp"), "uk", TODAY, ["amazon"])
        m = search.merge_product(card, info)
        self.assertEqual(m["price"], info["price"])                       # the buy-box price wins
        self.assertTrue(any("product page" in n for n in m["notes"]))      # and the difference is said
        self.assertEqual(m["seller"]["class"], "dispatched_by_amazon")
        gone = search.merge_product(card, dict(info, in_stock=False))
        self.assertIsNone(gone["price"])
        self.assertIn("currently unavailable on the product page", gone["notes"])
        noprice = search.merge_product(card, dict(info, price=None))
        self.assertEqual(noprice["price"], card["price"])                 # card price kept, said so
        self.assertTrue(any("no buy-box price" in n for n in noprice["notes"]))

    def test_choose_orders_by_trust_then_price_and_filters_by_spec(self):
        from amazon import parse
        with open(os.path.join(ROOT, "config_amazon.json"), encoding="utf-8") as f:
            acfg = json.load(f)
        cards = parse.parse_cards(fixture("uk", "search"), "uk", TODAY)
        cards[3]["title"] = "Cheap 20W charger"            # the person typed 65w: this one drops out
        cards[3]["price"] = 1.0
        chosen, notes = search.choose(cards, "usb c charger 65w", acfg)
        self.assertEqual(len(chosen), 3)
        self.assertTrue(all(c["price"] is not None for c in chosen))
        self.assertNotIn(cards[3]["id"], [c["id"] for c in chosen])
        self.assertTrue(all(parse.has_tokens(c["title"], ["65w"]) for c in chosen))
        self.assertTrue(any("65w" in n for n in notes))
        # no number+unit in the words: nothing is filtered
        chosen2, notes2 = search.choose(cards, "usb c charger", acfg)
        self.assertEqual(notes2, [])
        self.assertEqual(len(chosen2), 3)


if __name__ == "__main__":
    unittest.main()
