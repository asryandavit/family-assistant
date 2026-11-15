"""Quality rules for the basket: the best value among acceptable products, not just
the cheapest (decision 106).

The shops' data only has product names and prices (no ratings, ingredients or country
fields; discovery 2026-11-15, decision 106), so every rule reads the product name:

    Avoid      a product whose name has one of these words is never picked
    Require    the name must have at least one of these ("extra virgin")
    Prefer     preferred products may cost up to Premium % more than the cheapest
               acceptable one ("fresh" chicken over frozen)
    Min fat %  the fat % in the name must be at least this (unknown fat = rejected)
    Max price  AMD per kg / l / piece / pack (the row's unit), on what is actually
               bought, so a shop minimum or a bigger pack counts

One more guard applies to every row, rules or not: an item sold by weight whose
price per kg the shop did not show is skipped. Parma lists some loose produce at the
price of its minimum amount with no per-kg text ("Fuji Apples kg Sh": 130 for 0.1 kg),
and the basket used to cost that as 130 per kg. A price is never guessed.

Rows without a rule pick exactly what lib.basket.best_per_shop picks (tested).
Every pick that is not simply the cheapest carries a reason in plain words.

    parse_rules(md, rows=None)        the "Quality rules and aisles" table -> {item: rule}
    evaluate(row, items, words, rule) every candidate with its line and why it was rejected
    make_picker(rules)                drop-in for best_per_shop in lib.basket.price_basket
    explain_none(row, items, ...)     why a row with rules found nothing acceptable
"""
import re
from decimal import Decimal, InvalidOperation

from lib import basket as bk
from lib import parse_grocery as pg

DEFAULT_PREMIUM = 20          # % a preferred product may cost over the cheapest acceptable
MAX_PREMIUM = 100
HEADER = ("item", "aisle", "avoid", "require", "prefer", "premium %", "min fat %",
          "max price", "why")
DEFAULT_AISLE = "Other"

_FAT_RE = re.compile(r"(\d+(?:[.,․]\d+)?)\s*%")


# ------------------------------------------------------------------ parsing

def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _number(text, item, what, lo, hi, whole=False):
    """'3,2 %' / '8000 AMD' -> Decimal in [lo, hi]; '' -> None. ValueError with a
    sentence the owner can act on."""
    t = re.sub(r"(?i)\s*(%|amd|֏|dram)\s*$", "", (text or "").strip()).replace(",", ".")
    t = t.replace(" ", "")
    if not t:
        return None
    try:
        v = Decimal(t)
    except InvalidOperation:
        raise ValueError(f"{item}: {what} {text!r} is not a number")
    if not (lo <= v <= hi):
        raise ValueError(f"{item}: {what} {t} is out of range ({lo} to {hi})")
    if whole and v != v.to_integral_value():
        raise ValueError(f"{item}: {what} must be a whole number")
    return v


def _words(cell):
    """'a, b c' -> [('a', ['a']), ('b c', ['b', 'c'])]: the phrase as written and its tokens."""
    out = []
    for p in (cell or "").split(","):
        p = p.strip()
        toks = pg._tokens(p)
        if toks:
            out.append((p, toks))
    return out


def parse_rules(md_text, rows=None):
    """The table under a header row `| Item | Aisle | Avoid | Require | Prefer |
    Premium % | Min fat % | Max price | Why |` in plan/meals/basket.md ->
    {item: {"aisle", "avoid", "require", "prefer", "premium", "min_fat",
            "max_price", "why"}}.
    rows: parse_mapping() rows; when given, an item not among them is an error (a
    typo would otherwise silently switch a rule off)."""
    lines = (md_text or "").splitlines()
    start = None
    for n, line in enumerate(lines):
        if line.strip().startswith("|") and tuple(c.lower() for c in _cells(line)[:9]) == HEADER:
            start = n + 1
            break
    if start is None:
        return {}
    known = {r["item"] for r in rows} if rows is not None else None
    rules = {}
    for line in lines[start:]:
        if not line.strip().startswith("|"):
            break
        cells = _cells(line)
        if set("".join(cells)) <= set("-: "):
            continue                                   # the |---|---| line
        if len(cells) < 9:
            raise ValueError(f"quality row has {len(cells)} columns, expected 9: {line.strip()}")
        item, aisle, avoid, require, prefer, premium, fat, ceiling, why = cells[:9]
        if not item:
            raise ValueError(f"quality row without an item name: {line.strip()}")
        if known is not None and item not in known:
            raise ValueError(f"quality rule for {item!r}: no such item in the basket tables "
                             "(check the spelling)")
        if item in rules:
            raise ValueError(f"{item}: two quality rows")
        rule = {"aisle": aisle or DEFAULT_AISLE, "avoid": _words(avoid),
                "require": _words(require), "prefer": _words(prefer),
                "premium": _number(premium, item, "premium %", 0, MAX_PREMIUM, whole=True),
                "min_fat": _number(fat, item, "min fat %", 0, 100),
                "max_price": _number(ceiling, item, "max price", 1, 10_000_000),
                "why": why}
        if rule["premium"] is not None and not rule["prefer"]:
            raise ValueError(f"{item}: a premium % without Prefer words does nothing")
        if rule["prefer"] and rule["premium"] is None:
            rule["premium"] = Decimal(DEFAULT_PREMIUM)
        rules[item] = rule
    return rules


def aisle_of(rules, item):
    r = rules.get(item)
    return r["aisle"] if r else DEFAULT_AISLE


def has_checks(rule):
    return bool(rule and (rule["avoid"] or rule["require"] or rule["prefer"]
                          or rule["min_fat"] is not None or rule["max_price"] is not None))


# ---------------------------------------------------------------- judging

def fat_pct(name):
    """'Milk "Marianna" 3․2% 450ml' -> Decimal('3.2'); None when no % in the name."""
    m = _FAT_RE.search(name or "")
    return Decimal(m.group(1).replace(",", ".").replace("․", ".")) if m else None


def _has(name, phrase_tokens):
    ws = pg._tokens(name)
    return all(any(pg._same_word(t, w) for w in ws) for t in phrase_tokens)


def _first(name, phrases):
    for text, toks in phrases:
        if _has(name, toks):
            return text
    return None


def per_unit(line):
    """AMD per kg / l / piece / pack actually paid (the row's unit)."""
    b = line["bought"]
    return pg.amd(Decimal(line["cost"]) / b) if b else None


UNIT_WORD = {"kg": "kg", "l": "l", "pcs": "pc", "pack": "pack"}


def unknown_price(line):
    """Sold by weight, but the shop showed no price per kg (decision 106)."""
    i = line["item"]
    return bool(i["sold_by_weight"] and i.get("unit_price") is None)


def rejection(row, line, rule):
    """Why this product may not be picked, in plain words, or None."""
    i = line["item"]
    name = i["name"]
    if unknown_price(line):
        return ("price per kg not shown (the price is for {} kg)".format(format(i["min_qty"], "g"))
                if i.get("min_qty") else "price per kg not shown")
    if not rule:
        return None
    hit = _first(name, rule["avoid"])
    if hit:
        return f"“{hit}” is on your avoid list"
    if rule["require"] and not _first(name, rule["require"]):
        return "not {}".format(" or ".join(t for t, _ in rule["require"]))
    if rule["min_fat"] is not None:
        f = fat_pct(name)
        if f is None:
            return "fat % not on the label (want {}%+)".format(format(rule["min_fat"].normalize(), "f"))
        if f < rule["min_fat"]:
            return "{}% fat, below {}%".format(format(f.normalize(), "f"),
                                             format(rule["min_fat"].normalize(), "f"))
    if rule["max_price"] is not None:
        pu = per_unit(line)
        if pu is not None and pu > rule["max_price"]:
            return "{} ֏/{}, over your {} ceiling".format(format(pu, ","), UNIT_WORD[row["unit"]],
                                                      format(int(rule["max_price"]), ","))
    return None


def evaluate(row, items, words=None, rule=None):
    """[{"line", "rejected": reason|None, "preferred": phrase|None}] for every
    candidate that can be bought in the row's unit, cheapest first (best_per_shop's
    order: line cost, then price per kg/l, then name)."""
    out = []
    for i in bk.candidates(row, items, words):
        ln = bk.line_for(row, i)
        if not ln:
            continue
        out.append({"line": ln, "rejected": rejection(row, ln, rule),
                    "preferred": _first(i["name"], rule["prefer"]) if rule else None})
    out.sort(key=lambda e: bk._key(e["line"]))
    return out


def short(name, n=26):
    """'Olive oil "Campagna" g/b 1l' -> 'Campagna'; names without a brand are cut."""
    m = re.search(r"[\"“«]([^\"”»]{2,30})[\"”»]", name or "")
    return m.group(1) if m else (name or "")[:n]


def _money(v):
    return "{} ֏".format(format(int(v), ","))


def _reason(pick, cheapest, n_rejected_cheaper, rule):
    """Why `pick` and not the overall cheapest line `cheapest`, or None when it is it."""
    if pick is cheapest:
        return None
    pl, cl = pick["line"], cheapest["line"]
    diff = cl["cost"] - pl["cost"]
    if cheapest["rejected"]:
        more = f"; {n_rejected_cheaper - 1} more skipped" if n_rejected_cheaper > 1 else ""
        if unknown_price(cl):              # its "price" is for 100 g: not really cheaper
            return "{} skipped: no price per kg shown{}".format(short(cl["item"]["name"]), more)
        return "{} is {} less but {}{}".format(short(cl["item"]["name"]), _money(-diff),
                                         cheapest["rejected"], more)
    if pick["preferred"] and cl["cost"]:
        pct = (Decimal(pl["cost"] - cl["cost"]) * 100 / cl["cost"]).quantize(Decimal(1))
        return "{}, +{}% over {} (limit {}%)".format(pick["preferred"], pct,
                                                 short(cl["item"]["name"]), int(rule["premium"]))
    return None


def pick_shop(evals, rule):
    """The pick among one shop's evaluated candidates, or None: the cheapest
    acceptable one, unless a preferred one costs at most Premium % more."""
    ok = [e for e in evals if not e["rejected"]]
    if not ok:
        return None
    best = ok[0]
    if rule and rule["prefer"] and not best["preferred"]:
        pref = [e for e in ok if e["preferred"]]
        if pref and Decimal(pref[0]["line"]["cost"]) <= \
                Decimal(best["line"]["cost"]) * (1 + rule["premium"] / 100):
            best = pref[0]
    return best


def _rank(e, rule):
    """Cross-shop comparison value (lib.basket.choose): a preferred line counts as
    cost / (1 + premium), so it wins over another shop's line only within the premium."""
    c = Decimal(e["line"]["cost"])
    if rule and e["preferred"]:
        return c / (1 + rule["premium"] / 100)
    return c


def pick(row, items, words=None, rule=None):
    """{shop: line + "reason" + "rank"} -- the same shape as best_per_shop."""
    evals = evaluate(row, items, words, rule)
    if not evals:
        return {}
    cheapest = evals[0]
    out = {}
    for shop in sorted({e["line"]["item"]["shop"] for e in evals}):
        best = pick_shop([e for e in evals if e["line"]["item"]["shop"] == shop], rule)
        if not best:
            continue
        cheaper_rejected = sum(1 for e in evals if e["rejected"]
                               and e["line"]["cost"] < best["line"]["cost"])
        line = dict(best["line"])
        line["reason"] = _reason(best, cheapest, cheaper_rejected, rule)
        line["rank"] = _rank(best, rule)
        out[shop] = line
    return out


def make_picker(rules):
    """picker(row, items, words) for lib.basket.price_basket."""
    def picker(row, items, words=None):
        return pick(row, items, words, rules.get(row["item"]))
    return picker


def explain_none(row, items, words=None, rule=None):
    """When nothing was acceptable: 'nothing passes your rules — cheapest: X (why)'.
    None when there were no candidates at all (a plain 'no match')."""
    evals = evaluate(row, items, words, rule)
    if not evals or any(not e["rejected"] for e in evals):
        return None
    c = evals[0]
    return "nothing passes your rules — cheapest was {} ({})".format(
        short(c["line"]["item"]["name"]), c["rejected"])
