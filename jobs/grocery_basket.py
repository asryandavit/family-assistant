"""Basket: price the family shopping list at Yerevan City and Parma (decision 084).

    python jobs/grocery_basket.py                     weekly fresh, print + update the Sheet
    python jobs/grocery_basket.py --monthly           monthly staples
    python jobs/grocery_basket.py --all --send        both lists, Telegram to both of us
    python jobs/grocery_basket.py --fixtures tests/fixtures/grocery/basket --no-sheet
                                                      offline demo on captured results

Reads plan/meals/basket.md (what to buy, how much, which words match), searches each
distinct Search text once at both shops -- sequentially, one session, a pause between
searches -- and picks the cheaper shop per item (decision 081). Results go to the
"Shopping list" Google Sheet (tabs "This week" / "Monthly staples": checkboxes, product
and 📱 app links) and, with --send, to both family chats (telegram.send_family).
Read-only towards the shops: never logs in, never touches a cart, never orders.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from jobs.grocery_search import load_words  # noqa: E402
from lib import basket, config, fmt_basket, sheets, sheets_checklist, telegram, ui  # noqa: E402
from lib.fmt_grocery import money  # noqa: E402
from scrapers import grocery  # noqa: E402

JOB = "grocery_basket"
MAPPING = os.path.join("plan", "meals", "basket.md")
PAUSE = 1.5
DEFAULT_BUDGET = (80000, 100000)


def load_coach(root=ROOT):
    try:
        with open(os.path.join(root, "config_coach.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def load_rows(root=ROOT):
    with open(os.path.join(root, MAPPING), encoding="utf-8") as f:
        return basket.parse_mapping(f.read())


def searches_for(rows):
    """Distinct Search texts, in list order (one shop search each)."""
    out = []
    for r in rows:
        if not r["skip"] and r["search"] not in out:
            out.append(r["search"])
    return out


def fetch(searches, search_fn=grocery.search, pause=PAUSE, sleep=time.sleep):
    """{search: result}, one search at a time with a pause in between."""
    results = {}
    for n, q in enumerate(searches):
        if n:
            sleep(pause)
        results[q] = search_fn(q)
        print("  searched %-22s %s" % (q, " ".join("%s:%s" % (s, st[:5]) for s, st in results[q]["status"].items())),
              flush=True)
    return results


def fixture_slug(search):
    return re.sub(r"[^a-z0-9]+", "_", search.lower()).strip("_")


def load_fixtures(folder, searches):
    """Captured results ({query, status, items}) instead of live searches."""
    out = {}
    for q in searches:
        with open(os.path.join(folder, fixture_slug(q) + ".json"), encoding="utf-8") as f:
            d = json.load(f)
        out[q] = {"items": d["items"], "status": d["status"], "totals": {}}
    return out


def _save_local(cfg, kind, b, when):
    """A small local record of the run (what was chosen), next to the listener log."""
    d = os.path.join(cfg["_root"], ".browser")
    try:
        os.makedirs(d, exist_ok=True)
        rec = {"run_utc": when.astimezone(timezone.utc).isoformat(timespec="seconds"), "kind": kind,
               "totals": b["totals"], "compare": b["compare"], "partial": b["partial"],
               "lines": [{"item": e["row"]["item"], "status": e["status"], "shop": e["shop"],
                          "buy": e["line"]["buy"] if e["line"] else None,
                          "cost": e["line"]["cost"] if e["line"] else None,
                          "product": e["line"]["item"]["name"] if e["line"] else None,
                          "url": e["line"]["item"]["url"] if e["line"] else None}
                         for e in b["lines"]]}
        with open(os.path.join(d, "basket_%s.json" % kind), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=1)
    except OSError as e:
        print("  could not save local copy: %s" % e)


def run(cfg, kinds=("weekly",), send=False, write_sheet=True, fixtures=None, now=None,
        search_fn=grocery.search, sleep=time.sleep, writer=sheets_checklist.write_tab):
    """Price, notify, then persist (CLAUDE.md §5: a Sheet outage can't swallow the
    message). Returns {"baskets", "messages", "sheet_errors"}."""
    root = cfg.get("_root", ROOT)
    coach = load_coach(root)
    budget = tuple(coach.get("grocery_budget_amd") or DEFAULT_BUDGET)
    sheet_id = coach.get("shopping_sheet_id")
    when = now or ui.now_local()

    rows = [r for r in load_rows(root) if r["list"] in kinds]
    words = load_words(root)
    qs = searches_for(rows)
    results = load_fixtures(fixtures, qs) if fixtures else fetch(qs, search_fn, sleep=sleep)

    baskets = {k: basket.price_basket([r for r in rows if r["list"] == k], results, words)
               for k in kinds}
    totals = {k: baskets[k]["totals"]["all"] for k in kinds}

    messages = {k: fmt_basket.build(k, baskets[k], when, budget, totals) for k in kinds}
    if send:
        btn = [[("\U0001f4cb Open checklist", sheets_checklist.sheet_url(sheet_id))]] if sheet_id else None
        for k in kinds:
            telegram.send_family(cfg, messages[k], silent=True, buttons=btn)

    errors = []
    for k in kinds:
        _save_local(cfg, k, baskets[k], when)
        if not (write_sheet and sheet_id):
            continue
        srows, boxes, bold = fmt_basket.sheet_rows(k, baskets[k], when, budget, totals)
        try:
            writer(cfg, sheet_id, fmt_basket.TABS[k], srows, boxes, bold, (fmt_basket.MONEY_COL,))
        except Exception as e:
            errors.append("%s: %s" % (fmt_basket.TABS[k], str(e)[:150]))
    if errors:
        telegram.notify(cfg, "⚠️ SYSTEM: basket checklist not updated (%s). The Telegram list "
                             "is current; the Sheet shows the previous run." % "; ".join(errors))

    partial = any(b["partial"] for b in baskets.values()) or bool(errors)
    try:
        sheets.log_run(cfg, JOB, "partial" if partial else "ok",
                       " | ".join("%s %s AMD" % (k, format(totals[k], ",")) for k in kinds))
    except Exception:
        pass
    return {"baskets": baskets, "messages": messages, "sheet_errors": errors, "totals": totals}


def _print(kind, b):
    print("\n  %s — total %s (Yerevan City %s, Parma %s)" % (
        kind.upper(), money(b["totals"]["all"]), money(b["totals"]["yc"]), money(b["totals"]["parma"])))
    c = b["compare"]
    if c["n"]:
        print("  %d items at both shops: YC only %s · Parma only %s · cheapest of each %s"
              % (c["n"], money(c["yc"]), money(c["parma"]), money(c["cheapest"])))
    for e in b["lines"]:
        if e["line"]:
            ln = e["line"]
            print("    %-26s %-5s %-14s %9s  %s" % (e["row"]["item"][:26], e["shop"], ln["buy"],
                                                  money(ln["cost"]), ln["item"]["name"][:50]))
        else:
            print("    %-26s %s" % (e["row"]["item"][:26], fmt_basket._status_text(e)))


def main():
    ap = argparse.ArgumentParser(description="Price the shopping list at Parma and Yerevan City.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--weekly", action="store_true", help="weekly fresh (default)")
    g.add_argument("--monthly", action="store_true", help="monthly staples")
    g.add_argument("--all", action="store_true", help="both lists")
    ap.add_argument("--send", action="store_true", help="send to both family chats")
    ap.add_argument("--no-sheet", action="store_true", help="don't rewrite the Shopping list Sheet")
    ap.add_argument("--fixtures", help="folder of captured results (offline; implies --no-sheet "
                                       "unless --sheet)")
    ap.add_argument("--sheet", action="store_true", help="write the Sheet even with --fixtures")
    a = ap.parse_args()

    kinds = ("weekly", "monthly") if a.all else ("monthly",) if a.monthly else ("weekly",)
    write_sheet = not a.no_sheet and (a.sheet or not a.fixtures)
    cfg = config.load()
    try:
        out = run(cfg, kinds, send=a.send, write_sheet=write_sheet, fixtures=a.fixtures)
    except Exception as e:
        try:
            sheets.log_run(cfg, JOB, "error", str(e)[:300])
        except Exception:
            pass
        if a.send:
            telegram.notify(cfg, "⚠️ SYSTEM: basket errored: %s" % e)
        raise
    for k in kinds:
        _print(k, out["baskets"][k])
    if len(kinds) == 2:
        print("\n  month at these prices: %s (fresh x 52/12 + staples)"
              % money(basket.month_projection(out["totals"]["weekly"], out["totals"]["monthly"])))
    for err in out["sheet_errors"]:
        print("  SHEET NOT UPDATED: %s" % err)
    print()


if __name__ == "__main__":
    main()
