"""Market watch, nightly (~01:30): read every watched product link once, price each item to
Yerevan per forwarder × mode, send ONE report to both chats, alert on a big drop or back in
stock (docs/briefs/MARKET_WATCH.md §1, §4, §5, §9).

    python jobs/market_watch.py                   read, price, print (no Telegram, no Sheet)
    python jobs/market_watch.py --send            ...and send the report + alerts, write the Sheet
    python jobs/market_watch.py --offline         use the captured pages in tests/fixtures/market
                                                  instead of the browser (demo / smoke test)

Store fallback (§9, every store): one attempt per link per night; a block page skips that
store for the rest of the run; the item keeps its last price, marked ⚠️ with its date, and
raises no alert; one report line per blocked store; after 3 blocked nights in a row the
owner gets one message. /watch price stores an owner's price used like a read one. Never
read and no owner price -> "no price yet". The bot only reads pages: no login, no cart.
"""
import argparse
import json
import os
import sys
from datetime import timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib import config, sheets, telegram, ui  # noqa: E402
from market import DIR, pricing, rates as rates_mod, readers, report, sheet, state  # noqa: E402
from market import stores as stores_mod  # noqa: E402

JOB = "market_watch"
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "market")
OFFLINE_PAGES = {"amazon_us": "amazon_us_dp.html", "amazon_uk": "amazon_uk_dp.html",
                 "amazon_de": "amazon_de_dp.html", "amazon_it": "amazon_it_dp.html",
                 "vega": "vega_product.html", "wildberries": "wildberries_block.html",
                 "ozon": "ozon_block.html"}
BLOCK_NOTIFY_NIGHTS = 3


def market_config(root=ROOT):
    try:
        with open(os.path.join(root, "config_market.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def customs_rule(root=ROOT):
    try:
        with open(os.path.join(DIR, "customs.md"), encoding="utf-8") as f:
            for line in f:
                if line.startswith("`rule:"):
                    return line.split("`")[1].split(":")[1].strip()
    except OSError:
        pass
    return "default"


def load_tariffs():
    with open(os.path.join(DIR, "tariffs.json"), encoding="utf-8") as f:
        return json.load(f)


class OfflineSession:
    """Serves the captured pages by store (no browser, no network)."""

    def __init__(self, store_rows):
        self.store_rows = store_rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, url, wait_selector=None):
        from scrapers.market import blocked_reason
        st = stores_mod.store_for_url(url, self.store_rows)
        name = OFFLINE_PAGES.get(st["key"]) if st else None
        if not name:
            return {"status": "error", "url": url, "final_url": url, "html": "", "text": "",
                    "detail": "no captured page"}
        with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
            html = f.read()
        why = blocked_reason(url, readers._text(html), html)
        return {"status": "blocked" if why else "ok", "url": url, "final_url": url, "html": html,
                "text": "", "detail": why or ""}


def browser_session():
    from scrapers.market import Session
    return Session()


def _offer_from_read(off, today):
    o = {k: off.get(k) for k in ("title", "price", "currency", "shipping", "shipping_note",
                                 "in_stock", "stock_text", "weight_kg", "dims_cm")}
    o["delivery"] = [d.isoformat() for d in off["delivery"]] if off.get("delivery") else None
    o["date_local"] = today.isoformat()
    o["source"] = "read"
    return o


def _as_offer(o):
    """Stored offer -> the shape pricing wants (dates back to date objects)."""
    from datetime import date
    out = dict(o)
    if o.get("delivery"):
        out["delivery"] = tuple(date.fromisoformat(d) for d in o["delivery"])
    return out


def read_pages(items, store_rows, today, session_factory, root, log=print):
    """One attempt per link. Returns (fresh, blocked, errors, gone, notes, attempted, filled)."""
    fresh, blocked, errors, gone, notes, attempted = {}, {}, {}, set(), {}, set()
    filled = []
    todo = []
    for it in items:
        for url in it.get("links", []):
            st = stores_mod.store_for_url(url, store_rows)
            if st:                       # reader "none" too: a block is still detected
                todo.append((it, st, url))
    if not todo:
        return fresh, blocked, errors, gone, notes, attempted, filled
    with session_factory() as s:
        for it, st, url in todo:
            key = "%s|%s" % (it["id"], st["key"])
            if st["key"] in blocked:
                continue                                   # skipped for the rest of the run
            attempted.add(st["key"])
            r = s.read(stores_mod.canonical(url, st), wait_selector=None)
            if r["status"] == "blocked":
                blocked[st["key"]] = r["detail"]
                log("  %s blocked (%s) — skipped for tonight" % (st["name"], r["detail"]))
                continue
            if r["status"] != "ok":
                errors.setdefault(st["key"], []).append(r["detail"][:80])
                continue
            off = readers.parse(st["reader"], r["html"], today)
            if off["status"] == "gone":
                gone.add(key)
            elif off["status"] == "no_parser":
                notes[key] = "page opened; its price reader isn't built yet (page saved)"
                _save_capture(root, st["key"], today, r["html"])
            elif off.get("price") is None:
                notes[key] = "price not found on the page"
            else:
                fresh[key] = _offer_from_read(off, today)
                if not it.get("weight_kg") and off.get("weight_kg"):
                    filled.append((it["id"], off["weight_kg"], off.get("dims_cm"), off.get("size_source")))
    return fresh, blocked, errors, gone, notes, attempted, filled


def _save_capture(root, store_key, today, html):
    d = os.path.join(state.data_dir(root), "captures")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "%s_%s.html" % (store_key, today.isoformat())), "w", encoding="utf-8") as f:
        f.write(html)


def choose(key, fresh, owner, last):
    """(state, offer) for one item × store: fresh | owner | stale | none."""
    if key in fresh:
        return "fresh", fresh[key]
    o, l = owner.get(key), last.get(key)
    if o and (not l or o["date_local"] >= l["date_local"]):
        return "owner", dict(o, source="owner", shipping=None,
                             shipping_note="not known for an owner's price")
    if l:
        return "stale", l
    return "none", None


def run(cfg, today, session_factory, root=ROOT, send=False, write_sheet=True, sender=None,
        rates_get=None, log=print):
    sender = sender or telegram
    mcfg = market_config(root)
    sheet_id = mcfg.get("watch_sheet_id") if write_sheet else None
    store_rows = stores_mod.load()
    table = load_tariffs()
    rule = customs_rule(root)

    items, problems = sheet.sync_items(cfg, root, sheet_id, write=False) if sheet_id \
        else (state.load_items(root), [])
    act = state.active(items)
    for n, it in enumerate(act, start=1):
        it["_n"] = n
    rt = state.load_runtime(root)
    owner = state.load_owner_prices(root)
    rates = (rates_get or rates_mod.get)(root, today)

    fresh, blocked, errors, gone, notes, attempted, filled = read_pages(
        act, store_rows, today, session_factory, root, log)

    # weight/size read from the page fill items that had none (marked "page")
    if filled:
        cur = state.load_items(root)
        for iid, kg, dims, src in filled:
            for it in cur + act:
                if it["id"] == iid and not it.get("weight_kg"):
                    it["weight_kg"], it["size_cm"] = kg, list(dims) if dims else it.get("size_cm")
                    it["size_from"] = "page (%s)" % (src or "product")
        state.save_items(root, cur)

    results, alerts, offers_rows = {}, [], []
    for it in act:
        entries = []
        for url in it.get("links", []):
            st = stores_mod.store_for_url(url, store_rows)
            if not st:
                continue
            key = "%s|%s" % (it["id"], st["key"])
            if key in gone:
                entries.append({"store": st, "url": url, "state": "gone"})
                continue
            why = notes.get(key) or ("blocked tonight" if st["key"] in blocked else
                                     "page error tonight" if st["key"] in errors else "")
            kind, o = choose(key, fresh, owner, rt["last"])
            if kind == "none":
                entries.append({"store": st, "url": url, "state": "none", "why": why})
                continue
            q = pricing.quote(it, st, _as_offer(o), table["routes"], rates, today, rule)
            entries.append({"store": st, "url": url, "state": kind, "offer": o, "quote": q})
            offers_rows.append([it["id"], sheet.cell(it["name"]), st["key"], sheet.cell(o.get("title") or ""),
                                o.get("price"), o.get("currency") or st["currency"],
                                "" if o.get("shipping") is None else o["shipping"],
                                "" if o.get("in_stock") is None else ("in stock" if o["in_stock"] else "out"),
                                kind, o["date_local"], url, state.now_utc()])
            prev = rt["last"].get(key)
            if kind == "fresh" and prev and prev.get("in_stock") is False and o.get("in_stock"):
                alerts.append(report.stock_alert(it, st["name"], url, o["price"], o.get("currency")))
        results[it["id"]] = entries

    # change vs yesterday, history, drop alerts (fresh bests only)
    changes, todays = {}, []
    yesterday = today - timedelta(days=1)
    for it in act:
        entries = results[it["id"]]
        best, store_key, _ = pricing.best_of([e["quote"] for e in entries if e.get("quote")])
        if not best:
            continue
        ent = next(e for e in entries if e["store"]["key"] == store_key)
        before = [h for h in rt["history"] if h["item_id"] == it["id"] and h["date_local"] < today.isoformat()]
        if before:
            prev = before[-1]["best_total_amd"]
            pct = (best["total_amd"] - prev) / prev * 100 if prev else None
            changes[it["id"]] = pct
            if (ent["state"] == "fresh" and pct is not None and pct <= -report.DROP_PCT
                    and before[-1]["date_local"] >= (yesterday - timedelta(days=1)).isoformat()):
                alerts.append(report.drop_alert(it, best, prev, pct, ent["store"]["name"]))
        todays.append({"date_local": today.isoformat(), "item_id": it["id"], "item": it["name"],
                       "best_total_amd": best["total_amd"], "store": store_key,
                       "route": pricing.label(best), "source": ent["state"]})

    # blocked / error lines and streaks
    lines, owner_msgs = [], []
    for key, row in store_rows.items():
        n_items = sum(1 for it in act for u in it.get("links", [])
                      if (stores_mod.store_for_url(u, store_rows) or {}).get("key") == key)
        b = rt["blocked"].get(key, {"nights": 0, "notified": False})
        if key in blocked:
            kept = sum(1 for it in act for u in it.get("links", [])
                       if (stores_mod.store_for_url(u, store_rows) or {}).get("key") == key
                       and ("%s|%s" % (it["id"], key) in rt["last"] or "%s|%s" % (it["id"], key) in owner))
            lines.append(report.blocked_line(row["name"], n_items, kept))
            b = {"nights": b["nights"] + 1, "notified": b["notified"], "last_local": today.isoformat()}
            if b["nights"] >= BLOCK_NOTIFY_NIGHTS and not b["notified"]:
                links = [(it["_n"], it["name"], u) for it in act for u in it.get("links", [])
                         if (stores_mod.store_for_url(u, store_rows) or {}).get("key") == key]
                owner_msgs.append(report.blocked_owner_message(row["name"], links))
                b["notified"] = True
        elif key in attempted:
            b = {"nights": 0, "notified": False}
        rt["blocked"][key] = b
        if key in errors:
            lines.append("⚠️ %s: page error on %d link%s (%s)" % (row["name"], len(errors[key]),
                         "" if len(errors[key]) == 1 else "s", telegram.esc(errors[key][0])))
    for p in problems:
        lines.append("⚠️ Sheet: %s" % telegram.esc(p))
    if mcfg.get("watch_sheet_id") is None and write_sheet:
        lines.append("<i>Watch list Sheet not set up yet (config_market.json watch_sheet_id).</i>")

    text = report.report(today, act, results, changes, lines, rates,
                         table.get("refreshed_utc"), rule)

    # notify before persisting (CLAUDE.md §5)
    if send:
        sender.send_family(cfg, text, silent=True)
        for a in alerts:
            sender.send_family(cfg, a, silent=False)
        for m in owner_msgs:
            sender.send_html(cfg, m, silent=False)

    for key, o in fresh.items():
        rt["last"][key] = o
    rt["history"] = [h for h in rt["history"] if h["date_local"] != today.isoformat()] + todays
    rt["last_run_local"] = today.isoformat()
    state.save_runtime(root, rt)

    sheet_error = None
    if sheet_id:
        try:
            sheet.write_run(cfg, sheet_id, state.load_items(root), offers_rows, rt["history"])
        except Exception as e:
            sheet_error = str(e)[:200]
            if send:
                sender.send_html(cfg, "⚠️ Watch list Sheet not updated: %s" % telegram.esc(sheet_error))
    return {"text": text, "alerts": alerts, "owner_msgs": owner_msgs, "blocked": blocked,
            "errors": errors, "fresh": fresh, "sheet_error": sheet_error, "history": todays}


def main():
    ap = argparse.ArgumentParser(description="Market watch nightly run.")
    ap.add_argument("--send", action="store_true", help="send to both chats and write the Sheet")
    ap.add_argument("--offline", action="store_true", help="captured pages instead of the browser")
    a = ap.parse_args()
    cfg = config.load()
    today = ui.now_local().date()
    store_rows = stores_mod.load()
    factory = (lambda: OfflineSession(store_rows)) if a.offline else browser_session
    try:
        out = run(cfg, today, factory, send=a.send, write_sheet=a.send and not a.offline)
        status = "partial" if out["blocked"] or out["errors"] or out["sheet_error"] else "ok"
        sheets.log_run(cfg, JOB, status, "%d fresh, blocked: %s" % (len(out["fresh"]),
                                                                   ",".join(out["blocked"]) or "none"))
    except Exception as e:
        sheets.log_run(cfg, JOB, "error", str(e)[:300])
        if a.send:
            telegram.notify(cfg, "⚠️ SYSTEM: market watch errored: %s" % e)
        raise
    print(out["text"])
    for x in out["alerts"] + out["owner_msgs"]:
        print("\nALERT:", x)


if __name__ == "__main__":
    main()
