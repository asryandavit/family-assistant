"""Mini App smoke test in a real browser (review §14.2, decision 105).

Chromium (Playwright) opens the BUILT app (miniapp/web/dist) from a throwaway server that has a TEST
bot token, a test-signed initData in the URL hash (the same way Telegram passes it) and fake
actions behind it. Telegram's script is replaced by a small stub with the same shape (BackButton,
MainButton, CloudStorage, haptics, themeChanged) so the test needs no network and can press
Telegram's own buttons. Covers: Home, a deep link, back, China details, one ok and one refused
action, the MainButton search, dark mode, remembered tab.

Skipped when Playwright's Chromium or the built app is missing (`npm run build` in miniapp/web)."""
import json
import os
import threading
import time
import unittest
from urllib.parse import quote

from miniapp import DIST, server
from tests.test_miniapp_china import current
from tests.test_miniapp_screens import FakeSvc
from tests.test_miniapp_server import CFG, OWNER, PERSONS, TOKEN, init_data

try:
    from playwright.sync_api import sync_playwright
except ImportError:                                                    # pragma: no cover
    sync_playwright = None

LIGHT = {"bg_color": "#ffffff", "text_color": "#000000", "secondary_bg_color": "#efeff4",
         "hint_color": "#999999", "button_color": "#2481cc", "button_text_color": "#ffffff"}
DARK = {"bg_color": "#212121", "text_color": "#ffffff", "secondary_bg_color": "#0f0f0f",
        "hint_color": "#aaaaaa", "button_color": "#8774e1", "button_text_color": "#ffffff"}

STUB = r"""
(function () {
  const h = new URLSearchParams(location.hash.slice(1));
  const theme = JSON.parse(h.get('tgWebAppThemeParams') || '{}');
  const listeners = {}, store = {};
  const cbs = (o) => ({ _cbs: [], onClick(f) { this._cbs.push(f); return this; },
    offClick(f) { this._cbs = this._cbs.filter(x => x !== f); return this; } });
  const bb = Object.assign(cbs(), { isVisible: false, show() { this.isVisible = true; }, hide() { this.isVisible = false; } });
  const mb = Object.assign(cbs(), { isVisible: false, isActive: true, isProgressVisible: false, text: '',
    setParams(p) { if ('text' in p) this.text = p.text; if ('is_visible' in p) this.isVisible = p.is_visible;
      if ('is_active' in p) this.isActive = p.is_active; return this; },
    show() { this.isVisible = true; return this; }, hide() { this.isVisible = false; return this; },
    showProgress() { this.isProgressVisible = true; return this; }, hideProgress() { this.isProgressVisible = false; return this; } });
  const css = (t) => { const r = document.documentElement.style;
    for (const [k, v] of Object.entries(t)) r.setProperty('--tg-theme-' + k.replace(/_/g, '-'), v); };
  css(theme);
  const W = { initData: h.get('tgWebAppData') || '', colorScheme: theme.bg_color === '#212121' ? 'dark' : 'light',
    themeParams: theme, platform: h.get('tgWebAppPlatform') || 'ios', version: '8.0', ready() {}, expand() {}, close() {},
    isVersionAtLeast() { return true; }, setHeaderColor() {}, setBackgroundColor() {},
    onEvent(e, f) { (listeners[e] = listeners[e] || []).push(f); },
    offEvent(e, f) { listeners[e] = (listeners[e] || []).filter(x => x !== f); },
    BackButton: bb, MainButton: mb,
    HapticFeedback: { selectionChanged() { T.haptics.push('select'); }, impactOccurred() { T.haptics.push('tap'); },
      notificationOccurred(t) { T.haptics.push(t); } },
    CloudStorage: { setItem(k, v, cb) { store[k] = v; cb && cb(null, true); }, getItem(k, cb) { cb(null, store[k] ?? ''); } },
    showConfirm(m, cb) { T.confirms.push(m); cb && cb(true); }, enableClosingConfirmation() {},
    disableClosingConfirmation() {}, openLink(u) { T.opened.push(u); },
    checkHomeScreenStatus(cb) { cb && cb('missed'); }, addToHomeScreen() { T.homeAdded = true; } };
  const T = { haptics: [], confirms: [], opened: [], store, bb, mb, homeAdded: false,
    back() { bb._cbs.slice().forEach(f => f()); }, mainClick() { mb._cbs.slice().forEach(f => f()); },
    setTheme(t) { css(t); W.themeParams = t; W.colorScheme = t.bg_color === '#212121' ? 'dark' : 'light';
      (listeners.themeChanged || []).slice().forEach(f => f()); } };
  window.__tg = T;
  window.Telegram = { WebApp: W };
})();
"""

REFUSED = "That result is older than 24 h — send /china again."


def china_action(chat_id, action, job, n):
    return "👁 Added to 🌍 Market watch: <b>Item</b> at ¥9." if action == "watch" else REFUSED


@unittest.skipIf(sync_playwright is None, "playwright is not installed")
@unittest.skipUnless(os.path.isfile(os.path.join(DIST, "index.html")),
                     "miniapp/web/dist is not built (npm run build)")
class SmokeBase(unittest.TestCase):
    """The server, the browser and the helpers; the tests are in Smoke (and tests/test_miniapp_smoke_b.py)."""

    @classmethod
    def make_svc(cls):
        return FakeSvc()

    @classmethod
    def setUpClass(cls):
        cls.svc = cls.make_svc()
        data = current()
        cls.app = server.App(CFG, TOKEN, PERSONS, svc=cls.svc, china_action=china_action,
                             china_load=lambda chat: data if chat == str(OWNER) else None)
        cls.srv = server.Server(("127.0.0.1", 0), cls.app)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        try:
            cls.browser = cls.pw.chromium.launch()
        except Exception as e:                                         # no browser installed
            cls.pw.stop()
            cls.srv.shutdown()
            cls.srv.server_close()
            raise unittest.SkipTest(f"Chromium is not available: {type(e).__name__}") from e

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        self.svc.calls.clear()
        self.app.run_limiter.hits.clear()
        self.app.limiter.hits.clear()
        self.ctx = self.browser.new_context(viewport={"width": 375, "height": 812})
        self.ctx.route("https://telegram.org/js/telegram-web-app.js",
                       lambda r: r.fulfill(body=STUB, content_type="text/javascript"))
        self.page = self.ctx.new_page()
        self.addCleanup(self.ctx.close)

    def open(self, screen="", theme=LIGHT, platform="ios"):
        raw = init_data(OWNER)
        url = (f"http://127.0.0.1:{self.port}/{('?screen=' + screen) if screen else ''}#tgWebAppData="
               + quote(raw, safe="") + f"&tgWebAppVersion=8.0&tgWebAppPlatform={platform}&tgWebAppThemeParams="
               + quote(json.dumps(theme), safe=""))
        self.page.goto(url)

    def tg(self, expr):
        return self.page.evaluate(f"__tg.{expr}")

    def until(self, js, timeout=6.0):
        """Poll a JS expression until it is truthy. Not page.wait_for_function: that evaluates a
        string in the page, and the app's CSP (no 'unsafe-eval') rightly forbids it; the test keeps
        the production CSP on."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.page.evaluate(js):
                return
            time.sleep(0.05)
        self.fail(f"timed out waiting for: {js}")


class Smoke(SmokeBase):
    # ---------------------------------------------------------------- Home, deep link, back

    def test_home_lists_the_sections_and_who_you_are(self):
        self.open()
        self.page.get_by_text("Signed in as Davit · owner").wait_for()
        for name in ("Today", "China", "Market", "Basket", "Travel"):
            self.assertTrue(self.page.get_by_text(name, exact=True).first.is_visible(), name)
        self.assertFalse(self.tg("bb.isVisible"))                      # no Back button on Home
        self.page.get_by_text("Add to home screen").wait_for()          # 8.0 client, status "missed"

    def test_deep_link_opens_china_and_back_returns_home(self):
        self.open("china")
        self.page.get_by_text("Search China").wait_for()
        self.assertTrue(self.tg("bb.isVisible"))
        self.tg("back()")
        self.page.get_by_text("Signed in as Davit · owner").wait_for()
        self.assertFalse(self.tg("bb.isVisible"))

    def test_unknown_person_sees_private(self):
        raw = init_data(999000111)
        self.page.goto(f"http://127.0.0.1:{self.port}/#tgWebAppData=" + quote(raw, safe="")
                       + "&tgWebAppVersion=8.0&tgWebAppThemeParams=" + quote(json.dumps(LIGHT), safe=""))
        self.page.get_by_text("This app is private").wait_for()

    # ---------------------------------------------------------------- China: details, ok, refused

    def test_details_open_and_actions_ok_and_refused(self):
        self.open("china")
        self.page.get_by_text("Details", exact=True).first.wait_for()
        self.page.get_by_text("Details", exact=True).first.click()
        self.page.get_by_text("Shipping to Yerevan").first.wait_for()
        self.page.get_by_role("button", name="Watch").first.click()
        self.page.locator(".msg.ok", has_text="Added to").first.wait_for()
        self.page.get_by_role("button", name="Reviews").first.click()
        self.page.locator(".msg.bad", has_text="older than 24 h").first.wait_for()
        self.assertIn("success", self.tg("haptics"))                    # Telegram's names for the buzz
        self.assertIn("warning", self.tg("haptics"))

    def test_pick_jumps_to_its_card(self):
        self.open("china")
        self.page.get_by_text("🏆 Pick", exact=True).wait_for()
        self.page.locator(".hint", has_text="↓").first.click()
        self.until("document.querySelector('.flash') !== null")

    def card_ids(self):
        return self.page.locator("[id^=card-]").evaluate_all("els => els.map(e => e.id)")

    def test_order_and_filter_reorder_without_calculating(self):
        from miniapp import china_view
        orders = china_view.view(current())["orders"]                    # computed on the PC
        self.open("china")
        self.page.locator("[id^=card-]").first.wait_for()
        self.assertEqual(self.card_ids(), [f"card-{n}" for n in orders["trust"]])
        self.page.get_by_text("Cheapest delivered").click()
        self.until(f"document.querySelector('[id^=card-]').id === 'card-{orders['delivered'][0]}'")
        self.assertEqual(self.card_ids(), [f"card-{n}" for n in orders["delivered"]])
        self.page.get_by_text("1688", exact=True).last.click()          # the filter chip (the status row is first)
        heads = self.page.locator("[id^=card-] h1").all_inner_texts()
        self.assertTrue(heads and all("1688" in h for h in heads), heads)
        self.assertLess(len(heads), len(orders["delivered"]))

    def test_china_still_shows_cards_when_the_server_sends_no_orders(self):
        """The bundle is served live; the Python server restarts later. A page newer than the server
        must not crash on a missing `orders` (it showed an error screen before this was handled)."""
        from unittest import mock

        from miniapp import china_view
        with mock.patch.object(china_view, "_orders", return_value=None):
            self.open("china")
            self.page.locator("[id^=card-]").first.wait_for()
        self.assertGreater(len(self.card_ids()), 1)

    # ---------------------------------------------------------------- MainButton, confirm, prefs

    def test_main_button_searches(self):
        self.open("china")
        self.page.get_by_label("What are you looking for?").fill("silicone phone case")
        self.until("__tg.mb.isVisible")
        self.assertEqual(self.tg("mb.text"), "🔎 Search")
        self.tg("mainClick()")
        self.page.get_by_text("Sent to the bot").first.wait_for()
        self.assertEqual(self.svc.calls[-1], ("run", str(OWNER), "china", "silicone phone case"))

    def test_basket_asks_before_it_messages_the_family(self):
        self.open("basket")
        self.until("__tg.mb.isVisible")
        self.tg("mainClick()")
        self.page.get_by_text("Sent to the bot").first.wait_for()
        self.assertIn("both of you", self.tg("confirms")[0])
        self.assertEqual(self.svc.calls[-1], ("run", str(OWNER), "basket", "weekly"))

    def test_tab_choice_is_remembered(self):
        self.open("today")
        self.page.get_by_text("Next week", exact=True).wait_for()
        self.page.get_by_text("Next week", exact=True).click()
        self.until("__tg.store.ui_plan_tab === 'week'")

    # ---------------------------------------------------------------- dark mode

    def test_follows_the_telegram_theme(self):
        self.open()
        self.page.get_by_text("Signed in as Davit · owner").wait_for()
        def bg():
            return self.page.evaluate("getComputedStyle(document.body).backgroundColor")

        self.assertEqual(bg(), "rgb(239, 239, 244)")
        self.tg(f"setTheme({json.dumps(DARK)})")
        self.until("getComputedStyle(document.body).backgroundColor === 'rgb(15, 15, 15)'")
        self.assertEqual(bg(), "rgb(15, 15, 15)")


if __name__ == "__main__":
    unittest.main()
