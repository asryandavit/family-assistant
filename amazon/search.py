"""One queued /amazon job, start to finish (run by jobs/amazon_search.py, one at a time).

    plan (model: translate the query, category, <= 1 question) -> vague? ask one question with
    buttons and stop -> per store, in the bot's own browser: search page (postcode check, one
    scroll if cards are lazy) -> top N cards by trust and price get a product-page read (seller,
    weight, exact delivery) -> price in code -> pick + reason (model phrases, code decides; a
    deterministic sentence if the model fails) -> one answer (rich, plain fallback) -> save
    /amazon last (after sending).

Politeness (brief §6.3), all in code: read-only, signed out, never a check page passed (a hit
marks the store blocked for cooldown_hours), 3-6 s between pages, at most max_searches_per_day
runs. Order of failure handling (CLAUDE.md §5): a store that fails is named in the answer and the
others still answer; the message is sent before anything is saved.
"""
import json
import math
import os
import time
from datetime import UTC, datetime

from amazon import data_dir, limits, parse, pricing, report, runner, trust
from market import rates as rates_mod
from market import stores as stores_mod

SITES = ("uk", "de", "it")


def load_cfg(root):
    with open(os.path.join(root, "config_amazon.json"), encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ files
# same as china/search.py (folder: .browser/amazon_data)

def _path(root, name):
    return os.path.join(data_dir(root), name)


def write_json(root, name, obj):
    tmp = _path(root, name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, default=str)
    os.replace(tmp, _path(root, name))


def read_json(root, name, default=None):
    try:
        with open(_path(root, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_last(root, chat_id, payload):
    write_json(root, "last_%s.json" % chat_id, dict(payload, saved=time.time()))


def load_last(root, chat_id, keep_hours=24):
    d = read_json(root, "last_%s.json" % chat_id)
    if not d or time.time() - d.get("saved", 0) > keep_hours * 3600:
        return None
    return d


def find_result(root, chat_id, job_id, n):
    last = load_last(root, chat_id, 24)
    if not last or last.get("job") != job_id:
        return None, None
    k = 0
    for s in last["sites"]:
        for p in s.get("ranked") or []:
            k += 1
            if k == n:
                return p, last
    return None, last


# ------------------------------------------------------------------ reading one store

def choose(cards, description, acfg):
    """(cards to open as product pages, notes). Priced cards among the first cards_considered;
    number+unit words the person typed ('65w') must be in the title when at least top_per_store
    cards carry them; costume/seasonal listings (config avoid_words) are left out unless the person
    asked for them; then by trust band (card evidence), organic before sponsored, cheaper."""
    tc, top = acfg["trust"], acfg["top_per_store"]
    notes = []
    pool = [c for c in cards[:acfg["cards_considered"]] if c["price"] is not None]
    wanted = description.lower()
    avoid = [w for w in acfg.get("avoid_words", []) if w not in wanted]
    clean = [c for c in pool if not any(w in (c["title"] or "").lower() for w in avoid)]
    if len(clean) >= top:
        if len(clean) < len(pool):
            notes.append("left out %d costume/seasonal listing%s" % (
                len(pool) - len(clean), "" if len(pool) - len(clean) == 1 else "s"))
        pool = clean
    tokens = parse.spec_tokens(description)
    if tokens:
        match = [c for c in pool if parse.has_tokens(c["title"], tokens)]
        if len(match) >= top:
            if len(match) < len(pool):
                notes.append("kept the %d results whose title says %s" % (len(match), ", ".join(tokens)))
            pool = match
        else:
            notes.append("few titles say %s - not filtered" % ", ".join(tokens))

    def key(c):
        pts, _ = trust.score(c, tc)
        return (-math.floor(pts / tc["band"]), 1 if c["sponsored"] else 0, c["price"])
    return sorted(pool, key=key)[:top], notes


def merge_product(o, info):
    """Fold a parsed product page into the card's offer. The buy-box price wins over the card's."""
    out = dict(o)
    out["seller"], out["fulfilment"] = info["seller"], info.get("fulfilment")
    if info.get("delivery_text"):                      # fee, note, text and date come as one
        for k in ("delivery_text", "delivery_fee", "delivery_note", "delivery_eta"):
            out[k] = info[k]
    for k in ("weight_kg", "dims_cm"):
        if info.get(k):
            out[k] = info[k]
    if info.get("rating") is not None:
        out["rating"] = info["rating"]
    if info.get("reviews") is not None:
        out["reviews"] = info["reviews"]
    if info.get("title"):
        out["title"] = info["title"]
    notes = list(o.get("notes") or [])
    if not info.get("in_stock", True):
        out["price"] = None
        notes.append("currently unavailable on the product page")
    elif info.get("price") is not None:
        if o.get("price") is not None and abs(info["price"] - o["price"]) > 0.005:
            notes.append("search card showed %.2f, the product page %.2f - the page price is used"
                         % (o["price"], info["price"]))
        out["price"] = info["price"]
        out["list_price"] = info.get("list_price")
        out["notes"] = [n for n in notes if n != "price not read"]
        return out
    elif o.get("price") is not None:
        notes.append("no buy-box price on the product page - the search card's price is used")
    out["notes"] = notes
    return out


def read_store(session, site, query, description, acfg, root, today, store, names, log=print):
    """One store: search page -> cards -> product pages. Returns the store's result dict
    {site, status, notice, query, search_url, seen, read, offers, pages}."""
    url = parse.search_url(site, query)
    res = {"site": site, "status": "ok", "notice": None, "query": query, "search_url": url,
           "seen": 0, "read": 0, "offers": [], "pages": 0}
    r = session.read(url, wait_selector="[data-asin]")
    res["pages"] += 1
    if r["status"] == "blocked":
        limits.mark_blocked(root, site)
        return dict(res, status="check", notice=r["detail"])
    if r["status"] != "ok":
        return dict(res, status="error", notice=r["detail"] or "page did not load")
    line = parse.deliver_to(r["html"])
    if not parse.postcode_ok(line, store["postcode"]):
        return dict(res, status="setup",
                    notice="the page says 'Deliver to %s', not the warehouse %s" % (line or "?", store["postcode"]))
    cards = parse.parse_cards(r["html"], site, today)
    if len(cards) < acfg["cards_considered"]:           # lazy cards: scroll once, keep the better read
        more = parse.parse_cards(session.scroll_html(), site, today)
        res["pages"] += 1
        if len(more) > len(cards):
            cards = more
    res["seen"] = len(cards)
    if not cards:
        return dict(res, status="empty", notice="no result cards on the page")
    chosen, notes = choose(cards, description, acfg)
    if not chosen:
        return dict(res, status="empty", notice="no result with a price")
    note = "; ".join(notes) or None
    for c in chosen:
        pr = session.read(parse.product_url(site, c["id"]))
        res["pages"] += 1
        if pr["status"] == "blocked":
            limits.mark_blocked(root, site)
            note = "a product page showed a check page - the rest were not opened"
            res["offers"].append(c)
            res["offers"].extend(x for x in chosen[chosen.index(c) + 1:])
            break
        if pr["status"] == "ok":
            info = parse.parse_product(pr["html"], site, today, names)
            res["offers"].append(merge_product(c, info))
            res["read"] += 1
        else:
            res["offers"].append(c)
            note = "a product page did not load (%s)" % (pr["detail"] or "error")[:60]
    return dict(res, notice=note)


# ------------------------------------------------------------------ assembling

def assemble(results, acfg, routes, rates, today, store_rows):
    """results: per-store dicts from read_store -> (sites for report, all ranked offers)."""
    tc = acfg["trust"]
    sites, all_ranked = [], []
    for res in results:
        priced = []
        if res["offers"]:
            row = store_rows["amazon_" + res["site"]]
            priced = [pricing.price_offer(o, row, routes, rates, today, tc, acfg["assumed_kg"])
                      for o in res["offers"]]
        ranked = pricing.rank(priced, acfg["top_per_store"], tc["band"])
        sites.append(dict(res, ranked=ranked, offers=None))
        all_ranked.extend(ranked)
    return sites, all_ranked


def runner_up(all_ranked, pick, band):
    rest = [p for p in all_ranked if p is not pick and p["total_amd"] is not None]
    return min(rest, key=lambda p: pricing.order_key(p, band)) if rest else None


# ------------------------------------------------------------------ jobs

def question_buttons(job_id, qi, q):
    return [[(o, "am:q:%s:%d:%d" % (job_id, qi, oi)) for oi, o in enumerate(q["options"])][:4],
            [("➡️ Skip - search as is", "am:q:%s:%d:-1" % (job_id, qi))]]


def ask_question(tg, cfg, root, pend, qi):
    q = pend["plan"]["questions"][qi]
    tg.send_html(cfg, "🛒 <b>Amazon search</b> · %s\n%s" % (report.esc(pend["description"]),
                                                             report.esc(q["q"])),
                 silent=True, buttons=question_buttons(pend["job"], qi, q), chat_id=pend["chat_id"])


def browser_session(acfg, log):
    from scrapers.market import Session
    return Session(pause=tuple(acfg["pause_s"]), log=log, who="the /amazon search",
                   lock_wait_s=acfg["browser_wait_s"])


def run_search(job, cfg, root, tg, today, log=print, plan_fn=runner.plan, reason_fn=runner.reason,
               session_factory=browser_session, rates_get=rates_mod.get, now=time.time):
    acfg = load_cfg(root)
    chat, desc = job["chat_id"], job["description"]
    full = desc + ("; " + "; ".join(job["answers"]) if job.get("answers") else "")
    plan, usage = job.get("plan"), {}
    if not plan:
        try:
            plan, usage["plan_model"] = plan_fn(cfg, acfg, full)     # answers, if any, are in `full`
        except Exception as e:  # noqa: BLE001 - any failure is told to the asker, never silent
            log("plan failed: %s" % e)
            tg.send_html(cfg, "⚠️ Amazon search: I could not understand the request this time "
                              "(%s). Try again with a few more words." % report.esc(str(e)[:80]),
                         silent=True, chat_id=chat)
            return "plan_failed"
        if plan["vague"] and not job.get("answers") and not job.get("no_questions"):
            pend = {"job": job["job"], "chat_id": chat, "description": desc, "plan": plan,
                    "stores": job.get("stores"), "answers": [], "saved": time.time()}
            write_json(root, "pending_%s.json" % job["job"], pend)
            ask_question(tg, cfg, root, pend, 0)
            return "asked"
    ok, why = limits.can_start(root, today, acfg["max_searches_per_day"])
    if not ok:
        tg.send_html(cfg, "🛑 " + report.esc(why), silent=True, chat_id=chat)
        return "limit"
    wanted = [s for s in (job.get("stores") or acfg["stores"]) if s in SITES]
    store_rows = stores_mod.load()
    results, todo = [], []
    for s in wanted:
        left = limits.cooling(root, s, acfg["cooldown_hours"])
        if left > 0:
            results.append({"site": s, "status": "cooling", "offers": [], "query": plan["queries"][s],
                            "search_url": parse.search_url(s, plan["queries"][s]), "seen": 0, "read": 0,
                            "pages": 0, "notice": "usable again in about %d h" % math.ceil(left)})
        else:
            todo.append(s)
    started, pages = now(), 0
    names = acfg["amazon_seller_names"]
    if todo:
        limits.count_run(root, today)
        try:
            session = session_factory(acfg, log)
            session.__enter__()
        except Exception as e:  # noqa: BLE001 - BrowserBusy, Playwright missing, profile broken
            log("browser unavailable: %s" % e)
            tg.send_html(cfg, "⚠️ Amazon search: the bot's browser is busy or unavailable (%s). "
                              "Try again in a few minutes." % report.esc(str(e)[:100]),
                         silent=True, chat_id=chat)
            return "browser"
        try:
            for i, s in enumerate(todo, start=1):
                try:
                    res = read_store(session, s, plan["queries"][s], full, acfg, root, today,
                                     store_rows["amazon_" + s], names, log=log)
                except Exception as e:  # noqa: BLE001 - a store never takes the others down
                    log("%s failed: %s" % (s, e))
                    res = {"site": s, "status": "error", "notice": str(e)[:120], "offers": [],
                           "query": plan["queries"][s], "search_url": parse.search_url(s, plan["queries"][s]),
                           "seen": 0, "read": 0, "pages": 0}
                results.append(res)
                pages += res["pages"]
                log("%s: %s seen %d read %d pages %d %s" % (s, res["status"], res["seen"], res["read"],
                                                          res["pages"], res.get("notice") or ""))
                tg.send_html(cfg, report.progress(s, i, len(todo), res["status"]), silent=True, chat_id=chat)
        finally:
            session.__exit__(None, None, None)
    results.sort(key=lambda r: wanted.index(r["site"]))
    routes, tariffs_date = pricing.load_routes(root)
    rates = rates_get(root, today)
    sites_out, all_ranked = assemble(results, acfg, routes, rates, today, store_rows)
    band = acfg["trust"]["band"]
    pick, why = pricing.best_pick(all_ranked, band)
    usage.update(pages=pages, browser_s=round(now() - started))
    if pick:
        reason, ru = reason_fn(cfg, acfg, pick, runner_up(all_ranked, pick, band))
        usage["reason_model"] = ru
        why = reason or why
    rich, plain, btns = report.build(job["job"], full, sites_out, pick, why, rates, tariffs_date)
    if not report.fits(rich):
        kind = "plain"
        tg.send_html(cfg, plain, silent=True, buttons=btns, chat_id=chat)
    else:
        kind, _ = tg.send_rich(cfg, rich, plain, silent=True, buttons=btns, chat_id=chat)
    usage["total_s"] = round(now() - started)
    log("answer sent as %s; usage %s" % (kind, usage))
    save_last(root, chat, {"job": job["job"], "description": full, "plan": plan, "sites": sites_out,
                           "rich": rich, "plain": plain, "buttons": btns, "usage": usage,
                           "sent_utc": datetime.now(UTC).isoformat(timespec="seconds")})
    return kind
