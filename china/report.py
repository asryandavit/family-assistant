"""The /china answer: one Telegram Rich Message (sendRichMessage, Bot API 10.1–10.3) and the
same content as plain HTML for the fallback (docs/briefs/CHINA_SEARCH.md §5.1).

Rules seen on the owner's iPhone (P0): a newline in rich HTML is a space -> <br>; tables
≤ 4 columns with short cells; long parts in <details>; buttons use data=, not
callback_data=. Every number comes from china/pricing.py; model words are escaped and
shown as words only. Links are built in code from item ids.
"""
import html

from china import parse
from market import pricing as mpricing
from market import workdays

SITE_NAME = {"pinduoduo": "Pinduoduo", "taobao": "Taobao", "1688": "1688"}
SITE_ICON = {"pinduoduo": "🟥", "taobao": "🟧", "1688": "🟦"}
RICH_LIMIT = 32000            # Telegram: 32,768 UTF-8 characters
BLOCK_LIMIT = 480             # Telegram: 500 blocks incl. rows, list items, details
SELLER_MSG = "您好，请问这个商品包装后的重量（公斤）和尺寸（长×宽×高，厘米）是多少？谢谢！"
SELLER_MSG_PLUG = "您好，请问这个商品包装后的重量（公斤）和尺寸（长×宽×高，厘米）是多少？有欧标插头吗？谢谢！"
NO_WEIGHT = "⚠️ SHIPPING ESTIMATED FOR 1 KG — WEIGHT NOT LISTED"
OVER_1KG = "⚠️ PROBABLY OVER 1 KG"
POIZON = "👟 Also check Poizon (得物) on your phone — it has authenticated sneakers and clothes."
STATUS_TEXT = {
    "login": "🔑 %s logged out — open Chrome on the PC and sign in",
    "check": "🚫 %s showed a check page — not bypassed; open it yourself",
    "error": "⚠️ %s could not be read this time",
    "skipped": "⏭ %s not searched",
    "link": "🔗 %s is not read automatically (its sign-in check blocks the bot)",
}


def esc(s):
    return html.escape(str(s), quote=False)


def attr(s):
    return html.escape(str(s), quote=True)


def amd(x):
    return "—" if x is None else "{:,.0f}".format(round(x))


def usd(x):
    return "—" if x is None else "${:,.2f}".format(x)


def cny(x, cur="CNY"):
    if x is None:
        return "not read"
    sym = "$" if cur == "USD" else "¥"
    return sym + ("{:,.0f}".format(x) if x == int(x) else "{:,.2f}".format(x))


def short(s, n):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def route_label(ln):
    return mpricing.label(ln)


def weight_line(p):
    if p["weight_assumed"]:
        lines = [NO_WEIGHT]
    else:
        lines = ["Weight %g kg (from the page)" % p["kg"]]
    if p.get("likely_over_1kg") and p["weight_assumed"]:
        reason = (" — " + esc(p["over_1kg_reason"])) if p.get("over_1kg_reason") else ""
        lines.append(OVER_1KG + reason)
    if p.get("dims_note"):
        lines.append("Size: " + esc(p["dims_note"]))
    return lines


SUSPICIOUS = ("SUSPICIOUSLY CHEAP — far below the other listings; often a fake rating, a "
              "different item or a missing part. Not used for the 🏆 pick.")


def price_line(p):
    kind = {"after_coupon": "after coupon", "group": "group price (拼单)", "first_item":
            "first-item price", "tier": "price for the smallest quantity", "single": "single buy",
            "list": "", "unknown": ""}.get(p.get("price_kind") or "", "")
    s = "%s%s → %s AMD · %s" % (cny(p["price"], p.get("currency")), (" " + kind) if kind else "",
                                amd(p["price_amd"]), usd(p["price_usd"]))
    if p.get("promo"):
        s += "<br>⚠️ %s — the normal price is higher; not used for the 🏆 pick" % esc(p["promo"])
    if p.get("suspicious"):
        s += "<br>⚠️ " + SUSPICIOUS
    if p["site"] == "pinduoduo" and not p.get("variant"):
        s += "<br>⚠️ Listing price — may be a cheaper variant than the one you want."
    if p["site"] == "pinduoduo" and p.get("single_price") is None:
        s += "<br><i>Group price; the single-buy price is only in the PDD app.</i>"
    elif p.get("single_price") is not None:
        s += "<br>Single buy %s" % cny(p["single_price"])
    return s


def route_lines(p):
    q = p.get("quote")
    if not q:
        return ["Shipping: no price, so no totals"]
    out = []
    for ln in sorted(q["lines"], key=lambda x: (x["total_amd"] is None, x["total_amd"] or 0)):
        parts = ["%s %s" % (route_label(ln), amd(ln.get("ship_amd")))]
        if ln.get("customs_amd"):
            parts.append("customs %s" % amd(ln["customs_amd"]))
        parts.append("<b>total %s</b>" % amd(ln.get("total_amd")))
        rt = workdays.range_text(ln.get("days"))
        if rt:
            parts.append(rt)
        out.append(" · ".join(parts))
    if any(ln.get("customs_near") for ln in q["lines"]):
        out.append("⚠️ Customs: within 10% of the €200 limit")
    return out


def seller_line(p):
    lab = parse.LABEL[p["seller"]]
    shop = (" · " + esc(p["shop_name"])) if p.get("shop_name") else ""
    ev = (" <i>(%s)</i>" % esc(p["seller_evidence"])) if p.get("seller_evidence") else ""
    return lab + shop + ev


def detail_lines(p, category):
    L = []
    if p.get("variant"):
        L.append("Variant: " + esc(p["variant"]))
    L.append(price_line(p))
    L.append(esc(p["delivery_note"]))
    L.extend(weight_line(p))
    L.extend(route_lines(p))
    L.append("Seller: " + seller_line(p))
    if p.get("sales") is not None:
        L.append("Sold: %s" % "{:,}".format(p["sales"]))
    if p.get("min_order_text"):
        L.append("Minimum order: " + esc(p["min_order_text"]))
    specs = list((p.get("specs") or {}).items())[:6]
    if specs:
        L.append("Specs: " + "; ".join("%s: %s" % (esc(k), esc(v)) for k, v in specs))
    if p.get("material"):
        L.append("Material: " + esc(p["material"]))
    if p.get("size_advice"):
        L.append("Size: " + esc(p["size_advice"]))
    if p.get("reviews_read"):
        n = " (%s reviews)" % "{:,}".format(p["reviews"]) if p.get("reviews") is not None else ""
        if p.get("liked"):
            L.append("👍 " + "; ".join(esc(x) for x in p["liked"]) + n)
        if p.get("complaints"):
            L.append("👎 " + "; ".join(esc(x) for x in p["complaints"]))
        elif p.get("liked"):
            L.append("👎 no complaints found in the reviews read")
    elif p.get("reviews") is not None:
        L.append("💬 %s reviews — tap 💬 Reviews to read them" % "{:,}".format(p["reviews"]))
    for f in p.get("flags") or []:
        L.append("⚠️ " + parse.RESTRICT_TEXT[f])
    if p.get("why"):
        L.append("<i>" + esc(p["why"]) + "</i>")
    if p["weight_assumed"]:
        msg = SELLER_MSG_PLUG if category == "electronics" else SELLER_MSG
        L.append("Ask the seller: <code>%s</code>" % esc(msg))
    if p.get("link"):
        L.append('<a href="%s">Open on %s</a>' % (attr(p["link"]), SITE_NAME[p["site"]]))
    return L


def numbered(sites):
    """[(n, priced)] in display order: sites in order, each site's ranked list."""
    out, n = [], 0
    for s in sites:
        for p in s.get("ranked") or []:
            n += 1
            out.append((n, p))
    return out


def headline(p, n):
    return "%d. %s · %s" % (n, esc(short(p["title_en"], 60)), SITE_NAME[p["site"]])


def pick_lines(pick, reason, n):
    if not pick:
        return ["No result could be priced — see each site below."]
    b = pick["best"]
    L = ["🏆 <b>%s</b>" % headline(pick, n),
         "%s · <b>%s AMD</b> (%s) via %s" % (parse.LABEL[pick["seller"]], amd(pick["total_amd"]),
                                            usd(pick["total_usd"]), route_label(b)),
         "Why: " + esc(reason)]
    if pick["weight_assumed"]:
        L.append(NO_WEIGHT)
    return L


def site_status_line(s, query):
    st = s.get("status")
    if st == "ok":
        if s.get("notice"):
            return "ℹ️ %s: <i>%s</i>" % (SITE_NAME[s["site"]], esc(short(s["notice"], 160)))
        return None
    line = STATUS_TEXT.get(st, STATUS_TEXT["error"]) % SITE_NAME[s["site"]]
    if s.get("notice"):
        line += " <i>(%s)</i>" % esc(short(s["notice"], 120))
    link = parse.search_link(s["site"], query)
    if link:
        line += ' · <a href="%s">%s</a>' % (attr(link), "open this search on Taobao" if st == "link"
                                             else "search it yourself")
    return line


def buttons(job, sites, shown):
    """Rows of (label, callback data) — ids only, 64-byte cap (TELEGRAM_UX.md §3)."""
    rows = [[("🔁 Only " + SITE_NAME[s], "cn:only:%s:%s" % (s, job)) for s in SITE_NAME]]
    rev = [("💬 Reviews %d" % n, "cn:rev:%s:%d" % (job, n)) for n, p in shown
           if not p.get("reviews_read")][:8]
    watch = [("👁 Watch %d" % n, "cn:watch:%s:%d" % (job, n)) for n, p in shown
             if p.get("price") is not None][:8]
    for group in (rev, watch):
        for i in range(0, len(group), 4):
            rows.append(group[i:i + 4])
    return rows


def _context(query, sites, rates, tariffs_date):
    read = [SITE_NAME[s["site"]] for s in sites if s.get("status") == "ok"]
    ctx = "%s · top %s each by total to Yerevan" % (", ".join(read) or "no site read",
                                                    max([len(s.get("ranked") or []) for s in sites] + [0]))
    foot = "CBA %s · tariffs %s · customs: forwarders' rule (€200 duty-free, 15%% above), estimate" % (
        rates.get("date", "?") if rates else "no rates", tariffs_date or "?")
    return ctx, foot


def build(job, query, sites, pick, reason, groups, rates, tariffs_date, category,
          brand_guidance=None, search_query=None):
    """(rich_html, plain_html, button_rows). query is the owner's words (the header);
    search_query is the plan's short Chinese search words, used in the 'search it yourself'
    links — the owner's words with the question answers made Taobao match 'it' to the i.t
    clothing brand (phone demo 2026-11-09)."""
    link_q = search_query or query
    shown = numbered(sites)
    num = {id(p): n for n, p in shown}
    ctx, foot = _context(query, sites, rates, tariffs_date)
    title = "🇨🇳 China search · %s" % esc(short(query, 60))

    # ---------------------------------------------------------------- rich
    R = ["<p><b>%s</b></p>" % title, "<p><i>%s</i></p>" % esc(ctx)]
    R.append("<p>%s</p>" % "<br>".join(pick_lines(pick, reason, num.get(id(pick), 0))))
    for s in sites:
        st = site_status_line(s, link_q)
        if st:
            R.append("<p>%s</p>" % st)
    if brand_guidance:
        R.append("<p>🏷 <i>%s</i></p>" % esc(brand_guidance))
    if category in ("clothes", "shoes"):
        R.append("<p>%s</p>" % POIZON)
    flags = sorted({f for _, p in shown for f in p.get("flags") or []})
    for f in flags:
        R.append("<p>⚠️ %s</p>" % esc(parse.RESTRICT_TEXT[f]))
    for s in sites:
        ranked = s.get("ranked") or []
        if not ranked:
            continue
        rows = ["<tr><th>#</th><th>Item</th><th>Seller</th><th align=\"right\">Total AMD</th></tr>"]
        for p in ranked:
            rows.append("<tr><td>%d</td><td>%s</td><td>%s</td><td align=\"right\">%s%s%s%s</td></tr>" % (
                num[id(p)], esc(short(p["title_en"], 34)), parse.LABEL[p["seller"]].split(" ")[0],
                amd(p["total_amd"]), "*" if p["weight_assumed"] and p["total_amd"] is not None else "",
                " promo" if p.get("promo") else "", " ⚠️" if p.get("suspicious") else ""))
        R.append('<table bordered striped compact><caption>%s %s</caption>%s</table>' % (
            SITE_ICON[s["site"]], SITE_NAME[s["site"]], "".join(rows)))
        for p in ranked:
            R.append("<details><summary>%s</summary><p>%s</p></details>" % (
                headline(p, num[id(p)]), "<br>".join(detail_lines(p, category))))
    if any(p["weight_assumed"] for _, p in shown):
        R.append("<p><i>* weight not listed: shipping estimated for 1 kg</i></p>")
    if any(p.get("suspicious") for _, p in shown):
        R.append("<p><i>⚠️ suspiciously cheap: far below the other listings, never the 🏆 pick</i></p>")
    if groups:
        g = ["<br>".join("%s: %s AMD (#%d)" % (SITE_NAME[p["site"]], amd(p["total_amd"]), num[id(p)])
                         for p in grp if id(p) in num) for grp in groups]
        R.append("<details><summary>⚖️ Same product on several sites</summary><p>%s</p></details>"
                 % "<br><br>".join(x for x in g if x))
    R.append("<p><i>%s</i></p>" % esc(foot))
    btns = buttons(job, [s["site"] for s in sites], shown)
    R.append("".join("<tg-button-row>%s</tg-button-row>" % "".join(
        '<tg-button type="callback_data" data="%s">%s</tg-button>' % (attr(d), esc(lbl))
        for lbl, d in row) for row in btns))
    rich = "".join(R)

    # ---------------------------------------------------------------- plain
    P = ["<b>%s</b>" % title, "<i>%s</i>" % esc(ctx), "━━━━━━━━━━━━"]
    P.extend(pick_lines(pick, reason, num.get(id(pick), 0)))
    for s in sites:
        st = site_status_line(s, link_q)
        if st:
            P.append(st)
    if brand_guidance:
        P.append("🏷 <i>%s</i>" % esc(brand_guidance))
    if category in ("clothes", "shoes"):
        P.append(POIZON)
    for f in flags:
        P.append("⚠️ " + esc(parse.RESTRICT_TEXT[f]))
    for s in sites:
        ranked = s.get("ranked") or []
        if not ranked:
            continue
        P.append("━━━━━━━━━━━━")
        P.append("%s <b>%s</b>" % (SITE_ICON[s["site"]], SITE_NAME[s["site"]]))
        for p in ranked:
            P.append("%s — %s AMD%s%s" % (headline(p, num[id(p)]), amd(p["total_amd"]),
                                          "*" if p["weight_assumed"] and p["total_amd"] is not None else "",
                                          " ⚠️ suspiciously cheap" if p.get("suspicious") else ""))
            P.append("<blockquote expandable>%s</blockquote>" % "\n".join(
                x.replace("<br>", "\n") for x in detail_lines(p, category)))
    P.append("━━━━━━━━━━━━")
    P.append("<i>%s</i>" % esc(foot))
    plain = "\n".join(P)
    return rich, plain, btns


def block_count(rich):
    """Rough count of Telegram rich blocks: paragraphs, rows, details, button rows."""
    return sum(rich.count(t) for t in ("<p>", "<tr>", "<details>", "<tg-button-row>", "<table"))


def fits(rich):
    return len(rich) <= RICH_LIMIT and block_count(rich) <= BLOCK_LIMIT


def progress(site, done, total, status):
    mark = "done" if status == "ok" else {"login": "logged out", "check": "check page",
                                          "skipped": "skipped"}.get(status, "not read")
    return "⏳ %s %s (%d/%d)…" % (SITE_NAME[site], mark, done, total)
