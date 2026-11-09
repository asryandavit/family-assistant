"""Taobao / Tmall in the bot's own browser profile (.browser/taobao) — owner's choice (a),
2026-11-09 (docs/briefs/CHINA_SEARCH.md §8). The Claude in Chrome extension asks for a
click on every Taobao action, so Taobao cannot run unattended there.

Reading only, slowly: one search page + at most `max_pages` product pages, 20–30 s apart.
The owner signs in ONCE himself (`python -m china.taobao --setup`): the bot never types a
password or code. A login page, a check, a slider or 访问异常 is reported, never passed.

    python -m china.taobao --setup            open Taobao's login page; you sign in; it waits
    python -m china.taobao --probe <query>    read one search page and print what it sees
"""
import argparse
import os
import random
import re
import sys
import time
from urllib.parse import quote

from china import ROOT

PROFILE = os.path.join(ROOT, ".browser", "taobao")
LOGIN_MARKS = ("亲，请登录", "密码登录", "短信登录", "扫码登录")
CHECK_MARKS = ("访问异常", "安全验证", "滑块", "请拖动", "验证码", "unusual traffic", "baxia")
CARD_JS = r"""() => { const seen = {}; const rows = [];
  for (const a of document.querySelectorAll('a')) {
    const m = (a.href || '').match(/(?:item\.taobao\.com|detail\.tmall\.com)\/item\.htm\?.*?[?&]?id=(\d+)/)
           || (a.href || '').match(/[?&]id=(\d{8,15})/);
    if (!m || !/item\.taobao\.com|detail\.tmall\.com/.test(a.href)) continue;
    const id = m[1]; const t = (a.innerText || '').replace(/\n+/g, '|');
    if (!seen[id] || t.length > seen[id].length) seen[id] = t; }
  return Object.entries(seen); }"""


def state(text, n_links=0):
    """'login' | 'check' | 'ok' | 'empty' from the visible text."""
    t = text or ""
    if any(m in t for m in CHECK_MARKS):
        return "check"
    if n_links == 0 and any(m in t for m in LOGIN_MARKS):
        return "login"
    return "ok" if n_links else "empty"


def choose(cards, n):
    """Product pages to open: official flagships first, then the search order."""
    off = [c for c in cards if "官方旗舰店" in c[1]]
    rest = [c for c in cards if c not in off]
    return [c[0] for c in (off + rest)[:n]]


class Reader:
    def __init__(self, headless=False, pause=(20.0, 30.0), log=print):
        self.headless, self.pause, self.log = headless, pause, log
        self._last = 0.0

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        os.makedirs(PROFILE, exist_ok=True)
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            PROFILE, headless=self.headless, locale="zh-CN", viewport={"width": 1366, "height": 900})
        self.page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        return self

    def __exit__(self, *exc):
        try:
            self._ctx.close()
        finally:
            self._pw.stop()

    def _polite(self):
        wait = random.uniform(*self.pause) - (time.time() - self._last)
        if self._last and wait > 0:
            time.sleep(wait)
        self._last = time.time()

    def open(self, url, settle_ms=6000):
        self._polite()
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(settle_ms)
        try:
            return self.page.inner_text("body")
        except Exception:
            return ""

    def search(self, query_cn):
        text = self.open("https://s.taobao.com/search?q=" + quote(query_cn), settle_ms=8000)
        cards = [(i, t) for i, t in self.page.evaluate(CARD_JS)]
        return state(text, len(cards)), cards, text

    def product(self, item_id):
        text = self.open("https://item.taobao.com/item.htm?id=" + item_id)
        st = state(text, 1)
        return st, text


def read(query_cn, max_pages=3, log=print, reader=None):
    """{"status", "notice", "cards": [(id, text)], "pages": {id: text}}."""
    out = {"status": "ok", "notice": None, "cards": [], "pages": {}}
    try:
        with (reader or Reader(log=log)) as r:
            st, cards, text = r.search(query_cn)
            if st != "ok":
                out["status"] = "login" if st in ("login", "empty") else st
                out["notice"] = re.sub(r"\s+", " ", text)[:160]
                return out
            out["cards"] = cards[:40]
            for item_id in choose(cards, max_pages):
                st, page = r.product(item_id)
                if st == "check":
                    out["notice"] = "product page check: " + re.sub(r"\s+", " ", page)[:120]
                    break                       # stop reading Taobao for this run
                out["pages"][item_id] = page
    except Exception as e:
        out.update(status="error", notice=str(e)[:160])
    return out


def setup(timeout_s=600):
    print("Opening Taobao's sign-in page in the bot's browser (.browser/taobao).")
    print("Sign in yourself (QR code in the Taobao app is easiest). This window waits up to "
          "%d minutes and closes when it sees you are signed in." % (timeout_s // 60))
    with Reader(pause=(0, 0)) as r:
        r.open("https://login.taobao.com/", settle_ms=2000)
        end = time.time() + timeout_s
        while time.time() < end:
            time.sleep(5)
            try:
                url = r.page.url
            except Exception:
                return False
            if "login.taobao.com" not in url:
                text = r.open("https://www.taobao.com/", settle_ms=4000)
                if "亲，请登录" not in text:
                    print("Signed in: the bot's Taobao profile is ready.")
                    return True
                r.open("https://login.taobao.com/", settle_ms=2000)
    print("Not signed in within the time; run --setup again.")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--probe")
    a = ap.parse_args()
    if a.setup:
        sys.exit(0 if setup() else 1)
    if a.probe:
        res = read(a.probe, max_pages=1)
        print("status:", res["status"], "| notice:", res["notice"])
        print("cards:", len(res["cards"]), "| pages:", list(res["pages"]))
        for i, t in res["cards"][:3]:
            print(" ", i, t[:120])


if __name__ == "__main__":
    main()
