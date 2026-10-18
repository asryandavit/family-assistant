"""Fetch product search results from Parma and Yerevan City.

Plain HTTP, no browser: Parma renders search results server-side and Yerevan
City has a public JSON search API that needs no login or token (both verified
2026-10-18; payloads in tests/fixtures/grocery/). Each shop is fetched
independently, so one being down never hides the other's results.

Polite by design: one search = at most two Parma pages + one YC request,
with a pause between Parma pages.
"""
import time

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
TIMEOUT = 25

PARMA_SEARCH = "https://parma.am/en/product/search"
PARMA_PER_PAGE = 60

YC_SEARCH = "https://apishopv2.yerevan-city.am/api/Product/Search"
YC_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://yerevan-city.am",
    "Referer": "https://yerevan-city.am/",
    "ostype": "1",
}

SHOPS = ("parma", "yc")
SHOP_NAMES = {"parma": "Parma", "yc": "Yerevan City"}


def _session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en"})
    return s


def fetch_parma(query, max_pages=2, session=None):
    """Returns a list of HTML pages (page 1 first)."""
    s = session or _session()
    pages = []
    for page in range(1, max_pages + 1):
        if page > 1:
            time.sleep(1.5)
        r = s.get(PARMA_SEARCH, params={"text": query, "page": page}, timeout=TIMEOUT)
        r.raise_for_status()
        pages.append(r.text)
        # stop when this page wasn't full
        if r.text.count('<div class="product_item ') < PARMA_PER_PAGE:
            break
    return pages


def fetch_yc(query, count=100, session=None):
    """Returns the parsed JSON payload of one search request.

    YC's own ordering is weak (a "milk" search leads with cosmetics), so we
    ask for 100 and let lib.parse_grocery.rank filter locally.
    """
    s = session or _session()
    body = {"count": count, "page": 1, "priceFrom": 20, "priceTo": 2290000,
            "countries": [], "tags": [], "categories": [], "brands": [],
            "search": query, "isDiscounted": False, "sortBy": 0}
    r = s.post(YC_SEARCH, headers=YC_HEADERS, json=body, timeout=TIMEOUT)
    r.raise_for_status()
    payload = r.json()
    if not payload.get("success", True):
        raise RuntimeError("YC answered success=false")
    return payload


def search(query, shops=SHOPS):
    """Fetch + parse every requested shop.

    Returns {"items": [...], "status": {shop: "ok" | "error: ..."},
             "totals": {shop: items reported by the shop}}.
    """
    from lib import parse_grocery as pg

    s = _session()
    items, status, totals = [], {}, {}
    for shop in shops:
        try:
            if shop == "parma":
                pages = fetch_parma(query, session=s)
                got = [i for p in pages for i in pg.parse_parma(p)]
                rng = pg.parma_page_range(pages[0]) if pages else None
                totals[shop] = len(got) if not rng else max(rng[1], len(got))
            elif shop == "yc":
                payload = fetch_yc(query, session=s)
                got = pg.parse_yc(payload)
                totals[shop] = pg.yc_counts(payload)[0]
            else:
                raise ValueError("unknown shop %r" % shop)
            items += got
            status[shop] = "ok"
        except Exception as e:
            status[shop] = "error: %s" % str(e)[:120]
            totals[shop] = 0
    return {"items": items, "status": status, "totals": totals}
