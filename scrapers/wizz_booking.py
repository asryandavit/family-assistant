"""Wizz booking-page scraper, built on the farechart endpoint.

Distinct from scrapers/wizz_fare_finder.py, which drives the fare finder. That
tool answers "where can I go" but ignores dates on a specific route. This one
answers "what does this route cost on these dates", which is what /flights needs.

Endpoint (confirmed 2026-07): .../Api/asset/farechart
It returns a price-by-date calendar as {"outboundFlights":[...], "returnFlights":[...]},
each entry carrying departureStation, arrivalStation, price{amount,currencyCode},
date and classOfService. One request therefore covers a span of dates and often
both directions.

URL format (confirmed by hand):
  /booking/select-flight/{FROM}/{TO}/{DATE}/{RETURN|null}/{adults}/{children}/{infants}/null
"""
import os
import random
import time

from playwright.sync_api import sync_playwright

FARECHART = "Api/asset/farechart"
BLOCK_PHRASES = ["verify you are human", "are you a robot", "unusual traffic",
                 "access denied", "press and hold", "confirm you are human"]

URL = ("https://www.wizzair.com/en-gb/booking/select-flight"
       "/{f}/{t}/{d1}/{d2}/{a}/{c}/{i}/null")


def build_url(frm, to, date_out, date_back=None, adults=2, children=0, infants=1):
    return URL.format(f=frm.upper(), t=to.upper(), d1=date_out,
                      d2=date_back or "null", a=adults, c=children, i=infants)


def fetch(cfg, requests, verbose=True):
    """requests: list of dicts with from/to/date_out and optional date_back.

    Returns {"status": ok|blocked|error, "payloads": [{req, data}, ...]}.
    A visible verification page stops the run; it is never clicked through.
    """
    w = cfg["wizz"]
    profile = os.path.join(cfg["_root"], w["profile_dir"])
    os.makedirs(profile, exist_ok=True)
    fl = cfg.get("flights", {})
    adults = fl.get("adults", 2)

    payloads, blocked = [], None
    captured = []

    def log(m):
        if verbose:
            print(m, flush=True)

    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                profile, headless=fl.get("headless", False), locale="en-GB",
                viewport={"width": 1400, "height": 950})
            ctx.add_cookies([{"name": "cur_curr", "value": "USD",
                              "domain": ".wizzair.com", "path": "/"}])
            page = ctx.new_page()

            def on_response(resp):
                try:
                    if FARECHART in resp.url and "json" in resp.headers.get(
                            "content-type", ""):
                        captured.append(resp.json())
                except Exception:
                    pass

            page.on("response", on_response)

            # Warming the session first is what got us past Booking's WAF; the
            # same precaution costs one page load here.
            log("  warming session")
            page.goto("https://www.wizzair.com/en-gb",
                      wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(3500)

            for req in requests:
                captured.clear()
                u = build_url(req["from"], req["to"], req["date_out"],
                              req.get("date_back"), adults,
                              req.get("children", 0), req.get("infants", 1))
                log("  %s->%s %s%s" % (req["from"], req["to"], req["date_out"],
                                       " / " + req["date_back"]
                                       if req.get("date_back") else ""))
                try:
                    page.goto(u, wait_until="domcontentloaded", timeout=90000)
                except Exception as e:
                    log("    navigation failed: %s" % str(e)[:70])
                    continue
                page.wait_for_timeout(11000)

                try:
                    visible = page.inner_text("body").lower()
                except Exception:
                    visible = ""
                hit = next((b for b in BLOCK_PHRASES if b in visible), None)
                if hit:
                    blocked = hit
                    log("    BLOCKED: %r" % hit)
                    break

                for d in captured:
                    payloads.append({"req": dict(req), "url": u, "data": d})
                time.sleep(random.uniform(2, 4))

            ctx.close()
    except Exception as e:
        return {"status": "error", "detail": str(e)[:200], "payloads": payloads}

    if blocked:
        return {"status": "blocked", "detail": blocked, "payloads": payloads}
    log("  captured %d farechart payload(s)" % len(payloads))
    return {"status": "ok", "payloads": payloads}
