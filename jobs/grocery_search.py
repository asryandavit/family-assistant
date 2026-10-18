"""Grocery price lookup: /price <product> [parma|yc] [match]

    python jobs/grocery_search.py lentils
    python jobs/grocery_search.py ոսպ                 (Armenian works too)
    python jobs/grocery_search.py katnashor
    python jobs/grocery_search.py olive oil --shop parma
    python jobs/grocery_search.py milk --send        (also sends to Telegram)

Searches Parma and Yerevan City, keeps results that actually name the product,
and prints them cheapest per kg/l first, with links -- plus a comparison: the
cheapest per kg/l at each shop, and products sold at both shops side by side.
Armenian and transliterated words are translated through
plan/meals/grocery-words.md. The listener runs it with --send for /price.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib import config, fmt_grocery, parse_grocery, sheets, telegram  # noqa: E402
from scrapers import grocery  # noqa: E402

JOB = "grocery_search"
WORDS_FILE = os.path.join("plan", "meals", "grocery-words.md")


def load_words(root=ROOT):
    """The word list, or [] when the file is missing (search still works)."""
    try:
        with open(os.path.join(root, WORDS_FILE), encoding="utf-8") as f:
            return parse_grocery.parse_word_list(f.read())
    except OSError:
        return []


def run(cfg, query, shops=grocery.SHOPS, sort="cheap", limit=10, send=False, words=None):
    words = load_words(cfg.get("_root", ROOT)) if words is None else words
    searched, _ = parse_grocery.expand_query(query, words)
    res = grocery.search(searched, shops)
    ranked = parse_grocery.rank(res["items"], query, sort=sort, words=words)
    cmp = parse_grocery.compare_shops(ranked) if len(shops) > 1 else None
    pairs = parse_grocery.same_products(ranked, query, words) if len(shops) > 1 else []
    if send:
        telegram.send_html(cfg, fmt_grocery.build(query, ranked, res["status"], res["totals"],
                                                  sort, limit, searched, cmp, pairs))
    failed = [s for s, st in res["status"].items() if st != "ok"]
    try:
        sheets.log_run(cfg, JOB, "partial" if failed else "ok",
                       "%r: %d match(es)%s" % (query, len(ranked),
                                               (" | failed: " + ",".join(failed)) if failed else ""))
    except Exception:
        pass
    return {"res": res, "ranked": ranked, "searched": searched, "cmp": cmp, "pairs": pairs}


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
        out = run(cfg, query, shops, sort, a.limit, a.send)
    except Exception as e:
        try:
            sheets.log_run(cfg, JOB, "error", str(e)[:300])
        except Exception:
            pass
        if a.send:
            telegram.notify(cfg, "⚠️ SYSTEM: price search errored: %s" % e)
        raise

    res, ranked = out["res"], out["ranked"]
    if out["searched"].lower() != query.lower():
        print("  searched the shops for: %r" % out["searched"])
    for shop, st in res["status"].items():
        print("  %-12s %s  (%s found by the shop)" % (grocery.SHOP_NAMES[shop], st,
                                                    res["totals"].get(shop, 0)))
    cmp = out["cmp"]
    if cmp:
        print("\n  COMPARE (cheapest per %s)" % cmp["unit"])
        for shop, i in cmp["best"].items():
            print("    %-12s %s/%s  %s" % (grocery.SHOP_NAMES[shop], fmt_grocery.money(i["unit_price"]),
                                         cmp["unit"], i["name"][:55]))
        if cmp["cheaper"]:
            print("    -> %s is %d%% cheaper per %s" % (grocery.SHOP_NAMES[cmp["cheaper"]], cmp["pct"], cmp["unit"]))
    if out["pairs"]:
        print("\n  SAME PRODUCT AT BOTH SHOPS")
        for p, y, diff, pct in out["pairs"][:6]:
            who = "Yerevan City" if diff < 0 else "Parma" if diff > 0 else "-"
            print("    %-46s Parma %10s | YC %10s -> %s cheaper by %d%%"
                  % (p["name"][:46], fmt_grocery.money(p["price"]), fmt_grocery.money(y["price"]), who, pct))
    print("\n  %d result(s) match %r; showing %d\n" % (len(ranked), query, min(a.limit, len(ranked))))
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
