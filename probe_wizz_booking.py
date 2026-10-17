"""Can Playwright read the Wizz booking page, and where are the fares?

Claude in Chrome reached this page fine, but that was a human browsing with a
warmed profile. A scripted browser may get a WAF challenge instead, and the fares
may live only in the DOM rather than in an interceptable JSON response. Both
questions decide how /flights is built, so neither is guessed.

    python probe_wizz_booking.py
    python probe_wizz_booking.py EVN LCA 2026-09-18 2026-09-21
    python probe_wizz_booking.py NAP EVN 2026-09-21 null      # one-way

URL format, confirmed by hand:
  /booking/select-flight/{FROM}/{TO}/{DATE}/{RETURN|null}/{adults}/{children}/{infants}/null

Visible browser, reusing the existing warmed Wizz profile. Never clicks through a
verification page.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright

from lib import config

BLOCK = ["verify you are human", "are you a robot", "unusual traffic",
         "access denied", "press and hold", "confirm you are human"]

# Field names that would mark a real flight-search payload.
HINTS = ["flightNumber", "carrierCode", "departureDate", "departureStation",
         "arrivalStation", "fares", "bundle", "priceType", "outboundFlights",
         "returnFlights", "flightsOutbound", "discountedPrice", "std"]

SKIP = ["asset/culture", "asset/country", "asset/map", "asset/initFeature",
        "usercentrics", "cookielaw", "googleadservices", "adtrafficquality",
        "sitecorecloud", "cdndex", "chunk-metadata", "c360-api", "cms/api",
        "emergencyNews", "yellowRibbon", "dist/builds", "serviceFees",
        "chatbot/getParameters"]

BASE = ("https://www.wizzair.com/en-gb/booking/select-flight"
        "/{f}/{t}/{d1}/{d2}/{a}/{c}/{i}/null")


def main():
    a = sys.argv[1:]
    frm = (a[0] if len(a) > 0 else "EVN").upper()
    to = (a[1] if len(a) > 1 else "LCA").upper()
    d1 = a[2] if len(a) > 2 else "2026-09-18"
    d2 = a[3] if len(a) > 3 else "2026-09-21"
    adults, children, infants = 2, 0, 1

    cfg = config.load()
    url = BASE.format(f=frm, t=to, d1=d1, d2=d2, a=adults, c=children, i=infants)
    seen, captured = {}, []

    print("\n" + "=" * 72)
    print("WIZZ BOOKING PAGE FROM PLAYWRIGHT")
    print("=" * 72)
    print("  %s" % url)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            os.path.join(cfg["_root"], cfg["wizz"]["profile_dir"]),
            headless=False, locale="en-GB",
            viewport={"width": 1400, "height": 950})
        ctx.add_cookies([{"name": "cur_curr", "value": "USD",
                          "domain": ".wizzair.com", "path": "/"}])
        page = ctx.new_page()

        def on_response(resp):
            try:
                if "json" not in resp.headers.get("content-type", ""):
                    return
                if "wizzair.com" not in resp.url or any(s in resp.url for s in SKIP):
                    return
                body = resp.text()
                hits = [h for h in HINTS if h in body]
                key = resp.url.split("?")[0]
                prev = seen.get(key)
                if prev is None or len(body) > prev["bytes"]:
                    seen[key] = {"url": resp.url, "status": resp.status,
                                 "bytes": len(body), "hints": hits,
                                 "preview": body[:1500]}
                if hits:
                    captured.append(body)
            except Exception:
                pass

        page.on("response", on_response)

        # warm the session first: going straight to a deep page is what tripped
        # Booking's WAF, and the same precaution costs little here
        print("\n[1] warming on the homepage")
        page.goto("https://www.wizzair.com/en-gb", wait_until="domcontentloaded",
                  timeout=90000)
        page.wait_for_timeout(4000)

        print("[2] loading the booking page")
        r = page.goto(url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(14000)

        try:
            visible = page.inner_text("body")
        except Exception:
            visible = ""
        low = visible.lower()

        print("\n[3] page state")
        print("    http %s" % (r.status if r else "?"))
        print("    title  %r" % page.title()[:70])
        print("    landed %s" % page.url[:120])
        print("    visible text %d chars" % len(visible))
        hit = next((b for b in BLOCK if b in low), None)
        print("    BLOCKED: %r" % hit if hit else "    no block phrases")

        # do prices appear anywhere in the rendered text?
        money = re.findall(r"(?:US\$|\$|\u20ac|EUR|USD)\s?\d[\d ,.]*", visible)
        print("    money-like strings in visible text: %d %s"
              % (len(money), money[:8]))

        print("\n[4] site JSON responses")
        ranked = sorted(seen.values(), key=lambda x: (-len(x["hints"]), -x["bytes"]))
        if not ranked:
            print("    none captured")
        for s in ranked[:6]:
            print("\n    [%s] %8dB  hints: %s"
                  % (s["status"], s["bytes"], ", ".join(s["hints"][:7]) or "none"))
            print("    %s" % s["url"][:150])
            if s["hints"]:
                print("    %s" % s["preview"][:400].replace("\n", " "))

        print("\n[5] DOM fallback probe")
        for label, sel in [("flight rows", "[class*='flight-select']"),
                           ("fare cards", "[data-test*='flight']"),
                           ("price nodes", "[class*='price']"),
                           ("date strip", "[class*='date-picker'], [class*='calendar']")]:
            try:
                n = page.locator(sel).count()
            except Exception:
                n = -1
            print("    %-12s %-42s %s" % (label, sel, n))

        html = page.content()
        with open(os.path.join(cfg["_root"], ".browser", "booking_page.html"),
                  "w", encoding="utf-8") as f:
            f.write(html)
        try:
            page.screenshot(path=os.path.join(cfg["_root"], ".browser",
                                              "booking_page.png"))
        except Exception:
            pass
        ctx.close()

    out = os.path.join(cfg["_root"], ".browser", "probe_wizz_booking.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"url": url, "endpoints": ranked}, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 72)
    print("VERDICT")
    fare_ep = [s for s in ranked if len(s["hints"]) >= 3]
    if hit:
        print("  BLOCKED -- Playwright does not get the page a human gets.")
    elif fare_ep:
        print("  Fares available as JSON. Best endpoint:")
        print("    %s" % fare_ep[0]["url"][:140])
    elif money:
        print("  No fare JSON, but prices ARE in the rendered DOM.")
        print("  /flights would parse the DOM instead -- workable, more fragile.")
    else:
        print("  Neither JSON nor visible prices. Page may not have finished")
        print("  rendering; check .browser\\booking_page.png")
    print("\n  wrote %s" % out)
    print("  html + screenshot in .browser\\")


if __name__ == "__main__":
    main()
