"""The basket: the family's shopping list priced at both shops (decision 084).

Deterministic arithmetic only (CLAUDE.md §2) -- every price is a value a shop
returned; costs are whole packages x package price, or kg x price per kg for
items sold by weight. Nothing is ever estimated: an item without a matching
product is "no match" and stays out of every total.

    parse_mapping(md)            plan/meals/basket.md -> rows
    line_for(row, item)          what buying `row` as `item` costs
    best_per_shop(row, items)    cheapest sensible product at each shop
    price_basket(rows, results)  chosen shop per item, totals, comparison
    month_projection / budget_verdict   the monthly budget check
"""
import re
from decimal import ROUND_CEILING, Decimal

from lib import parse_grocery as pg

LISTS = ("weekly", "monthly")
UNITS = ("kg", "l", "pcs", "pack")
SHOPS = ("yc", "parma")            # Yerevan City first: the usual winner (decision 081)

# A package up to 10% under the amount counts as enough (950 g for "1 kg").
SHORT_OK = Decimal("0.9")
WEEKS_PER_MONTH = Decimal(52) / Decimal(12)
MAX_QTY = Decimal(100)

_PCS_RE = re.compile(r"(\d+)\s*(?:pcs|pc|pieces)\b", re.I)


def _d(x):
    return Decimal(str(x))


def _phrases(cell):
    """'a, b c' -> [['a'], ['b', 'c']] (token lists, empty ones dropped)."""
    return [t for t in (pg._tokens(p) for p in (cell or "").split(",")) if t]


def parse_qty(text, unit, item):
    """'3.5' / '3,5' -> Decimal; whole numbers for pcs and pack. ValueError with a
    sentence a person can act on when the cell is wrong."""
    t = (text or "").strip().replace(",", ".")
    try:
        q = Decimal(t)
    except ArithmeticError:
        raise ValueError("%s: amount %r is not a number (write 1.5, or skip)" % (item, text))
    if not (0 < q <= MAX_QTY):
        raise ValueError("%s: amount %s is out of range (above 0, up to %s)" % (item, t, MAX_QTY))
    if unit in ("pcs", "pack") and q != q.to_integral_value():
        raise ValueError("%s: %s must be a whole number of %s" % (item, t, unit))
    return q


def parse_mapping(md_text):
    """Rows of the tables in plan/meals/basket.md:

        | List | Item | Search | Match | Qty | Unit | Exclude | Shop | Note |

    -> [{"list", "item", "search", "match": [alternatives], "qty": Decimal|None,
         "unit", "exclude": [token lists], "shop": "yc"|"parma"|None, "note",
         "skip": bool}]
    Only lines whose first cell is weekly/monthly are rows; anything else in the
    file (headers, prose) is ignored. A malformed row raises ValueError.
    """
    rows = []
    for line in (md_text or "").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or cells[0].lower() not in LISTS:
            continue
        if len(cells) < 9:
            raise ValueError("basket row has %d columns, expected 9: %s" % (len(cells), line.strip()))
        lst, item, search, match, qty, unit, exclude, shop, note = cells[:9]
        if not item:
            raise ValueError("basket row without an item name: %s" % line.strip())
        row = {"list": lst.lower(), "item": item, "search": search, "note": note,
               "match": [m.strip() for m in match.split(";") if m.strip()],
               "exclude": _phrases(exclude), "unit": unit.lower() or None,
               "shop": None, "qty": None, "skip": qty.strip().lower() == "skip"}
        if shop.strip():
            s = {"yc": "yc", "yerevan city": "yc", "parma": "parma"}.get(shop.strip().lower())
            if not s:
                raise ValueError("%s: shop %r is not yc or parma" % (item, shop))
            row["shop"] = s
        if not row["skip"]:
            if row["unit"] not in UNITS:
                raise ValueError("%s: unit %r is not one of %s" % (item, unit, ", ".join(UNITS)))
            if not search or not row["match"]:
                raise ValueError("%s: needs Search and Match words" % item)
            row["qty"] = parse_qty(qty, row["unit"], item)
        rows.append(row)
    return rows


# --------------------------------------------------------------- one line

def pcs_from_name(name):
    """Pieces per package from the name ('Eggs "Koko" 10pcs' -> 10), or None."""
    m = _PCS_RE.search(name or "")
    return int(m.group(1)) if m and int(m.group(1)) > 0 else None


def size_label(size, unit):
    """Decimal('0.8'), 'kg' -> '800 g'; Decimal('1'), 'l' -> '1 l'."""
    if size < 1:
        return "%s %s" % (format((size * 1000).normalize(), "f"), "g" if unit == "kg" else "ml")
    return "%s %s" % (format(size.normalize(), "f"), unit)


def _packs(qty, size):
    """Whole packages so that packs x size >= qty x SHORT_OK (at least one)."""
    n = (qty * SHORT_OK / size).to_integral_value(rounding=ROUND_CEILING)
    return max(int(n), 1)


def line_for(row, i):
    """What buying `row` as product `i` costs, or None when the product can't be
    bought in that unit (e.g. a by-weight item for a count of cans).

    -> {"item", "cost" (int AMD), "buy" ("2 × 800 g"), "bought" (Decimal, in the
        row's unit), "min_order" (True when the shop's minimum is more than asked)}
    """
    qty, unit = row["qty"], row["unit"]
    price = _d(i["price"])
    min_order = False
    if unit in ("kg", "l"):
        if i["sold_by_weight"]:
            if unit != "kg":
                return None
            amount = qty
            if i.get("min_qty") and _d(i["min_qty"]) > qty:
                amount, min_order = _d(i["min_qty"]), True
            return {"item": i, "cost": pg.amd(price * amount), "bought": amount,
                    "buy": "%s kg" % format(amount.normalize(), "f"), "min_order": min_order}
        size = pg.size_from_name(i["name"])
        if not size or size[1] != unit:
            return None
        sz = _d(round(size[0], 3))
        if sz <= 0:
            return None
        n = _packs(qty, sz)
        return {"item": i, "cost": pg.amd(price * n), "bought": sz * n,
                "buy": "%d × %s" % (n, size_label(sz, unit)), "min_order": False}
    if i["sold_by_weight"]:
        return None
    if unit == "pcs":
        per = pcs_from_name(i["name"])
        if not per:
            return None
        n = _packs(qty, _d(per))
        return {"item": i, "cost": pg.amd(price * n), "bought": _d(per * n),
                "buy": "%d × %d pcs" % (n, per), "min_order": False}
    # pack: whole packs, bunches or cans, as many as asked for
    n = int(qty)
    size = pg.size_from_name(i["name"])
    buy = ("%d × %s" % (n, size_label(_d(round(size[0], 3)), size[1])) if size
           else "%d pc%s" % (n, "" if n == 1 else "s"))
    return {"item": i, "cost": pg.amd(price * n), "bought": qty, "buy": buy,
            "min_order": False}


# ------------------------------------------------------------- choosing

def _excluded(name, exclude):
    ws = pg._tokens(name)
    return any(all(any(pg._same_word(t, w) for w in ws) for t in ph) for ph in exclude)


LEAD_SKIP = pg.DESCRIPTORS | {"canned"}
LEAD_WORDS = 2


def leads(name, alt, words=None):
    """True when one of the first LEAD_WORDS words of the name (descriptors such
    as "fresh", "canned" skipped) is a word of the Match alternative.

    Shop names lead with the product type ("Cucumber (russian) kg", "Greenhouse
    tomatoes", "Canned mackerel"), while things that merely contain it put it
    later ("Cat food Whiskas trout", "Hummus Ayo green walnut") -- whole-word
    matching alone would price shampoo as olive oil.
    """
    _, groups = pg.expand_query(alt, words)
    want = [t for g in groups for ph in g for t in ph]
    head = [t for t in pg._tokens(name) if t not in LEAD_SKIP][:LEAD_WORDS]
    return any(pg._same_word(t, w) for t in head for w in want)


def candidates(row, items, words=None):
    """Available products whose name matches a Match alternative (and leads with
    it, see leads()) and no Exclude phrase. Each product once."""
    seen, out = set(), []
    for alt in row["match"]:
        for i in pg.rank(items, alt, sort="cheap", words=words):
            key = (i["shop"], i["id"], i["name"])
            if key in seen or _excluded(i["name"], row["exclude"]) or not leads(i["name"], alt, words):
                continue
            seen.add(key)
            out.append(i)
    return out


def _key(line):
    i = line["item"]
    return (line["cost"], i["unit_price"] is None, i["unit_price"] or 0, i["name"])


def best_per_shop(row, items, words=None):
    """{shop: cheapest line} among the matching products. The cheapest line cost
    wins even when it means buying a bit more (a shop's minimum order, a bigger
    pack that costs less in total); ties go to the lower price per kg/l."""
    best = {}
    for i in candidates(row, items, words):
        ln = line_for(row, i)
        if ln and (i["shop"] not in best or _key(ln) < _key(best[i["shop"]])):
            best[i["shop"]] = ln
    return best


def choose(row, per_shop):
    """(shop, line) for the row: the preferred shop when it has a match, else the
    cheaper line (Yerevan City on a tie). (None, None) without any match."""
    if row.get("shop") in per_shop:
        return row["shop"], per_shop[row["shop"]]
    if not per_shop:
        return None, None
    shop = min(per_shop, key=lambda s: (per_shop[s]["cost"], SHOPS.index(s) if s in SHOPS else 9))
    return shop, per_shop[shop]


def price_basket(rows, results, words=None):
    """rows: parse_mapping() rows of one list. results: {search text: grocery.search()
    result}. -> {
        "lines": [{"row", "status": "ok"|"no match"|"skipped"|"unavailable",
                   "shop", "line", "per_shop"}],
        "totals": {"yc": int, "parma": int, "all": int},
        "compare": {"n", "yc", "parma", "cheapest"}   -- items found at BOTH shops
        "partial": bool, "failed": [shops that errored]}
    """
    lines, totals = [], {"yc": 0, "parma": 0, "all": 0}
    cmp = {"n": 0, "yc": 0, "parma": 0, "cheapest": 0}
    failed, partial = set(), False
    for row in rows:
        if row["skip"]:
            lines.append({"row": row, "status": "skipped", "shop": None, "line": None, "per_shop": {}})
            continue
        res = results.get(row["search"]) or {"items": [], "status": {s: "error: not searched" for s in SHOPS}}
        bad = [s for s, st in res.get("status", {}).items() if st != "ok"]
        failed.update(bad)
        per_shop = best_per_shop(row, res.get("items") or [], words)
        shop, line = choose(row, per_shop)
        if line is None:
            status = "unavailable" if bad else "no match"
            partial = True
        else:
            status = "ok"
            totals[shop] += line["cost"]
            totals["all"] += line["cost"]
        if "yc" in per_shop and "parma" in per_shop:
            cmp["n"] += 1
            cmp["yc"] += per_shop["yc"]["cost"]
            cmp["parma"] += per_shop["parma"]["cost"]
            cmp["cheapest"] += min(per_shop["yc"]["cost"], per_shop["parma"]["cost"])
        lines.append({"row": row, "status": status, "shop": shop, "line": line, "per_shop": per_shop})
    return {"lines": lines, "totals": totals, "compare": cmp,
            "partial": partial or bool(failed), "failed": sorted(failed)}


def by_shop(basket):
    """[(shop, [entries], subtotal)] for shops with chosen items, Yerevan City first."""
    out = []
    for shop in SHOPS:
        entries = [e for e in basket["lines"] if e["status"] == "ok" and e["shop"] == shop]
        if entries:
            out.append((shop, entries, sum(e["line"]["cost"] for e in entries)))
    return out


def not_priced(basket):
    return [e for e in basket["lines"] if e["status"] != "ok"]


# --------------------------------------------------------------- budget

def month_projection(weekly_total=None, monthly_total=None):
    """Weekly total x 52/12 plus the monthly staples, whole AMD. Either may be None
    (not priced in this run); None when both are."""
    if weekly_total is None and monthly_total is None:
        return None
    w = _d(weekly_total or 0) * WEEKS_PER_MONTH
    return pg.amd(w + _d(monthly_total or 0))


def budget_verdict(month, lo, hi):
    """('under' | 'within' | 'over', AMD away from the nearest edge, 0 when within)."""
    if month < lo:
        return "under", lo - month
    if month > hi:
        return "over", month - hi
    return "within", 0
