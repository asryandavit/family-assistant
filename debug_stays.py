"""Discovery pass for Booking.com and Airbnb search pages.

Usage (visible browser, one site at a time):
    python debug_stays.py booking LCA 2026-11-04 2026-11-11
    python debug_stays.py airbnb  LCA 2026-11-04 2026-11-11

City may be an IATA code (mapped below) or a plain name: "Larnaca", "Bari".

Captures BOTH ways these sites ship data:
  1. JSON/GraphQL network responses
  2. JSON embedded in the HTML (__NEXT_DATA__, application/json scripts)

Writes .browser/stays_<site>.json (endpoint list + previews), a screenshot, and
the page HTML. Cookie banners are answered with the most privacy-preserving
option available (reject non-essential). Any visible bot wall is reported and
never clicked through.
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
                 "access denied", "please complete the security check",
                 "press and hold", "let's confirm you are human"]

REJECT_SELECTORS = [
    "#onetrust-reject-all-handler",
    "button#onetrust-reject-all-handler",
    "[data-testid='cookie-banner-decline']",
    "button:has-text('Decline')",
    "button:has-text('Reject')",
    "button:has-text('Only necessary')",
    "button:has-text('Necessary only')",
]


def url_for(site, city, ci, co):
    name = CITY.get(city.upper(), city)
    if site == "booking":
        return ("https://www.booking.com/searchresults.html?"
                f"ss={name}&checkin={ci}&checkout={co}"
                "&group_adults=2&group_children=1&age=2&no_rooms=1")
    return (f"https://www.airbnb.com/s/{name}/homes?"
            f"checkin={ci}&checkout={co}&adults=2&infants=1")


def main():
    if len(sys.argv) < 5:
        print(__doc__)
        return
    site, city, ci, co = sys.argv[1].lower(), sys.argv[2], sys.argv[3], sys.argv[4]
    os.makedirs(OUT, exist_ok=True)
    url = url_for(site, city, ci, co)
    captured = []

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            os.path.join(OUT, f"stays_{site}"),
            headless=False,
            viewport={"width": 1400, "height": 950},
            locale="en-GB",
        )
        page = ctx.new_page()

        def on_response(resp):
            try:
                ct = resp.headers.get("content-type", "")
                if "json" not in ct:
                    return
                body = resp.text()
                captured.append({"url": resp.url, "status": resp.status,
                                 "bytes": len(body), "preview": body[:500]})
            except Exception:
                pass

        page.on("response", on_response)

        print(f"\nnavigating:\n  {url}\n")
        r = page.goto(url, wait_until="domcontentloaded", timeout=90000)
        print(f"HTTP {r.status if r else '?'}  title={page.title()!r}")

        for sel in REJECT_SELECTORS:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=1500):
                    el.click(timeout=3000)
                    print(f"cookie banner: clicked {sel}")
                    page.wait_for_timeout(1500)
                    break
            except Exception:
                continue

        print("waiting 15s for results to render (watch the window)...")
        page.wait_for_timeout(15000)
        try:
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(4000)
        except Exception:
            pass

        html = page.content()
        try:
            visible = page.inner_text("body").lower()
        except Exception:
            visible = ""

        page.screenshot(path=os.path.join(OUT, f"stays_{site}.png"), full_page=False)
        with open(os.path.join(OUT, f"stays_{site}.html"), "w", encoding="utf-8") as f:
            f.write(html)

        print("\n--- block check (visible text only) ---")
        hits = [ph for ph in BLOCK_PHRASES if ph in visible]
        print("  BLOCKED: " + ", ".join(hits) if hits else "  clean")

        # embedded JSON blobs
        embedded = []
        for m in re.finditer(r'<script[^>]*type="application/json"[^>]*(?:id="([^"]*)")?[^>]*>(.{200,}?)</script>',
                             html, re.S):
            embedded.append({"id": m.group(1) or "(none)", "bytes": len(m.group(2)),
                             "preview": m.group(2)[:300]})
        for key in ("__NEXT_DATA__", "window.__INITIAL_STATE__", "data-deferred-state"):
            if key in html:
                embedded.append({"id": key, "bytes": html.count(key), "preview": "(marker present)"})

        print(f"\n--- {len(captured)} JSON responses (>2KB shown) ---")
        for c in sorted(captured, key=lambda x: -x["bytes"]):
            if c["bytes"] > 2000:
                print(f"  [{c['status']}] {c['bytes']:>8}B  {c['url'][:120]}")

        print(f"\n--- {len(embedded)} embedded JSON blobs ---")
        for e in sorted(embedded, key=lambda x: -x["bytes"])[:10]:
            print(f"  id={e['id'][:40]:40} {e['bytes']:>8}B")

        with open(os.path.join(OUT, f"stays_{site}.json"), "w", encoding="utf-8") as f:
            json.dump({"url": url, "network": captured, "embedded": embedded},
                      f, ensure_ascii=False, indent=2)
        print(f"\nwrote {OUT}\\stays_{site}.json / .png / .html")
        input("\nPress Enter to close the browser...")
        ctx.close()


if __name__ == "__main__":
    main()
