"""Discovery pass v2 for Booking.com / Airbnb.

Changes vs v1, all aimed at the AWS WAF 202 challenge:
  1. Warms the session on the site homepage first (jumping straight to a deep
     search URL is what trips WAF hardest), handles cookies there.
  2. Waits for REAL result cards to appear instead of a fixed sleep, so we can
     say definitively whether results rendered.
  3. Optional mobile emulation (--mobile) to surface Booking Mobile Rates.
  4. Sets currency via cookie + URL param.

Usage:
    python debug_stays2.py booking LCA 2026-11-04 2026-11-11
    python debug_stays2.py booking LCA 2026-11-04 2026-11-11 --mobile
    python debug_stays2.py airbnb  LCA 2026-11-04 2026-11-11

Any visible verification wall is reported and never clicked through.
"""
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, ".browser")

CITY = {
    "LCA": "Larnaca", "BRI": "Bari", "NAP": "Naples", "BUD": "Budapest",
    "OTP": "Bucharest", "BTS": "Bratislava", "PRG": "Prague", "VCE": "Venice",
    "FCO": "Rome", "MXP": "Milan", "RHO": "Rhodes", "HAM": "Hamburg",
    "EIN": "Eindhoven", "CRL": "Brussels", "DTM": "Dortmund", "FMM": "Memmingen",
    "BVA": "Paris", "LTN": "London",
}

BLOCK_PHRASES = ["verify you are human", "are you a robot", "unusual traffic",
                 "access denied", "security check", "press and hold",
                 "confirm you are human", "enable javascript"]

COOKIE_SELECTORS = [
    "#onetrust-reject-all-handler",
    "[data-testid='cookie-banner'] button:has-text('Decline')",
    "button:has-text('Decline optional')",
    "button:has-text('Reject all')",
    "button:has-text('Only necessary')",
    "button[aria-label*='Decline']",
    "button:has-text('Accept')",           # last resort: unblock rendering
    "#onetrust-accept-btn-handler",
]

RESULT_SELECTORS = {
    "booking": ["[data-testid='property-card']", "[data-testid='title']"],
    "airbnb": ["[itemprop='itemListElement']", "[data-testid='card-container']"],
}

HOME = {"booking": "https://www.booking.com/", "airbnb": "https://www.airbnb.com/"}


def url_for(site, city, ci, co):
    name = CITY.get(city.upper(), city)
    if site == "booking":
        return ("https://www.booking.com/searchresults.html?"
                f"ss={name}&checkin={ci}&checkout={co}"
                "&group_adults=2&group_children=1&age=2&no_rooms=1"
                "&selected_currency=USD")
    return (f"https://www.airbnb.com/s/{name}/homes?"
            f"checkin={ci}&checkout={co}&adults=2&infants=1")


def dismiss_cookies(page, label):
    for sel in COOKIE_SELECTORS:
        try:
            el = page.locator(sel).first
            if el.count() and el.is_visible(timeout=2500):
                el.click(timeout=4000)
                print(f"  [{label}] cookie banner: clicked {sel}")
                page.wait_for_timeout(2000)
                return True
        except Exception:
            continue
    print(f"  [{label}] no cookie banner matched")
    return False


def main():
    if len(sys.argv) < 5:
        print(__doc__)
        return
    site, city, ci, co = sys.argv[1].lower(), sys.argv[2], sys.argv[3], sys.argv[4]
    mobile = "--mobile" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    tag = f"{site}{'_mobile' if mobile else ''}"
    captured = []

    with sync_playwright() as p:
        device = p.devices["iPhone 13"] if mobile else {}
        opts = dict(headless=False, locale="en-GB")
        if mobile:
            opts.update({k: v for k, v in device.items() if k != "default_browser_type"})
        else:
            opts["viewport"] = {"width": 1400, "height": 950}

        ctx = p.chromium.launch_persistent_context(
            os.path.join(OUT, f"stays_{tag}"), **opts)

        ctx.add_cookies([{"name": "cur_curr", "value": "USD",
                          "domain": ".booking.com", "path": "/"}])

        page = ctx.new_page()

        def on_response(resp):
            try:
                if "json" not in resp.headers.get("content-type", ""):
                    return
                body = resp.text()
                captured.append({"url": resp.url, "status": resp.status,
                                 "bytes": len(body), "preview": body[:600]})
            except Exception:
                pass

        page.on("response", on_response)

        # --- 1. warm the session on the homepage ---
        print(f"\n[1] warming session: {HOME[site]}  (mobile={mobile})")
        r0 = page.goto(HOME[site], wait_until="domcontentloaded", timeout=90000)
        print(f"  HTTP {r0.status if r0 else '?'}  title={page.title()!r}")
        page.wait_for_timeout(4000)
        dismiss_cookies(page, "home")
        page.wait_for_timeout(3000)

        # --- 2. now the search ---
        url = url_for(site, city, ci, co)
        print(f"\n[2] search:\n  {url}")
        r = page.goto(url, wait_until="domcontentloaded", timeout=90000)
        print(f"  HTTP {r.status if r else '?'}  title={page.title()!r}")
        dismiss_cookies(page, "search")

        # --- 3. wait for REAL cards, not a fixed sleep ---
        print("\n[3] waiting up to 60s for result cards...")
        found = None
        for sel in RESULT_SELECTORS[site]:
            try:
                page.wait_for_selector(sel, timeout=60000, state="attached")
                found = sel
                break
            except Exception:
                continue
        n_cards = page.locator(found).count() if found else 0
        print(f"  cards: {n_cards}" + (f" via {found}" if found else "  (NONE FOUND)"))

        page.wait_for_timeout(5000)
        try:
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(4000)
        except Exception:
            pass

        html = page.content()
        try:
            visible = page.inner_text("body").lower()
        except Exception:
            visible = ""

        print(f"\n[4] final state:  url={page.url[:110]}")
        print(f"  title={page.title()!r}  html={len(html)}B  visible_text={len(visible)}B")
        hits = [ph for ph in BLOCK_PHRASES if ph in visible]
        print("  BLOCK: " + ", ".join(hits) if hits else "  block phrases: none")

        page.screenshot(path=os.path.join(OUT, f"stays_{tag}.png"))
        with open(os.path.join(OUT, f"stays_{tag}.html"), "w", encoding="utf-8") as f:
            f.write(html)

        embedded = []
        for m in re.finditer(
                r'<script[^>]*type="application/json"[^>]*?(?:id="([^"]*)")?[^>]*>(.{500,}?)</script>',
                html, re.S):
            embedded.append({"id": m.group(1) or "(none)", "bytes": len(m.group(2)),
                             "preview": m.group(2)[:300]})
        for key in ("__NEXT_DATA__", "data-deferred-state", "window.booking",
                    "niobeMinimalClientData", "b_search_results"):
            if key in html:
                embedded.append({"id": f"marker:{key}", "bytes": html.count(key),
                                 "preview": "(present)"})

        print(f"\n[5] {len(captured)} JSON responses (site-owned, >2KB):")
        host = "booking.com" if site == "booking" else "airbnb.com"
        for c in sorted(captured, key=lambda x: -x["bytes"]):
            if c["bytes"] > 2000 and host in c["url"]:
                print(f"  [{c['status']}] {c['bytes']:>8}B  {c['url'][:120]}")

        print(f"\n[6] {len(embedded)} embedded JSON blobs/markers:")
        for e in sorted(embedded, key=lambda x: -x["bytes"])[:12]:
            print(f"  {e['id'][:45]:45} {e['bytes']:>8}B")

        with open(os.path.join(OUT, f"stays_{tag}.json"), "w", encoding="utf-8") as f:
            json.dump({"url": url, "cards": n_cards, "network": captured,
                       "embedded": embedded}, f, ensure_ascii=False, indent=2)
        print(f"\nwrote {OUT}\\stays_{tag}.json / .png / .html")
        input("\nPress Enter to close the browser...")
        ctx.close()


if __name__ == "__main__":
    main()
