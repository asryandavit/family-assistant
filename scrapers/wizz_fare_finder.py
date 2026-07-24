"""Pull Wizz Air fare-finder data for EVN in both directions.

Phase 1: EVN -> anywhere, one search window per month.
Phase 2: each destination found in phase 1 -> EVN, one wide window each.

Both phases share a single browser session. Phase 2 is what makes open-jaw
planning possible: cheapest way out to city A, cheapest way home from city B.

Intercepts the JSON API responses that feed the fare grid rather than parsing
the DOM. Fare endpoint (confirmed 2026-07): .../Api/search/SmartSearchCheapFlightsV2

Block detection checks only VISIBLE page text, never raw HTML -- commercial
sites routinely load captcha libraries in source without ever challenging the
visitor. A genuine wall returns status "blocked"; it is never solved.
"""
import calendar
import json
import os
import random
import time
from datetime import date

from playwright.sync_api import sync_playwright

BLOCK_PHRASES = [
    "verify you are human",
    "are you a robot",
    "unusual traffic",
    "access denied",
    "please complete the security check",
]

DEFAULT_TEMPLATE = ("https://www.wizzair.com/en-gb/flights/fare-finder"
                    "/{origin}/{dest}/0/0/0/1/0/0/{date_from}/{date_to}"
                    "?flexible=anytime&duration={duration}")


def _month_windows(months_ahead):
    """One search window per month: first day -> last day."""
    out = []
    today = date.today()
    y, m = today.year, today.month
    for i in range(months_ahead):
        mm = m + i
        yy = y + (mm - 1) // 12
        mm = (mm - 1) % 12 + 1
        first = date(yy, mm, 1)
        last = date(yy, mm, calendar.monthrange(yy, mm)[1])
        if last < today:
            continue
        out.append((max(first, today).isoformat(), last.isoformat()))
    return out


def _wide_window(months_ahead):
    """Single window spanning the whole search horizon."""
    windows = _month_windows(months_ahead)
    return (windows[0][0], windows[-1][1]) if windows else None


def _destinations_from(captured, limit):
    """Pull unique arrival codes out of raw phase-1 responses, in order."""
    seen = []
    for resp in captured or []:
        for item in (resp.get("data") or {}).get("items", []) or []:
            code = (item.get("outboundFlight") or {}).get("arrivalStation")
            if code and code not in seen:
                seen.append(code)
    return seen[:limit]


def scrape(cfg, verbose=True):
    w = cfg["wizz"]
    root = cfg["_root"]
    profile = os.path.join(root, w["profile_dir"])
    os.makedirs(profile, exist_ok=True)
    os.makedirs(os.path.join(root, ".browser"), exist_ok=True)

    template = w.get("url_template") or DEFAULT_TEMPLATE
    duration = w.get("duration", "1_week")
    months = w.get("months_ahead", 4)
    match = (w.get("fare_api_match") or "").strip()

    origin_slug = w.get("origin_slug", "yerevan")
    origin_code = w.get("origin_code", "EVN")
    inb = cfg.get("inbound", {})
    do_inbound = inb.get("enabled", True)
    max_dests = inb.get("max_destinations", 20)

    discovery, captured = [], []
    blocked_by = None

    def log(msg):
        if verbose:
            print(msg, flush=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            profile,
            headless=w.get("headless", True),
            viewport={"width": 1400, "height": 950},
            locale="en-GB",
        )
        page = ctx.new_page()

        def on_response(resp):
            try:
                if "application/json" not in resp.headers.get("content-type", ""):
                    return
                if not match:
                    discovery.append({"url": resp.url, "status": resp.status,
                                      "preview": resp.text()[:400]})
                elif match in resp.url:
                    captured.append({"url": resp.url, "data": resp.json()})
            except Exception:
                pass

        page.on("response", on_response)

        def visit(origin, dest, date_from, date_to, label):
            nonlocal blocked_by
            url = template.format(origin=origin, dest=dest, date_from=date_from,
                                  date_to=date_to, duration=duration)
            log(f"  {label}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=90000)
            except Exception as e:
                log(f"    navigation failed: {e}")
                return False
            page.wait_for_timeout(8000)
            try:
                visible = page.inner_text("body").lower()
            except Exception:
                visible = ""
            hit = next((ph for ph in BLOCK_PHRASES if ph in visible), None)
            if hit:
                blocked_by = hit
                log(f"    BLOCKED: page visibly shows {hit!r}")
                return False
            time.sleep(random.uniform(2, 5))
            return True

        # --- phase 1: outbound, EVN -> anywhere ---
        log("phase 1: outbound")
        for date_from, date_to in _month_windows(months):
            if not visit(origin_slug, "anywhere", date_from, date_to,
                         f"{origin_code} -> anywhere  {date_from} to {date_to}"):
                if blocked_by:
                    break

        outbound_count = len(captured)

        # --- phase 2: inbound, each destination -> EVN ---
        if do_inbound and not blocked_by and match:
            dests = _destinations_from(captured, max_dests)
            window = _wide_window(months)
            if dests and window:
                log(f"phase 2: inbound ({len(dests)} destinations)")
                for code in dests:
                    if not visit(code, origin_code, window[0], window[1],
                                 f"{code} -> {origin_code}"):
                        if blocked_by:
                            break

        ctx.close()

    if blocked_by:
        return {"status": "blocked", "detail": blocked_by, "raw": captured}

    if not match:
        path = os.path.join(root, ".browser", "discovery.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(discovery, f, ensure_ascii=False, indent=2)
        log(f"  discovery: {len(discovery)} JSON responses -> {path}")
        return {"status": "discovery", "raw": [],
                "hint": "Inspect .browser/discovery.json, then set wizz.fare_api_match"}

    log(f"  captured {outbound_count} outbound + {len(captured) - outbound_count} inbound responses")
    return {"status": "ok", "raw": captured}
