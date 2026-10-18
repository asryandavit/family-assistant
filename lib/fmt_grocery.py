"""Telegram message for /price. Layout only -- every number arrives computed
by lib.parse_grocery."""
from lib.fmt import BAR
from lib.parse_grocery import amd
from lib.telegram import esc

SHOP_NAMES = {"parma": "Parma", "yc": "Yerevan City"}
SHOP_DOT = {"parma": "\U0001f7e2", "yc": "\U0001f534"}   # green / red circle


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
    bits.append(SHOP_NAMES.get(i["shop"], i["shop"]))
    return head + "\n   " + " · ".join(bits)


def compare_block(cmp, pairs, pair_limit=4):
    """⚖️ best price per shop + 🔁 same product at both shops. [] if neither."""
    out = []
    if cmp:
        unit = cmp["unit"]
        out.append("⚖️ <b>Compare</b> <i>(cheapest per %s at each shop)</i>" % unit)
        for shop in ("parma", "yc"):
            i = cmp["best"].get(shop)
            if i:
                out.append('%s %s: <b>%s/%s</b> — <a href="%s">%s</a>'
                           % (SHOP_DOT[shop], SHOP_NAMES[shop], money(i["unit_price"]), unit,
                              i["url"], esc(i["name"][:55])))
        if cmp["cheaper"] and cmp["pct"]:
            out.append("→ <b>%s</b> is %d%% cheaper per %s"
                       % (SHOP_NAMES[cmp["cheaper"]], cmp["pct"], unit))
        else:
            out.append("→ same price per %s at both shops" % unit)
        out.append("<i>Cheapest match at each shop — brand or quality may differ.</i>")
    if pairs:
        if out:
            out.append("")
        out.append("\U0001f501 <b>Same product, both shops</b>")
        for p, y, diff, pct in pairs[:pair_limit]:
            if diff < 0:
                verdict = "Yerevan City −%s (−%d%%)" % (money(-diff), pct)
            elif diff > 0:
                verdict = "Parma −%s (−%d%%)" % (money(diff), pct)
            else:
                verdict = "same price"
            unit = "/kg" if p["sold_by_weight"] else ""
            out.append('• %s — %s <a href="%s">%s%s</a> · %s <a href="%s">%s%s</a> → %s'
                       % (esc(p["name"][:45]), SHOP_DOT["parma"], p["url"], money(p["price"]), unit,
                          SHOP_DOT["yc"], y["url"], money(y["price"]), unit, verdict))
        if len(pairs) > pair_limit:
            out.append("<i>…%d more products sold at both</i>" % (len(pairs) - pair_limit))
    return out


def build(query, ranked, status, totals=None, sort="cheap", limit=10,
          searched=None, cmp=None, pairs=None):
    order = "cheapest per kg/l first" if sort == "cheap" else "best match first"
    shops = [SHOP_NAMES[s] for s in status]
    title = esc(query)
    if searched and searched.lower() != (query or "").strip().lower():
        title += " <i>(%s)</i>" % esc(searched)
    out = ["\U0001f6d2 <b>PRICES · %s</b>" % title,
           "<i>%s · %s</i>" % (order, " + ".join(shops)), BAR]
    if not ranked:
        out.append("Nothing matched <b>%s</b>." % esc(query))
        out.append("<i>Try the product type first, in English or Armenian: "
                   "<code>/price lentils</code>, <code>/price մածուն</code>, "
                   "<code>/price chicken breast</code>.</i>")
    block = compare_block(cmp, pairs or [])
    if block:
        out += block + [BAR]
    for n, i in enumerate(ranked[:limit], 1):
        out.append(_line(n, i))
    if len(ranked) > limit:
        out.append("<i>…and %d more matches</i>" % (len(ranked) - limit))
    for shop, st in status.items():
        if st != "ok":
            out.append("⚠️ <i>%s unavailable this run (%s)</i>"
                       % (SHOP_NAMES.get(shop, shop), esc(st)))
    out += [BAR, "<i>\U0001f7e2 Parma · \U0001f534 Yerevan City · "
                 "prices change; tap a name to check and order</i>"]
    return "\n".join(out)
