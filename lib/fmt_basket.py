"""The basket as a Telegram message and as Shopping-list Sheet rows.
Layout only -- every number arrives computed by lib.basket (CLAUDE.md §2).

    🧺 Basket · weekly                       header
    Mon 19 Oct · 23 items · cheapest shop per item
    ━━━━━━━━━━━━
    💰 Total · per shop
    📅 month projection vs the 80–100k budget
    ⚖️ one shop only vs cheapest of each (items found at both shops)
    ▸ 🔴 Yerevan City   folded: amount, product link, 📱 app, line cost
    ▸ 🟢 Parma
    ▸ Not priced        skipped (as needed) and no match
"""
from lib import basket as bk
from lib import ui
from lib.fmt_grocery import SHOP_DOT, SHOP_NAMES, _app, money
from lib.sheets_checklist import link
from lib.telegram import esc

TITLES = {"weekly": "weekly", "monthly": "monthly"}
TABS = {"weekly": "This week", "monthly": "Monthly staples"}
MAX_CHARS = 3900          # one Telegram message, with headroom
NAME_LENGTHS = (60, 40, 28, 0)   # product names shrink until the message fits


def k(v):
    """82000 -> '82k' (budget range labels only)."""
    return "%gk" % (v / 1000.0)


def _status_text(e):
    if e["status"] == "skipped":
        return "skipped — %s" % (e["row"]["note"] or "not priced")
    if e["status"] == "unavailable":
        return "not priced — shop unavailable this run"
    return "no match at either shop"


def _amount(row):
    if row["qty"] is None:
        return ""
    q = format(row["qty"].normalize(), "f")
    return "%s %s" % (q, {"pack": "pack" if row["qty"] == 1 else "packs"}.get(row["unit"], row["unit"]))


def _price_text(i):
    if i["sold_by_weight"]:
        return "%s/kg" % money(i["price"])
    return money(i["price"])


def budget_lines(kind, totals, budget):
    """📅 line(s): the month at this run's prices against the budget.
    totals: {"weekly": int|None, "monthly": int|None} for the lists priced."""
    lo, hi = budget
    rng = "%s–%s" % (k(lo), k(hi))
    w, m = totals.get("weekly"), totals.get("monthly")
    if w is not None and m is not None:
        month = bk.month_projection(w, m)
        verdict, diff = bk.budget_verdict(month, lo, hi)
        say = {"within": "within", "under": "%s under" % money(diff),
               "over": "<b>%s over</b>" % money(diff)}[verdict]
        return ["📅 Month ≈ <b>%s</b> (fresh × 4.33 + staples) · budget %s: %s"
                % (money(month), rng, say)]
    if w is not None:
        return ["\U0001f4c5 Fresh ≈ <b>%s</b>/month (× 4.33) · budget %s with staples "
                "(/basket monthly)" % (money(bk.month_projection(w, None)), rng)]
    return ["\U0001f4c5 Staples <b>%s</b>/month · budget %s with fresh (/basket weekly)"
            % (money(m), rng)]


def compare_line(cmp):
    """⚖️ one shop for everything vs the cheapest of each, over items at both."""
    if not cmp["n"]:
        return None
    save = cmp[min(("yc", "parma"), key=lambda s: cmp[s])] - cmp["cheapest"]
    return ("⚖️ %d items at both shops: all %s %s · all %s %s · cheapest of each "
            "<b>%s</b>%s"
            % (cmp["n"], SHOP_DOT["yc"], money(cmp["yc"]), SHOP_DOT["parma"], money(cmp["parma"]),
               money(cmp["cheapest"]), (" (saves %s)" % money(save)) if save else ""))


def _item_line(e, name_len):
    """name_len > 0: '• Eggs 2 × 10 pcs · <product name> · 📱 app · 1,980 ֏'.
    name_len 0 (compact): '• <Eggs> 2 × 10 pcs · 1,980 ֏ 📱' -- the item name is
    the product link; the full product name stays in the Sheet."""
    ln = e["line"]
    i = ln["item"]
    minimum = " <i>(shop minimum)</i>" if ln["min_order"] else ""
    if not name_len:
        app = (' <a href="%s">\U0001f4f1</a>' % i["app_url"]) if i.get("app_url") else ""
        return '• <a href="%s">%s</a> %s%s · %s%s' % (i["url"], esc(e["row"]["item"]), esc(ln["buy"]),
                                                    minimum, format(ln["cost"], ","), app)
    return '• <b>%s</b> %s%s · <a href="%s">%s</a>%s · %s' % (
        esc(e["row"]["item"]), esc(ln["buy"]), minimum, i["url"], esc(i["name"][:name_len]),
        _app(i), money(ln["cost"]))


def _build(kind, b, when, budget, totals, name_len):
    n_items = sum(1 for e in b["lines"] if e["status"] != "skipped")
    head = ui.header("\U0001f9fa", "Basket", TITLES.get(kind, kind),
                     "%s · %d items" % (ui.day_label(when), n_items))
    groups = bk.by_shop(b)
    shops = " · ".join("%s %s" % (SHOP_DOT[s], money(t)) for s, _, t in groups)
    body = ["\U0001f4b0 <b>Total %s</b>%s" % (money(b["totals"]["all"]), (" · " + shops) if shops else "")]
    body += budget_lines(kind, totals, budget)
    cl = compare_line(b["compare"])
    if cl:
        body.append(cl)
    missing = [e for e in bk.not_priced(b) if e["status"] != "skipped"]
    if missing:
        body.append("⚠️ <b>Partial:</b> %d item%s not priced, not in the total — %s"
                    % (len(missing), "" if len(missing) == 1 else "s",
                       esc(", ".join(e["row"]["item"] for e in missing))))
    for shop in b["failed"]:
        body.append("⚠️ <i>%s unavailable this run</i>" % SHOP_NAMES.get(shop, shop))

    folds = []
    for shop, entries, sub in groups:
        folds.append(ui.fold([_item_line(e, name_len) for e in entries],
                             "%s %s · %s (%d)" % (SHOP_DOT[shop], SHOP_NAMES[shop], money(sub),
                                                  len(entries))))
    rest = bk.not_priced(b)
    if rest:
        folds.append(ui.fold(["• %s — %s" % (esc(e["row"]["item"]), esc(_status_text(e))) for e in rest],
                             "Not priced · %d" % len(rest)))
    footer = "<i>Tick off in the checklist · tap an item for its shop page · \U0001f4f1 app</i>"
    return ui.page(head, body, "\n".join(f for f in folds if f), footer)


def build(kind, b, when, budget, totals):
    """The Telegram message, kept to one message where possible: product names
    get shorter until it fits; lib.telegram._split keeps folds valid if not."""
    for name_len in NAME_LENGTHS:
        msg = _build(kind, b, when, budget, totals, name_len)
        if len(msg) <= MAX_CHARS:
            return msg
    return msg


# ------------------------------------------------------------------ Sheet

HEADER = ["Done", "Item", "Buy", "Shop", "Product", "App", "Price", "Line cost"]
MONEY_COL = 7


def sheet_rows(kind, b, when, budget, totals):
    """Rows for the tab plus where the checkboxes and bold rows go:
    -> (rows, checkbox_rows, bold_rows), row indexes 0-based."""
    lo, hi = budget
    rows, boxes, bold = [], [], []

    def add(r, box=False, strong=False):
        if box:
            boxes.append(len(rows))
        if strong:
            bold.append(len(rows))
        rows.append(r)

    title = "\U0001f9fa Basket · %s — priced %s %s · cheapest shop per item" % (
        TABS.get(kind, kind), ui.day_label(when), when.strftime("%H:%M"))
    add([title], strong=True)
    w, m = totals.get("weekly"), totals.get("monthly")
    if w is not None and m is not None:
        month = bk.month_projection(w, m)
        verdict, diff = bk.budget_verdict(month, lo, hi)
        check = {"within": "within budget", "under": "%s under budget" % money(diff),
                 "over": "%s OVER budget" % money(diff)}[verdict]
        add(["Month ≈ %s (fresh × 4.33 + staples) · budget %s–%s · %s"
             % (money(month), money(lo), money(hi), check)])
    elif w is not None:
        add(["Fresh ≈ %s per month (× 4.33 weeks) · budget %s–%s for everything"
             % (money(bk.month_projection(w, None)), money(lo), money(hi))])
    else:
        add(["Staples %s per month · budget %s–%s for everything" % (money(m), money(lo), money(hi))])
    add([])
    add(HEADER, strong=True)
    for shop, entries, sub in bk.by_shop(b):
        add(["", "%s %s" % (SHOP_DOT[shop], SHOP_NAMES[shop])], strong=True)
        for e in entries:
            ln, i = e["line"], e["line"]["item"]
            add([False, e["row"]["item"],
                 ln["buy"] + (" (shop minimum)" if ln["min_order"] else ""),
                 SHOP_NAMES[shop], link(i["url"], i["name"]),
                 link(i["app_url"], "\U0001f4f1") if i.get("app_url") else "",
                 _price_text(i), ln["cost"]], box=True)
        add(["", "%s total" % SHOP_NAMES[shop], "", "", "", "", "", sub], strong=True)
    add(["", "Total", "", "", "", "", "", b["totals"]["all"]], strong=True)
    rest = bk.not_priced(b)
    if rest:
        add([])
        add(["", "Not priced (not in the total)"], strong=True)
        for e in rest:
            add([False, e["row"]["item"], _amount(e["row"]), "", _status_text(e)], box=True)
    return rows, boxes, bold
