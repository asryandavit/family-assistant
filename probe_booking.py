"""Discover the endpoint behind Wizz's real booking search.

The fare finder is now understood: origin -> anywhere is a date-aware search,
origin -> a specific city is a lookup that returns one cheapest-ever fare and
ignores the dates. Neither can answer "flights on this route on these dates",
which is what /flights needs.

The booking search can. Rather than automate Wizz's custom form widgets (brittle),
this opens a browser, lets YOU perform the search by hand, and captures every JSON
response plus the resulting URL.

    python probe_booking.py

Then: search EVN -> Larnaca, out 18 Sep 2026, back 21 Sep 2026, 2 adults.
The script watches for up to 4 minutes and reports what it saw.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright

from lib import config

WATCH_SECONDS = 240
START = "https://www.wizzair.com/en-gb"

# Endpoints we already know about and do not need reported again.
KNOWN = ["asset/culture", "asset/country", "asset/map", "asset/initFeature",
         "usercentrics", "cookielaw", "googleadservices", "adtrafficquality",
         "sitecorecloud", "cdndex", "chunk-metadata", "c360-api"]

# Field names that suggest an actual flight search result rather than assets.
FARE_HINTS = ["outboundFlights", "returnFlights", "flightsOutbound", "fares",
              "flights", "departureDate", "carrierCode", "flightNumber",
              "priceType", "bundle", "isReturnFlight", "std"]


def interesting(url):
    return ("wizzair.com" in url) and not any(k in url for k in KNOWN)


def main():
    cfg = config.load()
    seen = {}

    print("\n" + "=" * 70)
    print("WIZZ BOOKING SEARCH DISCOVERY")
    print("=" * 70)
    print("""
A browser will open at wizzair.com. Do this by hand:

  1. Accept or decline cookies as you normally would.
  2. From: Yerevan      To: Larnaca
  3. Return trip, out 18 September 2026, back 21 September 2026
  4. 2 adults
  5. Press Search and WAIT for the flight results to appear.
  6. If a date has no flights, note that and try 19 or 20 September.

Everything is captured while you work. Watching for %d seconds.
""" % WATCH_SECONDS)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            os.path.join(cfg["_root"], cfg["wizz"]["profile_dir"]),
            headless=False, locale="en-GB",
            viewport={"width": 1400, "height": 950})
        page = ctx.new_page()

        def on_response(resp):
            try:
                ct = resp.headers.get("content-type", "")
                if "json" not in ct or not interesting(resp.url):
                    return
                body = resp.text()
                key = resp.url.split("?")[0]
                hits = [h for h in FARE_HINTS if h in body]
                prev = seen.get(key)
                if prev is None or len(body) > prev["bytes"]:
                    seen[key] = {"url": resp.url, "bytes": len(body),
                                 "status": resp.status, "hints": hits,
                                 "preview": body[:1500]}
            except Exception:
                pass

        page.on("response", on_response)
        page.goto(START, wait_until="domcontentloaded", timeout=90000)

        # Poll rather than block on input(): sync Playwright only dispatches
        # events while a page method is running.
        elapsed, last_url, last_count = 0, page.url, 0
        while elapsed < WATCH_SECONDS:
            page.wait_for_timeout(2000)
            elapsed += 2
            if page.url != last_url:
                last_url = page.url
                print("  [%3ds] navigated: %s" % (elapsed, last_url[:100]))
            if len(seen) != last_count:
                last_count = len(seen)
                print("  [%3ds] %d endpoint(s) captured" % (elapsed, last_count))
            if elapsed % 60 == 0:
                print("  [%3ds] still watching..." % elapsed)

        final_url = page.url
        try:
            page.screenshot(path=os.path.join(cfg["_root"], ".browser",
                                              "booking_result.png"))
        except Exception:
            pass
        ctx.close()

    print("\n" + "=" * 70)
    print("FINAL URL")
    print("  %s" % final_url)

    ranked = sorted(seen.values(), key=lambda x: -len(x["hints"]))
    print("\nCAPTURED ENDPOINTS (most fare-like first)")
    for s in ranked:
        print("\n  [%s] %8dB  hints: %s" %
              (s["status"], s["bytes"], ", ".join(s["hints"][:6]) or "none"))
        print("  %s" % s["url"][:150])
        if s["hints"]:
            print("  preview: %s" % s["preview"][:300].replace("\n", " "))

    path = os.path.join(cfg["_root"], ".browser", "probe_booking.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"final_url": final_url, "endpoints": ranked},
                  f, ensure_ascii=False, indent=2)
    print("\n  wrote %s" % path)
    print("  screenshot: .browser\\booking_result.png")


if __name__ == "__main__":
    main()
