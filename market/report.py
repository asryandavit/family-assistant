"""The nightly report and the alerts (docs/briefs/MARKET_WATCH.md §5, §9 fallback).

Layout only: every number arrives computed (market/pricing.py). Per item one headline
line (best total, the route, its arrival, the change vs yesterday) and the per-store
details folded underneath. Prices that were not re-read tonight are marked ⚠️ with their
date; an item never read shows "no price yet" with its link — never a guessed number.
"""
from datetime import date

from lib import ui
from lib.telegram import esc
from market import pricing, workdays

SYM = {"USD": "$", "GBP": "£", "EUR": "€"}
SUFFIX = {"RUB": " ₽", "AMD": " ֏", "CNY": " ¥"}
DROP_PCT = 10.0


def amd(x):
    return "{:,.0f}".format(round(x)) if x is not None else "—"


def money(x, cur):
    if x is None:
        return "—"
    if cur in SYM:
        return SYM[cur] + ("{:,.0f}".format(x) if x == int(x) else "{:,.2f}".format(x))
    return "{:,.0f}{}".format(x, SUFFIX.get(cur, " " + cur))


def short_date(iso):
    d = date.fromisoformat(iso) if isinstance(iso, str) else iso
    return "%d %s" % (d.day, d.strftime("%b"))


def _route_line(ln, kg):
    lab = esc(pricing.label(ln))
    if ln["mode"] == "local":
        return "     in Yerevan · total %s" % amd(ln["total_amd"])
    if ln["mode"] == "direct":
        tail = " · total %s" % amd(ln["total_amd"]) if ln["total_amd"] is not None else ""
        return "     store delivery to Armenia%s" % tail
    parts = ["%s %s/kg" % (lab, amd(ln["per_kg"]))]
    if ln.get("ship_amd") is not None:
        parts[0] += " · %g kg → %s" % (ln["chargeable_kg"], amd(ln["ship_amd"]))
        if ln.get("by_volume"):
            parts[0] += " (by volume)"
    if ln.get("total_amd") is not None:
        parts.append("total %s" % amd(ln["total_amd"]))
    parts.append(workdays.range_text(ln.get("days")))
    if ln.get("arrival"):
        parts.append(workdays.date_text(ln["arrival"]))
    return "     " + " · ".join(parts)


def _customs_line(q):
    vals = [ln["customs_amd"] for ln in q["lines"] if ln.get("customs_amd") is not None]
    if q["value_eur"] is None or not vals:
        return None
    near = any(ln.get("customs_near") for ln in q["lines"])
    flag = " ⚠️ within 10% of €200" if near else ""
    if max(vals) < 0.5:
        return "     customs: none (≤ €200, estimate)%s" % flag
    lo, hi = min(vals), max(vals)
    span = amd(hi) if abs(hi - lo) < 1 else "%s–%s" % (amd(lo), amd(hi))
    return "     customs ≈ %s (estimate; value €%.0f)%s" % (span, q["value_eur"], flag)


def store_block(entry, item):
    """Lines for one store of one item."""
    st = entry["store"]
    name = esc(st["name"])
    link = '<a href="%s">%s</a>' % (esc(entry["url"]), name)
    state = entry["state"]
    if state == "gone":
        return ["  ▸ %s — product page gone (removed by the store?)" % link]
    if state == "none":
        why = " · %s" % esc(entry["why"]) if entry.get("why") else ""
        return ["  ▸ %s — no price yet%s" % (link, why)]
    o, q = entry["offer"], entry["quote"]
    cur = o.get("currency") or st["currency"]
    head = "  ▸ %s %s" % (link, money(o["price"], cur))
    if int(item.get("qty") or 1) > 1:
        head += " × %d" % int(item["qty"])
    if "local" not in st["modes"]:
        if o.get("shipping") is not None:
            head += " + %s to the warehouse" % money(o["shipping"], cur) if st["origin"] != "local" else ""
        else:
            head += " + store delivery unknown"
    if o.get("in_stock") is False:
        head += " · ❌ out of stock"
    if state == "stale":
        head += " · ⚠️ not re-read tonight (%s)" % short_date(o["date_local"])
    elif state == "owner":
        head += " · owner, %s" % short_date(o["date_local"])
    lines = [head]
    kg = (item.get("weight_kg") or 0) * int(item.get("qty") or 1) or None
    for ln in q["lines"]:
        lines.append(_route_line(ln, kg))
    c = _customs_line(q) if "local" not in st["modes"] else None
    if c:
        lines.append(c)
    if q["notes"]:
        lines.append("     <i>%s</i>" % esc("; ".join(q["notes"])))
    return lines


def item_headline(item, entries, change_pct):
    quotes = [e["quote"] for e in entries if e.get("quote")]
    best, store_key, _ = pricing.best_of(quotes)
    name = "<b>%s</b>" % esc(item["name"])
    if not best:
        if not item.get("weight_kg") and quotes:
            return "%s — weight needed for totals (/watch weight %s 2.4)" % (name, item["_n"])
        return "%s — no price yet" % name
    store = next(e for e in entries if e["store"]["key"] == store_key)
    when = ""
    if best.get("arrival"):
        when = ", " + workdays.date_text(dict(best["arrival"], notes=[]))
    text = "%s — best %s AMD (%s · %s%s)" % (name, amd(best["total_amd"]), esc(store["store"]["name"]),
                                           esc(pricing.label(best)), when)
    if store["state"] == "stale":
        text += " ⚠️"
    if store["quote"]["store_ship_amd"] is None and "local" not in store["store"]["modes"]:
        text += " · excl. store delivery"
    if change_pct is not None and abs(change_pct) >= 0.5:
        text += " · %s %+.0f%% vs yesterday" % ("📉" if change_pct < 0 else "📈", change_pct)
    return text


def report(today, items, results, changes, blocked_lines, rates, tariffs_date, rule):
    head = ui.header("\U0001f30d", "Market watch", ui.day_label(today))
    body = []
    for it in items:
        entries = results.get(it["id"], [])
        body.append(item_headline(it, entries, changes.get(it["id"])))
        detail = []
        for e in entries:
            detail += store_block(e, it)
        if detail:
            body.append(ui.fold(detail))
    if not items:
        body.append("The list is empty — add an item with /watch add.")
    body += blocked_lines
    foot = []
    if rates:
        cur = " · ".join(("%s %.1f" if rates["amd_per"][c] >= 10 else "%s %.2f") % (c, rates["amd_per"][c])
                         for c in ("USD", "EUR", "GBP", "RUB") if c in rates["amd_per"])
        foot.append("Rates CBA %s · %s%s" % (short_date(rates["date"]), cur,
                                            " ⚠️ " + esc(rates["note"]) if rates.get("stale") else ""))
    else:
        foot.append("⚠️ No CBA rates — AMD totals not shown")
    if tariffs_date:
        foot.append("tariffs from %s" % short_date(tariffs_date[:10]))
    foot.append("customs: estimate (%s rule)" % rule)
    return ui.page(head, body, footer=" · ".join(foot))


def blocked_line(store_name, n_items, n_kept):
    """'Wildberries blocked tonight — 3 items not re-read (2 on their last price)'."""
    text = "🚫 %s blocked tonight — %d item%s not re-read" % (esc(store_name), n_items,
                                                             "" if n_items == 1 else "s")
    if n_kept:
        text += " (%d on %s last price)" % (n_kept, "its" if n_kept == 1 else "their")
    return text


def drop_alert(item, best_now, best_before, pct, store_name):
    return ("📉 <b>%s</b> dropped %.0f%%: %s AMD (was %s) · %s · %s"
            % (esc(item["name"]), abs(pct), amd(best_now["total_amd"]), amd(best_before),
               esc(store_name), esc(pricing.label(best_now))))


def stock_alert(item, store_name, url, price, cur):
    return ('✅ <b>%s</b> is back in stock at <a href="%s">%s</a> · %s'
            % (esc(item["name"]), esc(url), esc(store_name), money(price, cur)))


def blocked_owner_message(store_name, items_links):
    lines = ["🚫 <b>%s</b> has blocked the bot 3 nights in a row." % esc(store_name),
             "Open the link yourself, or send the price: <code>/watch price &lt;n&gt; &lt;amount&gt;</code>"]
    lines += ['• %s <a href="%s">%s</a>' % (n, esc(u), esc(name)) for n, name, u in items_links]
    return "\n".join(lines)
