"""Targeted Wizz search for one specific date window. A manual precursor to /flights.

Answers questions the daily scan cannot, because the scan stores only the cheapest
date per destination per month:

    python quickflights.py --depart-after 2026-09-18T19:00 --return-by 2026-09-21

"18 September after 19:00, or the 19th" is one constraint, not two: any flight on
the 19th is automatically after 18 Sep 19:00.

Reuses the proven parser and currency normaliser; does its own browsing so nothing
in the working daily job is touched. Visible browser. Never clicks through a
verification page.
"""
import argparse
import os
import random
import sys
import time
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright

from lib import config, parse_wizz

BLOCK_PHRASES = ["verify you are human", "are you a robot", "unusual traffic",
                 "access denied", "press and hold", "confirm you are human"]


def parse_moment(s, end_of_day=False):
    """'2026-09-21' or '2026-09-18T19:00' -> datetime."""
    if "T" in s:
        return datetime.fromisoformat(s)
    d = date.fromisoformat(s)
    return datetime(d.year, d.month, d.day, 23, 59 if end_of_day else 0,
                    0 if end_of_day else 0)


def leg_moment(row):
    t = row.get("out_time") or "00:00"
    if t in ("-", ""):
        t = "00:00"
    try:
        return datetime.fromisoformat("%sT%s" % (row["out_date"], t))
    except ValueError:
        return datetime.fromisoformat("%sT00:00" % row["out_date"])


def scrape(cfg, pairs, verbose=True):
    """pairs: list of (origin, dest, date_from, date_to). Returns parsed rows."""
    w = cfg["wizz"]
    template = w["url_template"]
    duration = w.get("duration", "1_week")
    match = w["fare_api_match"]
    captured = []
    blocked = None

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            os.path.join(cfg["_root"], w["profile_dir"]),
            headless=w.get("headless", False), locale="en-GB",
            viewport={"width": 1400, "height": 950})
        page = ctx.new_page()

        def on_response(resp):
            try:
                if match in resp.url and "json" in resp.headers.get("content-type", ""):
                    captured.append({"url": resp.url, "data": resp.json()})
            except Exception:
                pass

        page.on("response", on_response)

        for origin, dest, d1, d2 in pairs:
            url = template.format(origin=origin, dest=dest, date_from=d1,
                                  date_to=d2, duration=duration)
            if verbose:
                print("  %s -> %s  %s..%s" % (origin, dest, d1, d2), flush=True)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=90000)
            except Exception as e:
                print("    navigation failed: %s" % str(e)[:70])
                continue
            page.wait_for_timeout(8000)
            try:
                visible = page.inner_text("body").lower()
            except Exception:
                visible = ""
            hit = next((ph for ph in BLOCK_PHRASES if ph in visible), None)
            if hit:
                blocked = hit
                print("    BLOCKED: %r -- stopping" % hit)
                break
            time.sleep(random.uniform(2, 4))

        ctx.close()

    if blocked:
        return None
    return parse_wizz.parse(captured)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--depart-after", required=True,
                    help="earliest outbound, e.g. 2026-09-18T19:00")
    ap.add_argument("--return-by", required=True,
                    help="latest inbound date, e.g. 2026-09-21")
    ap.add_argument("--min-nights", type=int, default=1)
    ap.add_argument("--top", type=int, default=10,
                    help="how many destinations to check return flights for")
    args = ap.parse_args()

    cfg = config.load()
    home = cfg["wizz"].get("origin_code", "EVN")
    after = parse_moment(args.depart_after)
    until = parse_moment(args.return_by, end_of_day=True)
    win_from, win_to = after.date().isoformat(), until.date().isoformat()

    print("\nWindow %s .. %s   outbound not before %s"
          % (win_from, win_to, after.strftime("%d %b %H:%M")))

    print("\nphase 1: outbound")
    out_rows = scrape(cfg, [(cfg["wizz"]["origin_slug"], "anywhere", win_from, win_to)])
    if out_rows is None:
        print("blocked -- try again later")
        return

    outs = [r for r in out_rows
            if r["origin"] == home and leg_moment(r) >= after]
    outs.sort(key=lambda r: r["regular"])
    print("  %d outbound option(s) inside the window" % len(outs))
    if not outs:
        print("  nothing departs in that window")
        return

    dests = []
    for r in outs:
        if r["destination"] not in dests:
            dests.append(r["destination"])
    dests = dests[: args.top]

    print("\nphase 2: return flights (%d destination(s))" % len(dests))
    in_rows = scrape(cfg, [(d, home, win_from, win_to) for d in dests]) or []
    ins = [r for r in in_rows if r["destination"] == home
           and leg_moment(r) <= until]
    print("  %d return option(s) inside the window" % len(ins))

    # nearby clusters make an open jaw possible
    groups = {}
    for g in cfg.get("trips", {}).get("nearby_groups", []):
        for c in g:
            groups[c] = set(g)

    flip = date.fromisoformat(cfg["passengers"]["flip_date"])
    trips = []
    for o in outs:
        for i in ins:
            a, b = o["destination"], i["origin"]
            if a != b and groups.get(a) != groups.get(b):
                continue
            n = (date.fromisoformat(i["out_date"]) -
                 date.fromisoformat(o["out_date"])).days
            if n < args.min_nights:
                continue
            s1 = 3 if date.fromisoformat(o["out_date"]) >= flip else 2
            s2 = 3 if date.fromisoformat(i["out_date"]) >= flip else 2
            trips.append({
                "route": a if a == b else "%s>%s" % (a, b),
                "out": "%s %s" % (o["out_date"][5:], o["out_time"]),
                "back": "%s %s" % (i["out_date"][5:], i["out_time"]),
                "nights": n,
                "total": round(o["regular"] * s1 + i["regular"] * s2, 2),
                "pax": "2A" if (s1, s2) == (2, 2) else "2A+1C",
            })

    trips.sort(key=lambda t: t["total"])
    seen, uniq = set(), []
    for t in trips:
        k = (t["route"], t["out"][:5], t["back"][:5])
        if k not in seen:
            seen.add(k)
            uniq.append(t)

    print("\n%-10s %-12s %-12s %3s %5s %10s" %
          ("ROUTE", "OUT", "BACK", "N", "PAX", "TOTAL"))
    print("-" * 60)
    for t in uniq[:20]:
        print("%-10s %-12s %-12s %3d %5s %10s" %
              (t["route"], t["out"], t["back"], t["nights"], t["pax"],
               "$%.2f" % t["total"]))
    if not uniq:
        print("  no pairing fits the window")
    print("\n  totals are seats only; bags and the lap-infant fee are extra")


if __name__ == "__main__":
    main()
