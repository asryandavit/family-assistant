"""Standalone diagnostic for the Wizz Air fare finder.

Run:  python debug_wizz.py

Opens a VISIBLE browser, loads the exact fare-finder URL, captures every JSON
response, and reports precisely why the main scraper bailed. Writes:
  .browser/discovery.json  - every JSON endpoint + preview
  .browser/debug.png       - screenshot of what the browser actually saw
  .browser/debug.html      - full page source

No dependencies on lib/ - fully standalone.
"""
import json
import os

from playwright.sync_api import sync_playwright

# Your real fare-finder URL shape, taken from the browser.
URL = ("https://www.wizzair.com/en-gb/flights/fare-finder/yerevan/anywhere"
       "/0/0/0/1/0/0/2026-08-01/2026-08-08?flexible=anytime&duration=1_week")

MARKERS = ["captcha", "verify you are human", "are you a robot",
           "px-captcha", "access denied", "unusual traffic"]

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, ".browser")
os.makedirs(OUT, exist_ok=True)


def main():
    captured = []

    with sync_playwright() as p:
        print("launching visible browser...")
        ctx = p.chromium.launch_persistent_context(
            os.path.join(OUT, "wizz"),
            headless=False,
            viewport={"width": 1400, "height": 950},
            locale="en-GB",
        )
        page = ctx.new_page()

        def on_response(resp):
            try:
                if "application/json" in resp.headers.get("content-type", ""):
                    captured.append({
                        "url": resp.url,
                        "status": resp.status,
                        "preview": resp.text()[:400],
                    })
            except Exception:
                pass

        page.on("response", on_response)

        print(f"navigating to:\n  {URL}\n")
        resp = page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        print(f"HTTP status: {resp.status if resp else 'no response'}")
        print(f"landed on:   {page.url}")
        print(f"page title:  {page.title()!r}")

        print("\nwaiting 15s for fares to load (watch the window)...")
        page.wait_for_timeout(15000)

        html = page.content()
        try:
            body_text = page.inner_text("body").lower()
        except Exception:
            body_text = ""

        page.screenshot(path=os.path.join(OUT, "debug.png"), full_page=True)
        with open(os.path.join(OUT, "debug.html"), "w", encoding="utf-8") as f:
            f.write(html)

        print("\n--- block-marker check ---")
        html_l = html.lower()
        for m in MARKERS:
            in_src = m in html_l
            in_vis = m in body_text
            if in_src or in_vis:
                where = "VISIBLE TEXT (likely real)" if in_vis else "html source only (probably false alarm)"
                print(f"  '{m}' found in {where}")
        if not any(m in html_l for m in MARKERS):
            print("  no markers at all - page is clean")

        print(f"\n--- captured {len(captured)} JSON responses ---")
        for c in captured:
            print(f"  [{c['status']}] {c['url'][:150]}")

        with open(os.path.join(OUT, "discovery.json"), "w", encoding="utf-8") as f:
            json.dump(captured, f, ensure_ascii=False, indent=2)

        print(f"\nwrote {OUT}\\discovery.json, debug.png, debug.html")
        input("\nPress Enter to close the browser...")
        ctx.close()


if __name__ == "__main__":
    main()
