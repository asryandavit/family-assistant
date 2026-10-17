"""Why does a specific-route fare-finder query ignore the date window?

Observed: EVN -> anywhere for 18-21 Sep returned 18 fares inside the window, but
NAP -> EVN for the same window returned a fare in November.

Hypothesis: our URL always carries flexible=anytime and duration=1_week. On a
four-day window those are contradictory -- a one-week trip cannot fit -- so Wizz
discards the window and answers "cheapest on this route, whenever" instead.

This tries the parameter combinations and reports, for each, whether ANY result
falls inside the requested window. That single column is the answer.

    python probe_params.py                        # LCA->EVN, 18-21 Sep
    python probe_params.py LCA EVN 2026-09-18 2026-09-21

Visible browser. Never clicks through a verification page.
"""
import json
import os
import random
import sys
import time
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright

from lib import config

MATCH = "SmartSearchCheapFlightsV2"
BLOCK = ["verify you are human", "are you a robot", "unusual traffic",
         "access denied", "press and hold", "confirm you are human"]

BASE = "https://www.wizzair.com/en-gb/flights/fare-finder/{o}/{d}/0/0/0/1/0/0/{f}/{t}"

# Ordered cheapest-hypothesis-first. None means the parameter is omitted entirely.
VARIANTS = [
    ("no params at all",            None,       None),
    ("duration omitted",            "anytime",  None),
    ("flexible omitted",            None,       "1_week"),
    ("current: anytime + 1_week",   "anytime",  "1_week"),
    ("exact dates",                 "exact",    None),
    ("flexible=off",                "off",      None),
    ("flexible=false",              "false",    None),
    ("weekend duration",            "anytime",  "weekend"),
    ("3-day duration",              "anytime",  "3_days"),
]


def build(o, d, f, t, flexible, duration):
    url = BASE.format(o=o, d=d, f=f, t=t)
    q = []
    if flexible is not None:
        q.append("flexible=%s" % flexible)
    if duration is not None:
        q.append("duration=%s" % duration)
    return url + ("?" + "&".join(q) if q else "")


def dates_from(payloads):
    out = []
    for p in payloads:
        for i in (p.get("items") or []):
            for leg in ("outboundFlight", "returnFlight"):
                std = ((i.get(leg) or {}).get("std") or "")
                if std:
                    out.append(std[:10])
    return out


def main():
    a = sys.argv[1:]
    origin = a[0] if len(a) > 0 else "LCA"
    dest = a[1] if len(a) > 1 else "EVN"
    d_from = a[2] if len(a) > 2 else "2026-09-18"
    d_to = a[3] if len(a) > 3 else "2026-09-21"

    cfg = config.load()
    lo, hi = date.fromisoformat(d_from), date.fromisoformat(d_to)
    results = []
    captured = []

    print("\nroute %s -> %s   window %s .. %s" % (origin, dest, d_from, d_to))
    print("question: does ANY returned fare fall inside that window?\n")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            os.path.join(cfg["_root"], cfg["wizz"]["profile_dir"]),
            headless=False, locale="en-GB",
            viewport={"width": 1400, "height": 950})
        page = ctx.new_page()

        def on_response(resp):
            try:
                if MATCH in resp.url and "json" in resp.headers.get("content-type", ""):
                    captured.append(resp.json())
            except Exception:
                pass

        page.on("response", on_response)

        for label, flexible, duration in VARIANTS:
            captured.clear()
            url = build(origin, dest, d_from, d_to, flexible, duration)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=90000)
            except Exception as e:
                print("  %-28s navigation failed: %s" % (label, str(e)[:40]))
                continue
            page.wait_for_timeout(8500)

            try:
                visible = page.inner_text("body").lower()
            except Exception:
                visible = ""
            if any(b in visible for b in BLOCK):
                print("  %-28s BLOCKED -- stopping" % label)
                break

            ds = dates_from(list(captured))
            inside = [x for x in ds if lo <= date.fromisoformat(x) <= hi]
            verdict = "IN WINDOW (%d)" % len(inside) if inside else "ignored window"
            span = "%s..%s" % (min(ds), max(ds)) if ds else "no fares"
            print("  %-28s %-16s %-24s %s"
                  % (label, "%d fare(s)" % len(ds), span, verdict))
            results.append({"variant": label, "flexible": flexible,
                            "duration": duration, "url": url,
                            "fares": len(ds), "span": span,
                            "inside_window": len(inside)})
            time.sleep(random.uniform(2, 4))

        # cheap re-check: does the reverse "anywhere" form work at all?
        print("\n  re-checking anywhere -> yerevan (reported as broken earlier)")
        captured.clear()
        url = build("anywhere", "yerevan", d_from, d_to, "anytime", "1_week")
        try:
            r = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(8000)
            ds = dates_from(list(captured))
            print("    http %s  title=%r  fares=%d"
                  % (r.status if r else "?", page.title()[:50], len(ds)))
            print("    landed: %s" % page.url[:110])
        except Exception as e:
            print("    failed: %s" % str(e)[:70])

        ctx.close()

    path = os.path.join(cfg["_root"], ".browser", "probe_params.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    winners = [r for r in results if r["inside_window"]]
    print("\n  variants that respected the window: %s"
          % (", ".join(r["variant"] for r in winners) if winners else "NONE"))
    print("  wrote %s" % path)
    input("\nPress Enter to close the browser...")


if __name__ == "__main__":
    main()
