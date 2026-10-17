"""Probe the Wizz fare finder for a specific city pair, before building /flights.

Four questions, none of which should be guessed:

  1. Which `duration` values does the fare finder accept? We have only ever used
     1_week. If it takes others, trip-length search comes almost free.
  2. Does origin -> a SPECIFIC destination return PAIRED return flights
     (isReturnFlight true, with both outboundFlight and returnFlight), or only
     one-ways as EVN -> anywhere did?
  3. What do the six digits in the URL path mean? The template carries
     /0/0/0/1/0/0/ and we never decoded it. If those are passenger counts, we
     can ask for 2 adults + 1 infant directly instead of multiplying afterwards.
  4. How does a wide date window behave -- options spread across the range, or
     only the cheapest?

Usage:
    python probe_flights.py                 # EVN -> BUD, next full month
    python probe_flights.py BUD 2026-11-01 2026-11-30

Visible browser. Writes .browser/probe_flights.json plus a printed summary.
Any visible verification page is reported and never clicked through.
"""
import calendar
import json
import os
import sys
from datetime import date

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, ".browser")
MATCH = "SmartSearchCheapFlightsV2"

BLOCK_PHRASES = ["verify you are human", "are you a robot", "unusual traffic",
                 "access denied", "press and hold", "confirm you are human"]

BASE = ("https://www.wizzair.com/en-gb/flights/fare-finder/{origin}/{dest}"
        "/{pax}/{date_from}/{date_to}?flexible=anytime&duration={duration}")

# Guesses follow the one value we know works (1_week). The DOM scan below is
# the authoritative answer; this list just shows which ones return fares.
DURATIONS = ["1_week", "2_weeks", "3_weeks", "1_month", "weekend",
             "long_weekend", "3_days", "4_days", "5_days", "10_days", "any"]

# The six path digits, unchanged vs. a variant with 2 adults + 1 infant IF the
# positions mean what they appear to.
PAX_VARIANTS = {
    "as-used-today": "0/0/0/1/0/0",
    "guess-2adults-1infant": "0/0/0/2/0/1",
    "guess-2adults-1child": "0/0/0/2/1/0",
}


def next_month_window():
    t = date.today()
    y, m = (t.year + 1, 1) if t.month == 12 else (t.year, t.month + 1)
    return date(y, m, 1).isoformat(), date(y, m, calendar.monthrange(y, m)[1]).isoformat()


def summarize(payloads):
    """What came back: how many items, paired or one-way, date span, prices."""
    items = []
    for p in payloads:
        items += (p.get("items") or [])
    if not items:
        return {"items": 0}

    paired = sum(1 for i in items if i.get("isReturnFlight") and i.get("returnFlight"))
    dates, prices, currencies = [], [], set()
    for i in items:
        ob = i.get("outboundFlight") or {}
        std = ob.get("std") or ""
        if std:
            dates.append(std[:10])
        pr = ((ob.get("regularPrice") or {}).get("amount"))
        if isinstance(pr, (int, float)):
            prices.append(round(float(pr), 2))
        cur = (ob.get("regularPrice") or {}).get("currencyCode")
        if cur:
            currencies.add(cur)

    out = {
        "items": len(items),
        "paired_returns": paired,
        "oneways": len(items) - paired,
        "date_span": "%s .. %s" % (min(dates), max(dates)) if dates else "-",
        "distinct_dates": len(set(dates)),
        "price_range": "%s .. %s" % (min(prices), max(prices)) if prices else "-",
        "currencies": sorted(currencies),
    }
    if paired:
        ex = next(i for i in items if i.get("isReturnFlight") and i.get("returnFlight"))
        ob, rb = ex.get("outboundFlight") or {}, ex.get("returnFlight") or {}
        out["paired_example"] = {
            "out": "%s->%s %s" % (ob.get("departureStation"), ob.get("arrivalStation"),
                                  (ob.get("std") or "")[:10]),
            "back": "%s->%s %s" % (rb.get("departureStation"), rb.get("arrivalStation"),
                                   (rb.get("std") or "")[:10]),
            "out_price": (ob.get("regularPrice") or {}).get("amount"),
            "back_price": (rb.get("regularPrice") or {}).get("amount"),
        }
    return out


def main():
    # The fare finder accepts either an IATA code (BUD) or a lowercase city
    # slug (budapest). Three letters is treated as a code, anything longer as
    # a slug -- uppercasing a slug breaks the URL.
    raw = sys.argv[1] if len(sys.argv) > 1 else "BUD"
    dest = raw.upper() if (len(raw) == 3 and raw.isalpha()) else raw.strip().lower()
    if len(sys.argv) > 3:
        d_from, d_to = sys.argv[2], sys.argv[3]
    else:
        d_from, d_to = next_month_window()
    origin = "EVN"
    os.makedirs(OUT, exist_ok=True)

    results = {"route": "%s->%s" % (origin, dest), "window": [d_from, d_to],
               "durations": {}, "pax": {}, "dom_duration_options": []}
    captured = []

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            os.path.join(OUT, "wizz"), headless=False, locale="en-GB",
            viewport={"width": 1400, "height": 950})
        page = ctx.new_page()

        def on_response(resp):
            try:
                if MATCH in resp.url and "json" in resp.headers.get("content-type", ""):
                    captured.append(resp.json())
            except Exception:
                pass

        page.on("response", on_response)

        def visit(url, label):
            captured.clear()
            print("\n  %s" % label)
            print("    %s" % url)
            try:
                r = page.goto(url, wait_until="domcontentloaded", timeout=90000)
                status = r.status if r else "?"
            except Exception as e:
                print("    navigation failed: %s" % str(e)[:80])
                return {"error": str(e)[:120]}
            page.wait_for_timeout(9000)
            try:
                visible = page.inner_text("body").lower()
            except Exception:
                visible = ""
            hit = next((ph for ph in BLOCK_PHRASES if ph in visible), None)
            if hit:
                print("    BLOCKED: %r -- stopping" % hit)
                return {"blocked": hit}
            s = summarize(list(captured))
            s["http"] = status
            s["landed"] = page.url[:120]
            print("    http %s  items=%s paired=%s oneway=%s  dates=%s  %s"
                  % (status, s.get("items"), s.get("paired_returns"),
                     s.get("oneways"), s.get("date_span"), s.get("price_range")))
            return s

        # ---- 1 & 2 & 4: duration values, pairing, date spread ----
        print("\n=== DURATION VALUES ===")
        for dur in DURATIONS:
            url = BASE.format(origin=origin, dest=dest, pax=PAX_VARIANTS["as-used-today"],
                              date_from=d_from, date_to=d_to, duration=dur)
            results["durations"][dur] = visit(url, "duration=%s" % dur)
            if results["durations"][dur].get("blocked"):
                break

        # ---- read the page's own duration control, which is authoritative ----
        print("\n=== DOM DURATION CONTROL ===")
        try:
            opts = page.eval_on_selector_all(
                "select option, [role='option'], [data-test*='duration'] *",
                "els => els.map(e => (e.value||'') + '|' + (e.textContent||'').trim())"
                ".filter(t => t.length > 1).slice(0, 60)")
            results["dom_duration_options"] = opts
            for o in opts[:25]:
                print("    %s" % o[:90])
            if not opts:
                print("    (nothing matched -- the control may be custom markup)")
        except Exception as e:
            print("    could not read: %s" % str(e)[:80])

        # ---- 3: what the six path digits do ----
        print("\n=== PASSENGER PATH DIGITS ===")
        for label, pax in PAX_VARIANTS.items():
            url = BASE.format(origin=origin, dest=dest, pax=pax,
                              date_from=d_from, date_to=d_to, duration="1_week")
            results["pax"][label] = visit(url, "%s  (%s)" % (label, pax))
            if results["pax"][label].get("blocked"):
                break

        with open(os.path.join(OUT, "probe_flights.json"), "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print("\n=== SUMMARY ===")
        good = [d for d, r in results["durations"].items() if r.get("items")]
        print("  durations returning fares: %s" % (", ".join(good) or "none"))
        anypair = any(r.get("paired_returns") for r in results["durations"].values())
        print("  paired return flights seen: %s" % ("YES" if anypair else "no - one-ways only"))
        base = results["pax"].get("as-used-today", {}).get("price_range")
        for label, r in results["pax"].items():
            same = "same as baseline" if r.get("price_range") == base else "DIFFERENT"
            print("  pax %-22s %s  (%s)" % (label, r.get("price_range"), same))
        print("\n  wrote %s\\probe_flights.json" % OUT)
        input("\nPress Enter to close the browser...")
        ctx.close()


if __name__ == "__main__":
    main()
