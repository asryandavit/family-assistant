"""Grocery price lookup: /price <product> [parma|yc] [match]

    python jobs/grocery_search.py lentils
    python jobs/grocery_search.py olive oil --shop parma
    python jobs/grocery_search.py chicken breast --sort match
    python jobs/grocery_search.py milk --send        (also sends to Telegram)

Searches Parma and Yerevan City, keeps results that actually name the product,
and prints them cheapest per kg/l first, with the product links. The listener
runs it with --send for the /price command.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import config, fmt_grocery, parse_grocery, sheets, telegram  # noqa: E402
from scrapers import grocery  # noqa: E402

JOB = "grocery_search"


def run(cfg, query, shops=grocery.SHOPS, sort="cheap", limit=10, send=False):
    res = grocery.search(query, shops)
    ranked = parse_grocery.rank(res["items"], query, sort=sort)
    if send:
        telegram.send_html(cfg, fmt_grocery.build(query, ranked, res["status"],
                                                  res["totals"], sort, limit))
    failed = [s for s, st in res["status"].items() if st != "ok"]
    try:
        sheets.log_run(cfg, JOB, "partial" if failed else "ok",
                       "%r: %d match(es)%s" % (query, len(ranked),
                                               (" | failed: " + ",".join(failed)) if failed else ""))
    except Exception:
        pass
    return res, ranked


def main():
    ap = argparse.ArgumentParser(description="Search Parma and Yerevan City prices.")
    ap.add_argument("query", nargs="+")
    ap.add_argument("--shop", choices=["all", "parma", "yc"], default="all")
    ap.add_argument("--sort", choices=["cheap", "match"], default="cheap")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--send", action="store_true", help="also send the result to Telegram")
    a = ap.parse_args()

    query = " ".join(a.query).strip()
    shops = grocery.SHOPS if a.shop == "all" else (a.shop,)
    sort = "cheap" if a.sort == "cheap" else "relevance"
    cfg = config.load()
    try:
        res, ranked = run(cfg, query, shops, sort, a.limit, a.send)
    except Exception as e:
        try:
            sheets.log_run(cfg, JOB, "error", str(e)[:300])
        except Exception:
            pass
        if a.send:
            telegram.notify(cfg, "⚠️ SYSTEM: price search errored: %s" % e)
        raise

    for shop, st in res["status"].items():
        print("  %-12s %s  (%s found by the shop)" % (grocery.SHOP_NAMES[shop], st,
                                                    res["totals"].get(shop, 0)))
    print("  %d result(s) name %r; showing %d\n" % (len(ranked), query, min(a.limit, len(ranked))))
    for n, i in enumerate(ranked[:a.limit], 1):
        price = fmt_grocery.money(i["price"]) + ("/kg" if i["sold_by_weight"] else "")
        unit = ("%s/%s" % (fmt_grocery.money(i["unit_price"]), i["unit"])
                if i["unit_price"] is not None and not i["sold_by_weight"] else "")
        disc = (" (was %s, -%g%%)" % (format(parse_grocery.amd(i["old_price"]), ","), i["discount_pct"])
                if i["old_price"] else "")
        print("  %2d. %-5s %-50s %12s %14s%s" % (n, i["shop"], i["name"][:50], price, unit, disc))
        print("      %s" % i["url"])


if __name__ == "__main__":
    main()
