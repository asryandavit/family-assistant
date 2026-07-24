"""Live search on Booking.com and Airbnb.

Uses the session-warming that proved necessary against Booking's WAF: load the
homepage first, settle cookies, then the search URL, then wait for real result
cards rather than a fixed sleep.

Returns raw HTML for lib.parse_stays; any visible verification wall returns
status "blocked" and is never clicked through.
"""
import os
import random
import time

from playwright.sync_api import sync_playwright

BLOCK_PHRASES = ["verify you are human", "are you a robot", "unusual traffic",
                 "access denied", "press and hold", "confirm you are human"]

COOKIE_SELECTORS = [
    "#onetrust-reject-all-handler",
    "button:has-text('Decline optional')",
    "button:has-text('Reject all')",
    "button:has-text('Only necessary')",
    "#onetrust-accept-btn-handler",
    "button:has-text('OK')",
]

RESULT_SELECTORS = {
    "booking": "[data-testid='property-card']",
    "airbnb": "[itemprop='itemListElement'], [data-testid='card-container']",
}
HOME = {"booking": "https://www.booking.com/", "airbnb": "https://www.airbnb.com/"}

# Booking nflt facet codes
HT_APARTMENT, HT_HOLIDAY_HOME, HT_APARTHOTEL, HT_HOTEL = 201, 220, 224, 204


def booking_url(q, city_name):
    nflt = ["review_score=70"]
    if "apt" in q["flags"]:
        nflt += ["ht_id=%d" % HT_APARTMENT, "ht_id=%d" % HT_HOLIDAY_HOME]
    if "hotel" in q["flags"]:
        nflt.append("ht_id=%d" % HT_HOTEL)
    if "breakfast" in q["flags"]:
        nflt.append("mealplan=1")
    if "pool" in q["flags"]:
        nflt.append("popular_activities=2")
    if "center" in q["flags"]:
        nflt.append("distance=3000")
    if q.get("budget"):
        nflt.append("price=USD-0-%d-1" % int(q["budget"]))

    url = ("https://www.booking.com/searchresults.html?"
           "ss=%s&checkin=%s&checkout=%s"
           "&group_adults=%d&group_children=%d&age=%d&no_rooms=1"
           "&selected_currency=USD&order=bayesian_review_score_and_price"
           % (city_name.replace(" ", "+"), q["checkin"], q["checkout"],
              q["adults"], q["children"], q["child_age"]))
    if nflt:
        url += "&nflt=" + "%3B".join(nflt)
    return url


def airbnb_url(q, city_name):
    # Under 2 rides as an infant and does not count toward the guest total
    infants = 1 if q["child_age"] < 2 else 0
    children = 0 if infants else q["children"]
    url = ("https://www.airbnb.com/s/%s/homes?checkin=%s&checkout=%s"
           "&adults=%d&children=%d&infants=%d&currency=USD"
           % (city_name.replace(" ", "-"), q["checkin"], q["checkout"],
              q["adults"], children, infants))
    if q.get("budget"):
        url += "&price_max=%d" % int(q["budget"])
    if "apt" in q["flags"]:
        url += "&room_types%5B%5D=Entire%20home%2Fapt"
    if "pool" in q["flags"]:
        url += "&amenities%5B%5D=7"
    return url


def _cookies(page):
    for sel in COOKIE_SELECTORS:
        try:
            el = page.locator(sel).first
            if el.count() and el.is_visible(timeout=2000):
                el.click(timeout=3500)
                page.wait_for_timeout(1500)
                return
        except Exception:
            continue


def search(cfg, site, city_name, q, verbose=True):
    """Returns {'status','html','url'}. status: ok | blocked | empty | error."""
    profile = os.path.join(cfg["_root"], ".browser", "stays_%s" % site)
    os.makedirs(profile, exist_ok=True)
    url = (booking_url if site == "booking" else airbnb_url)(q, city_name)
    headless = (cfg.get("stays") or {}).get("headless", False)

    def log(m):
        if verbose:
            print(m, flush=True)

    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                profile, headless=headless, locale="en-GB",
                viewport={"width": 1400, "height": 950})
            if site == "booking":
                ctx.add_cookies([{"name": "cur_curr", "value": "USD",
                                  "domain": ".booking.com", "path": "/"}])
            page = ctx.new_page()

            log("  [%s] warming session" % site)
            page.goto(HOME[site], wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(3500)
            _cookies(page)

            log("  [%s] searching %s %s->%s" % (site, city_name, q["checkin"], q["checkout"]))
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            _cookies(page)

            found = False
            try:
                page.wait_for_selector(RESULT_SELECTORS[site], timeout=45000,
                                       state="attached")
                found = True
            except Exception:
                pass
            page.wait_for_timeout(4000)
            try:
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(3000)
            except Exception:
                pass

            html = page.content()
            try:
                visible = page.inner_text("body").lower()
            except Exception:
                visible = ""
            ctx.close()

        hit = next((ph for ph in BLOCK_PHRASES if ph in visible), None)
        if hit:
            log("  [%s] BLOCKED: %r" % (site, hit))
            return {"status": "blocked", "html": "", "url": url, "detail": hit}
        if not found:
            return {"status": "empty", "html": html, "url": url}
        time.sleep(random.uniform(1, 3))
        return {"status": "ok", "html": html, "url": url}

    except Exception as e:
        log("  [%s] error: %s" % (site, str(e)[:120]))
        return {"status": "error", "html": "", "url": url, "detail": str(e)[:200]}


def city_name_for(cfg, code):
    """IATA -> searchable city name, from areas.json then the Wizz station map."""
    import json
    if len(code) != 3 or not code.isalpha():
        return code
    try:
        with open(os.path.join(cfg["_root"], "areas.json"), encoding="utf-8") as f:
            a = json.load(f).get(code.upper())
            if a and a.get("city"):
                return a["city"]
    except (OSError, ValueError):
        pass
    try:
        from lib import stations
        return stations.city_name(cfg, code, fallback=code)
    except Exception:
        return code
