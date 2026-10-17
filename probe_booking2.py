"""Find the booking-search URL format without doing a manual search.

Clicking a fare on the fare-finder page navigates into the booking flow, so the
booking URL format is already present in that page's markup. Extract it, then
follow one to capture the endpoint that actually answers "flights on this route
on these dates" -- the thing the fare finder cannot do.

    python probe_booking2.py                  # EVN -> LCA
    python probe_booking2.py larnaca 2026-09-18 2026-09-21

Fully automatic. Visible browser. Never clicks through a verification page.
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

KNOWN = ["asset/culture", "asset/country", "asset/map", "asset/initFeature",
         "usercentrics", "cookielaw", "googleadservices", "adtrafficquality",
         "sitecorecloud", "cdndex", "chunk-metadata", "c360-api", "cms/api",
         "asset/emergencyNews", "asset/yellowRibbon", "dist/builds"]

FARE_HINTS = ["outboundFlights", "returnFlights", "flightsOutbound", "fares",
              "flightNumber", "carrierCode", "departureDate", "bundle",
              "priceType", "flightList", "flights"]


def interesting(url):
    return "wizzair.com" in url and not any(k in url for k in KNOWN)


def main():
    a = sys.argv[1:]
    dest = a[0] if len(a) > 0 else "larnaca"
    d_out = a[1] if len(a) > 1 else "2026-09-18"
    d_back = a[2] if len(a) > 2 else "2026-09-21"

    cfg = config.load()
    ff = ("https://www.wizzair.com/en-gb/flights/fare-finder/yerevan/%s"
          "/0/0/0/1/0/0/%s/%s?flexible=anytime&duration=1_week"
          % (dest, d_out, d_back))

    seen, links = {}, set()

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            os.path.join(cfg["_root"], cfg["wizz"]["profile_dir"]),
            headless=False, locale="en-GB",
            viewport={"width": 1400, "height": 950})
        page = ctx.new_page()

        def on_response(resp):
            try:
                if "json" not in resp.headers.get("content-type", ""):
                    return
                if not interesting(resp.url):
                    return
                body = resp.text()
                hits = [h for h in FARE_HINTS if h in body]
                key = resp.url.split("?")[0]
                prev = seen.get(key)
                if prev is None or len(body) > prev["bytes"]:
                    seen[key] = {"url": resp.url, "status": resp.status,
                                 "bytes": len(body), "hints": hits,
                                 "preview": body[:1200]}
            except Exception:
                pass

        page.on("response", on_response)

        print("\n[1] fare finder page")
        print("    %s" % ff)
        page.goto(ff, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(9000)

        try:
            visible = page.inner_text("body").lower()
        except Exception:
            visible = ""
        if any(b in visible for b in BLOCK):
            print("    BLOCKED -- stopping")
            ctx.close()
            return

        # every anchor, plus any booking-shaped path in the raw markup
        try:
            hrefs = page.eval_on_selector_all(
                "a[href]", "els => els.map(e => e.href)")
        except Exception:
            hrefs = []
        html = page.content()
        for h in hrefs:
            if "booking" in h or "select-flight" in h:
                links.add(h)
        for m in re.finditer(r'"(/[a-z\-]{2,6}/booking/[^"\']{5,160})"', html):
            links.add("https://www.wizzair.com" + m.group(1))
        for m in re.finditer(r'(https://[^"\']*?/booking/[^"\']{5,160})', html):
            links.add(m.group(1))

        print("\n[2] booking-shaped links found in the page: %d" % len(links))
        for l in sorted(links)[:12]:
            print("    %s" % l[:150])

        target = None
        for l in sorted(links, key=len, reverse=True):
            if "select-flight" in l or re.search(r"\d{4}-\d{2}-\d{2}", l):
                target = l
                break
        if not target and links:
            target = sorted(links, key=len, reverse=True)[0]

        if target:
            print("\n[3] following the most specific one")
            print("    %s" % target)
            seen.clear()
            try:
                r = page.goto(target, wait_until="domcontentloaded", timeout=90000)
                page.wait_for_timeout(12000)
                print("    http %s  landed: %s" % (r.status if r else "?",
                                                   page.url[:130]))
                print("    title: %r" % page.title()[:70])
            except Exception as e:
                print("    failed: %s" % str(e)[:90])
        else:
            print("\n[3] no booking link in the markup -- the fare cards likely")
            print("    navigate via JavaScript rather than an href.")
            print("    Clicking the cheapest fare card instead.")
            for sel in ["[data-test*='fare']", "[class*='fare-finder'] a",
                        "[class*='result'] button", "button:has-text('Select')"]:
                try:
                    el = page.locator(sel).first
                    if el.count():
                        el.click(timeout=5000)
                        page.wait_for_timeout(12000)
                        print("    clicked %s -> %s" % (sel, page.url[:110]))
                        break
                except Exception:
                    continue

        final = page.url
        try:
            page.screenshot(path=os.path.join(cfg["_root"], ".browser",
                                              "booking2.png"))
        except Exception:
            pass
        ctx.close()

    print("\n" + "=" * 70)
    print("FINAL URL\n  %s" % final)
    ranked = sorted(seen.values(), key=lambda x: (-len(x["hints"]), -x["bytes"]))
    print("\nENDPOINTS SEEN ON THE BOOKING PAGE (most fare-like first)")
    for s in ranked[:8]:
        print("\n  [%s] %8dB  hints: %s" %
              (s["status"], s["bytes"], ", ".join(s["hints"][:6]) or "none"))
        print("  %s" % s["url"][:160])
        if s["hints"]:
            print("  %s" % s["preview"][:280].replace("\n", " "))

    path = os.path.join(cfg["_root"], ".browser", "probe_booking2.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"fare_finder": ff, "links": sorted(links),
                   "final_url": final, "endpoints": ranked},
                  f, ensure_ascii=False, indent=2)
    print("\n  wrote %s" % path)


if __name__ == "__main__":
    main()
