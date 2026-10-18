"""Telegram message for /price, in the docs/TELEGRAM_UX.md template.
Layout only -- every number arrives computed by lib.parse_grocery.

    🛒 lentils · ոսպ                     header (+ what was searched)
    cheapest per kg/l first · both shops  subtitle
    ━━━━━━━━━━━━
    ⚖️ verdict: cheapest per kg at each shop, which is cheaper
    top 3 products
    ▸ folded: the rest + the same product at both shops
"""
from lib import ui
from lib.parse_grocery import amd
from lib.telegram import esc

SHOP_NAMES = {"parma": "Parma", "yc": "Yerevan City"}
SHOP_DOT = {"parma": "\U0001f7e2", "yc": "\U0001f534"}   # green / red circle
SHOWN = 3   # products visible before the fold


def money(v):
    """3000 -> '3,000 ֏'."""
    return "%s ֏" % format(amd(v), ",")


def _price_part(i):
    if i["sold_by_weight"]:
        s = "<b>%s/kg</b>" % money(i["price"])
        if i.get("min_qty"):
            s += " <i>(min %g kg)</i>" % i["min_qty"]
    else:
        s = "<b>%s</b>" % money(i["price"])
    if i.get("old_price"):
        s += " <s>%s</s> −%g%%" % (format(amd(i["old_price"]), ","), i["discount_pct"])
    return s


def _line(n, i):
    head = '%d. %s <a href="%s">%s</a>' % (n, SHOP_DOT.get(i["shop"], ""), i["url"],
                                          esc(i["name"][:70]))
    bits = [_price_part(i)]
    if i["unit_price"] is not None and not (i["sold_by_weight"] and i["unit"] == "kg"):
        bits.append("%s/%s" % (money(i["unit_price"]), i["unit"]))
    bits.append(SHOP_NAMES.get(i["shop"], i["shop"]) + _app(i))
    return head + "\n   " + " · ".join(bits)


def _app(i):
    """' · 📱 app' link that opens the shop's iPhone app (Yerevan City only)."""
    if not i.get("app_url"):
        return ""
    return ' · <a href="%s">\U0001f4f1 app</a>' % i["app_url"]


def compare_lines(cmp):
    """⚖️ cheapest per kg/l at each shop + the verdict. [] without a comparison."""
    if not cmp:
        return []
    unit = cmp["unit"]
    out = ["⚖️ <b>Cheapest per %s</b>" % unit]
    for shop in sorted(cmp["best"], key=lambda s: cmp["best"][s]["unit_price"]):
        i = cmp["best"][shop]
        out.append('%s %s <b>%s</b> — <a href="%s">%s</a>%s'
                   % (SHOP_DOT[shop], SHOP_NAMES[shop], money(i["unit_price"]), i["url"],
                      esc(i["name"][:45]), _app(i)))
    if cmp["cheaper"] and cmp["pct"]:
        out.append("→ <b>%s is %d%% cheaper</b> per %s"
                   % (SHOP_NAMES[cmp["cheaper"]], cmp["pct"], unit))
    else:
        out.append("→ same price per %s at both shops" % unit)
    out.append("<i>Cheapest match at each shop — brand or quality may differ.</i>")
    return out


def pair_lines(pairs, limit=6):
    """🔁 products sold at both shops, biggest price gap first."""
    if not pairs:
        return []
    out = ["\U0001f501 <b>Same product, both shops</b>"]
    for p, y, diff, pct in pairs[:limit]:
        if diff < 0:
            verdict = "Yerevan City −%d%%" % pct
        elif diff > 0:
            verdict = "Parma −%d%%" % pct
        else:
            verdict = "same price"
        unit = "/kg" if p["sold_by_weight"] else ""
        app = (' <a href="%s">\U0001f4f1</a>' % y["app_url"]) if y.get("app_url") else ""
        out.append('• %s: %s <a href="%s">%s%s</a> · %s <a href="%s">%s%s</a>%s → %s'
                   % (esc(p["name"][:40]), SHOP_DOT["parma"], p["url"], money(p["price"]), unit,
                      SHOP_DOT["yc"], y["url"], money(y["price"]), unit, app, verdict))
    if len(pairs) > limit:
        out.append("<i>…%d more sold at both</i>" % (len(pairs) - limit))
    return out


def compare_block(cmp, pairs, pair_limit=4):
    """Both comparison parts, separated by a blank line ([] when neither)."""
    a, b = compare_lines(cmp), pair_lines(pairs or [], pair_limit)
    return a + ([""] if a and b else []) + b


MAX_CHARS = 3900   # one Telegram message (4096) with headroom


def build(query, ranked, status, totals=None, sort="cheap", limit=10,
          searched=None, cmp=None, pairs=None):
    """The /price message, kept to ONE Telegram message: if it's too long, fewer
    extra products and pairs are folded in -- the verdict and top 3 always stay."""
    pair_limit = 6
    while True:
        msg = _build(query, ranked, status, sort, limit, searched, cmp, pairs, pair_limit)
        if len(msg) <= MAX_CHARS:
            return msg
        if limit > SHOWN:
            limit -= 1
        elif pair_limit > 0:
            pair_limit -= 1
        else:
            return msg            # still long: lib.telegram splits it safely


def _build(query, ranked, status, sort, limit, searched, cmp, pairs, pair_limit):
    order = "cheapest per kg/l first" if sort == "cheap" else "best match first"
    shops = " + ".join(SHOP_NAMES[s] for s in status)
    context = searched if searched and searched.lower() != (query or "").strip().lower() else None
    head = ui.header("\U0001f6d2", query, context, "%s · %s" % (order, shops))

    body = []
    if not ranked:
        body += ["Nothing matched <b>%s</b>." % esc(query),
                 "<i>Try the product type first, in English or Armenian: "
                 "<code>/price lentils</code>, <code>/price մածուն</code>, "
                 "<code>/price chicken breast</code>.</i>"]
    verdict = compare_lines(cmp)
    if verdict:
        body += verdict + [""]
    body += [_line(n, i) for n, i in enumerate(ranked[:SHOWN], 1)]
    for shop, st in status.items():
        if st != "ok":
            body.append("⚠️ <i>%s unavailable this run (%s)</i>"
                        % (SHOP_NAMES.get(shop, shop), esc(st)))

    rest = [_line(n, i) for n, i in enumerate(ranked[SHOWN:limit], SHOWN + 1)]
    if len(ranked) > limit:
        rest.append("<i>…and %d more matches</i>" % (len(ranked) - limit))
    both = pair_lines(pairs or [], pair_limit) if pair_limit else []
    titles = []
    if ranked[SHOWN:limit]:
        titles.append("%d more" % len(ranked[SHOWN:limit]))
    if both:
        titles.append("same product at both shops")
    folded = ui.fold(rest + ([""] if rest and both else []) + both,
                     " · ".join(titles).capitalize() if titles else None)

    footer = "<i>\U0001f7e2 Parma · \U0001f534 Yerevan City · prices change; tap a name to order</i>"
    return ui.page(head, body, folded, footer)
