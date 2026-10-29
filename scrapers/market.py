"""Read store product pages in the bot's own browser profile (.browser/market).

Headed Chromium with a persistent profile, like scrapers/stays.py. The bot only reads:
it never logs in with a password, never clicks add-to-cart or buy, and never tries to pass
a bot check, CAPTCHA or block page (no stealth plugins, solvers or proxies). A block page is
recognised and returned as status "blocked"; the caller skips that store for the night.

    python scrapers/market.py --capture URL --out tests/fixtures/market/x.html
                                   open one page, save its HTML (fixtures, CLAUDE.md §8)
    python scrapers/market.py --setup
                                   set each Amazon's delivery postcode to the forwarder's
                                   warehouse (market/stores.md) and the store's own currency
"""
import argparse
import os
import random
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PROFILE = os.path.join(ROOT, ".browser", "market")

# Phrases on block / check pages, per store family; matched on the visible text, lower-case.
BLOCK_PHRASES = [
    # Amazon
    "enter the characters you see below", "type the characters you see in this image",
    "sorry, we just need to make sure you're not a robot", "geben sie die zeichen unten ein",
    "inserisci i caratteri", "to discuss automated access to amazon data",
    # Wildberries
    "подозрительная активность", "suspicious activity", "почти готово", "проверяем браузер",
    # Ozon
    "доступ ограничен", "отключите vpn", "turn off vpn", "нет соединения", "access restricted",
    # generic
    "verify you are human", "are you a robot", "unusual traffic", "press and hold",
    "confirm you are human", "checking your browser", "captcha",
]
BLOCK_URL_PARTS = ["/errors/validatecaptcha", "/captcha", "/checkpoint", "antibot", "/abt/"]
# Challenge scripts/styles that only block pages load (seen 2026-10-29: Wildberries
# /__wbaas/challenges/antibot/, Ozon st.ozone.ru/s3/abt-challenge/).
BLOCK_HTML_MARKERS = ["/__wbaas/challenges/", "abt-challenge", "/errors/validatecaptcha"]


def blocked_reason(url, visible_text, html=""):
    """The phrase, URL part or page marker that shows a block/check page, or None."""
    u = (url or "").lower()
    hit = next((p for p in BLOCK_URL_PARTS if p in u), None)
    if hit:
        return "url " + hit
    t = " ".join((visible_text or "").lower().split())      # also folds non-breaking spaces
    hit = next((p for p in BLOCK_PHRASES if p in t), None)
    if hit:
        return hit
    h = (html or "")[:200000].lower()
    hit = next((p for p in BLOCK_HTML_MARKERS if p in h), None)
    return "page " + hit if hit else None


# Amazon delivery location and currency (market/stores.md). Currency rides on the i18n-prefs
# cookie Amazon itself sets from its "Change currency" page.
AMAZON = {
    "us": {"host": "www.amazon.com", "postcode": "19720", "currency": "USD"},
    "uk": {"host": "www.amazon.co.uk", "postcode": "E17 4SX", "currency": "GBP"},
    "de": {"host": "www.amazon.de", "postcode": "82152", "currency": "EUR"},
    "it": {"host": "www.amazon.it", "postcode": "70122", "currency": "EUR"},
}

COOKIE_BUTTONS = ["#sp-cc-rejectall-link", "input#sp-cc-rejectall-link",
                  "button:has-text('Decline')", "button:has-text('Reject all')",
                  "button:has-text('Rifiuta')", "button:has-text('Ablehnen')",
                  "role=button[name='Decline']", "text='Decline'", "text='Rifiuta'",
                  "text='Ablehnen'"]


class Session:
    """One browser for the whole run. read() makes exactly one attempt per URL."""

    def __init__(self, headless=False, pause=(3.0, 6.0), log=print):
        self.headless, self.pause, self.log = headless, pause, log
        self._pw = self._ctx = self._page = None
        self._last = 0.0

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        os.makedirs(PROFILE, exist_ok=True)
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            PROFILE, headless=self.headless, locale="en-US",
            viewport={"width": 1366, "height": 900})
        for site in AMAZON.values():
            self._ctx.add_cookies([{"name": "i18n-prefs", "value": site["currency"],
                                    "domain": "." + site["host"].replace("www.", ""), "path": "/"}])
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        return self

    def __exit__(self, *exc):
        try:
            self._ctx.close()
        finally:
            self._pw.stop()

    def _polite(self):
        wait = random.uniform(*self.pause) - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()

    def _cookies(self):
        for sel in COOKIE_BUTTONS:
            try:
                el = self._page.locator(sel).first
                if el.count() and el.is_visible(timeout=1000):
                    el.click(timeout=3000)
                    self._page.wait_for_timeout(800)
                    return
            except Exception:
                continue

    def read(self, url, wait_selector=None):
        """{"status": ok|blocked|error, "url", "final_url", "html", "text", "detail"}."""
        self._polite()
        page = self._page
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            self._cookies()
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=15000, state="attached")
                except Exception:
                    pass
            page.wait_for_timeout(2500)
            html = page.content()
            try:
                text = page.inner_text("body")
            except Exception:
                text = ""
            final = page.url
        except Exception as e:
            return {"status": "error", "url": url, "final_url": url, "html": "", "text": "",
                    "detail": str(e)[:200]}
        why = blocked_reason(final, text, html)
        if why:
            self.log("  blocked: %s (%s)" % (url[:70], why))
            return {"status": "blocked", "url": url, "final_url": final, "html": html,
                    "text": text, "detail": why}
        return {"status": "ok", "url": url, "final_url": final, "html": html, "text": text,
                "detail": ""}

    # ---------------------------------------------------------- profile setup

    def amazon_location(self, key):
        """Set one Amazon's delivery postcode through its own 'Deliver to' box.
        Returns the 'Deliver to' line read back afterwards."""
        site = AMAZON[key]
        page = self._page
        self._polite()
        page.goto("https://%s/" % site["host"], wait_until="domcontentloaded", timeout=60000)
        self._cookies()
        why = blocked_reason(page.url, page.inner_text("body"))
        if why:
            return "blocked (%s)" % why
        line = self.amazon_deliver_to()
        if site["postcode"].replace(" ", "") in line.replace(" ", ""):
            return line + " (already set)"
        page.click("#nav-global-location-popover-link", timeout=15000)
        page.wait_for_selector("#GLUXZipUpdateInput", timeout=15000)
        page.fill("#GLUXZipUpdateInput", site["postcode"])
        page.click("#GLUXZipUpdate", timeout=10000)
        page.wait_for_timeout(2500)
        for sel in ("#GLUXConfirmClose", "button[name='glowDoneButton']", ".a-popover-footer button"):
            try:
                el = page.locator(sel).first
                if el.count() and el.is_visible(timeout=1000):
                    el.click(timeout=3000)
                    break
            except Exception:
                continue
        page.wait_for_timeout(1500)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        return self.amazon_deliver_to()

    def amazon_deliver_to(self):
        try:
            text = self._page.inner_text("#glow-ingress-block", timeout=5000)
        except Exception:
            return "(deliver-to line not found)"
        return re.sub(r"[\s‌]+", " ", text).strip()


def main():
    ap = argparse.ArgumentParser(description="Market watch store pages (bot profile).")
    ap.add_argument("--capture", help="URL to open once and save")
    ap.add_argument("--out", help="where to save the HTML (with --capture)")
    ap.add_argument("--setup", action="store_true", help="set Amazon postcodes and currency")
    a = ap.parse_args()
    with Session() as s:
        if a.setup:
            for key in AMAZON:
                try:
                    line = s.amazon_location(key)
                except Exception as e:
                    dump = os.path.join(ROOT, ".browser", "market_setup_%s" % key)
                    try:
                        s._page.screenshot(path=dump + ".png")
                        with open(dump + ".html", "w", encoding="utf-8") as f:
                            f.write(s._page.content())
                    except Exception:
                        pass
                    line = "NOT SET (%s) — page saved to %s.png" % (str(e).splitlines()[0][:80], dump)
                print("  amazon %s: %s" % (key, line), flush=True)
        if a.capture:
            r = s.read(a.capture)
            print("  %s  final=%s  %s" % (r["status"], r["final_url"][:100], r["detail"]))
            if a.out and r["html"]:
                with open(a.out, "w", encoding="utf-8") as f:
                    f.write(r["html"])
                print("  saved %s (%d bytes)" % (a.out, len(r["html"])))


if __name__ == "__main__":
    main()
