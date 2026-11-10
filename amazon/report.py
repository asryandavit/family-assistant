"""The /amazon answer: one Telegram Rich Message (sendRichMessage) and the same content as plain
HTML for the fallback (docs/briefs/AMAZON_SEARCH.md §1). Layout, folds and the block limit are
china/report.py's - its helpers are imported, not copied. Every number comes from
amazon/pricing.py; the only model words are the 🏆 reason, escaped. Links are built in code from
ASINs.

Buttons (am:): 👁 Watch <n> adds the exact /dp/ link through the Market watch add path.
The 📱 Open in app button waits for the generic results screen (brief §4.1, P1b): the Mini App
screen reads China's saved answer, so a button here would open the wrong page.
"""
from amazon import parse
from china.report import (  # noqa: F401 - re-exported for callers and tests
    NO_WEIGHT,
    amd,
    attr,
    block_count,
    esc,
    fits,
    rich_button,
    route_lines,
    short,
    usd,
)
from market import pricing as mpricing

SYMBOL = {"GBP": "£", "EUR": "€", "USD": "$"}
SELLER_SHORT = {parse.AMAZON: "Amazon", parse.DISPATCHED: "via Amazon", parse.THIRD: "3rd party",
                parse.UNREAD: "not read"}
SELLER_ICON = {parse.AMAZON: "🟢", parse.DISPATCHED: "🟡", parse.THIRD: "🟠", parse.UNREAD: "⚪"}
STATUS_TEXT = {
    "check": "🚫 %s showed a check page - not bypassed; skipped (and not opened again for 24 h)",
    "setup": "⚙️ %s is not set to the warehouse address - skipped (run python scrapers/market.py --setup)",
    "cooling": "⏳ %s skipped: a check page was seen recently",
    "error": "⚠️ %s could not be read this time",
    "empty": "🤷 %s: no results could be read",
    "skipped": "⏭ %s not searched",
}


def money(x, cur):
    return "not read" if x is None else "%s%s" % (SYMBOL.get(cur, cur + " "), "{:,.2f}".format(x))


def seller_line(p):
    s = p.get("seller") or {}
    return "%s %s" % (SELLER_ICON[s.get("class", parse.UNREAD)], esc(s.get("evidence") or "seller not read"))


def price_line(p):
    s = "%s → %s AMD · %s" % (money(p["price"], p["currency"]), amd(p["price_amd"]), usd(p.get("price_usd")))
    if p.get("list_price") is not None:
        s += " (was %s)" % money(p["list_price"], p["currency"])
    if p.get("price_kind") == "voucher_available":
        s += "<br>🎟 a voucher lowers it at checkout - not counted"
    return s


def weight_line(p):
    if p["weight_assumed"]:
        return [NO_WEIGHT]
    out = ["Weight %g kg (from the page)" % p["kg"]]
    if p.get("dims_cm"):
        out.append("Size %s cm" % " × ".join("%g" % d for d in p["dims_cm"]))
    return out


def delivery_line(p):
    t = p.get("delivery_text") or "delivery not shown"
    note = p.get("delivery_note") or ""
    s = "Amazon delivery to the warehouse: %s" % esc(t)
    if p.get("delivery_fee") is None:
        s += " <i>(%s - not counted in the total)</i>" % esc(note or "fee unknown")
    elif p.get("delivery_fee"):
        s += " <i>(%s counted)</i>" % money(p["delivery_fee"], p["currency"])
    return s


def detail_lines(p):
    L = [price_line(p), delivery_line(p)]
    L.extend(weight_line(p))
    L.extend(route_lines(p))
    L.append("Seller: " + seller_line(p))
    L.append("🛡 <b>Trust %g</b>: %s" % (p["trust"], " · ".join(
        "%s %s%g" % (esc(lbl), "+" if v > 0 else "", v) for lbl, v in p["trust_parts"])))
    if p.get("sponsored"):
        L.append("📢 Sponsored result - never the 🏆 pick while an organic one is priced")
    for n in p.get("notes") or []:
        L.append("ℹ️ " + esc(n))
    L.append('<a href="%s">Open on %s</a>' % (attr(p["url"]), parse.NAME[p["site"]]))
    return L


def numbered(sites):
    out, n = [], 0
    for s in sites:
        for p in s.get("ranked") or []:
            n += 1
            out.append((n, p))
    return out


def headline(p, n):
    return "%d. %s · %s" % (n, esc(short(p.get("title") or p["id"], 60)), parse.NAME[p["site"]])


def pick_lines(pick, reason, n):
    if not pick:
        return ["No result could be priced - see each store below."]
    seller = (pick["seller"].get("evidence") or "seller not read").split(" · ")[0]
    L = ["🏆 <b>%s</b>" % headline(pick, n),
         "%s · <b>%s AMD</b> (%s) via %s" % (esc(seller), amd(pick["total_amd"]), usd(pick["total_usd"]),
                                            mpricing.label(pick["best"])),
         "Why: " + esc(reason)]
    if pick["weight_assumed"]:
        L.append(NO_WEIGHT)
    return L


def store_status_line(s):
    st = s.get("status")
    if st == "ok":
        return None
    line = STATUS_TEXT.get(st, STATUS_TEXT["error"]) % parse.NAME[s["site"]]
    if s.get("notice"):
        line += " <i>(%s)</i>" % esc(short(s["notice"], 140))
    if s.get("search_url"):
        line += ' · <a href="%s">search it yourself</a>' % attr(s["search_url"])
    return line


def seen_line(s):
    if s.get("status") != "ok":
        return None
    return "%s: saw %d result%s, read %d in detail" % (
        parse.NAME[s["site"]], s.get("seen", 0), "" if s.get("seen") == 1 else "s", s.get("read", 0))


def buttons(job, shown):
    watch = [("👁 Watch %d" % n, "am:watch:%s:%d" % (job, n)) for n, p in shown
             if p.get("price") is not None][:12]
    return [watch[i:i + 4] for i in range(0, len(watch), 4)]


def build(job, query, sites, pick, reason, rates, tariffs_date):
    """(rich_html, plain_html, button_rows). sites: [{site, status, notice, query, search_url,
    seen, read, ranked}] in display order."""
    shown = numbered(sites)
    num = {id(p): n for n, p in shown}
    read = [parse.NAME[s["site"]] for s in sites if s.get("status") == "ok"]
    searched = " · ".join("%s <code>%s</code>" % (parse.FLAG[s["site"]], esc(s["query"]))
                          for s in sites if s.get("query"))
    ctx = "%s · most trusted first (🛡), then cheapest delivered to Yerevan" % (", ".join(read) or "no store read")
    foot = "CBA %s · tariffs %s · customs: forwarders' rule (€200 duty-free, 15%% above), estimate" % (
        rates.get("date", "?") if rates else "no rates", tariffs_date or "?")
    title = "🛒 Amazon search · %s" % esc(short(query, 60))
    seen = [x for x in (seen_line(s) for s in sites) if x]
    statuses = [x for x in (store_status_line(s) for s in sites) if x]
    btns = buttons(job, shown)

    R = ["<p><b>%s</b></p>" % title, "<p><i>%s</i></p>" % esc(ctx)]
    if searched:
        R.append("<p>Searched: %s</p>" % searched)
    R.append("<p>%s</p>" % "<br>".join(pick_lines(pick, reason, num.get(id(pick), 0))))
    R.extend("<p>%s</p>" % x for x in statuses)
    if seen:
        R.append("<p><i>%s</i></p>" % esc(" · ".join(seen)))
    for s in sites:
        ranked = s.get("ranked") or []
        if not ranked:
            continue
        rows = ['<tr><th>#</th><th>Item</th><th>Seller</th><th align="right">Total AMD</th></tr>']
        for p in ranked:
            rows.append('<tr><td>%d</td><td>%s</td><td>%s %s</td><td align="right">%s%s%s</td></tr>' % (
                num[id(p)], esc(short(p.get("title") or p["id"], 30)),
                SELLER_ICON[p["seller"]["class"]], SELLER_SHORT[p["seller"]["class"]],
                amd(p["total_amd"]), "*" if p["weight_assumed"] and p["total_amd"] is not None else "",
                " 📢" if p.get("sponsored") else ""))
        R.append("<table bordered striped compact><caption>%s %s</caption>%s</table>" % (
            parse.FLAG[s["site"]], parse.NAME[s["site"]], "".join(rows)))
        for p in ranked:
            R.append("<details><summary>%s</summary><p>%s</p></details>" % (
                headline(p, num[id(p)]), "<br>".join(detail_lines(p))))
    if any(p["weight_assumed"] for _, p in shown):
        R.append("<p><i>* weight not listed: shipping estimated for 1 kg</i></p>")
    R.append("<p><i>%s</i></p>" % esc(foot))
    R.append("".join("<tg-button-row>%s</tg-button-row>" % "".join(rich_button(lbl, d) for lbl, d in row)
                     for row in btns))
    rich = "".join(R)

    P = ["<b>%s</b>" % title, "<i>%s</i>" % esc(ctx)]
    if searched:
        P.append("Searched: " + searched)
    P.append("━━━━━━━━━━━━")
    P.extend(pick_lines(pick, reason, num.get(id(pick), 0)))
    P.extend(statuses)
    if seen:
        P.append("<i>%s</i>" % esc(" · ".join(seen)))
    for s in sites:
        ranked = s.get("ranked") or []
        if not ranked:
            continue
        P.append("━━━━━━━━━━━━")
        P.append("%s <b>%s</b>" % (parse.FLAG[s["site"]], parse.NAME[s["site"]]))
        for p in ranked:
            P.append("%s - %s AMD%s%s" % (headline(p, num[id(p)]), amd(p["total_amd"]),
                                           "*" if p["weight_assumed"] and p["total_amd"] is not None else "",
                                           " 📢" if p.get("sponsored") else ""))
            P.append("<blockquote expandable>%s</blockquote>" % "\n".join(
                x.replace("<br>", "\n") for x in detail_lines(p)))
    P.append("━━━━━━━━━━━━")
    P.append("<i>%s</i>" % esc(foot))
    return rich, "\n".join(P), btns


def progress(site, done, total, status):
    mark = "done" if status == "ok" else {"check": "check page", "setup": "not set up",
                                           "cooling": "skipped"}.get(status, "not read")
    return "⏳ %s %s (%d/%d)…" % (parse.NAME[site], mark, done, total)
