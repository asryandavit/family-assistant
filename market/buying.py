"""market/buying.md -> the "How to buy" steps on a /china or /amazon result (CROSS_BORDER.md X1).

Words come from the hand-edited table; every number comes from the result's quote
(market.pricing.quote). The one sum computed here is the fastest route's difference from the
cheapest one, AMD minus AMD. Steps are plain text; the report escapes them.

    data = load()                         # both tables, from market/buying.md
    how_to(data, "amazon_de", quote, price_text="€12.99", delivery_text="…", flags=[], today=…)
        -> ["Buy on amazon.de with your card — €12.99.", "Deliver to …", …]

A store with no row gets no steps (an empty list), never invented ones. A row checked more than
STALE_DAYS ago keeps its steps and adds a dated warning.
"""
import datetime
import os
import re

from market import DIR, workdays
from market import pricing as mpricing
from market import stores as stores_mod

STALE_DAYS = 90
COUNTRY = {"china": "China", "uk": "UK", "germany": "Germany", "italy": "Italy", "usa": "USA",
           "russia": "Russia", "uae": "UAE", "greece": "Greece", "spain": "Spain", "poland": "Poland",
           "korea": "Korea"}
ITEM_WORD = {"battery": "battery", "liquid": "liquid", "magnet": "magnets", "aerosol": "aerosol"}
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _tables(text):
    """{section heading: [row dicts]} for every '## heading' that holds a markdown table."""
    out, head, cols, section = {}, None, None, None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            section, cols = line[3:].strip().lower(), None
            continue
        if not line.startswith("|") or section is None:
            cols = None if not line.startswith("|") else cols
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cols is None:
            cols = [c.lower() for c in cells]
            head = True
            continue
        if head:  # the |---| line
            head = False
            continue
        out.setdefault(section, []).append(dict(zip(cols, cells)))
    return out


def load(path=None):
    """{"stores": {key: row}, "restrict": [row]} from market/buying.md.
    ValueError when the stores table is missing, so a broken file is loud, not silent."""
    with open(path or os.path.join(DIR, "buying.md"), encoding="utf-8") as f:
        t = _tables(f.read())
    if not t.get("stores"):
        raise ValueError("buying.md: no Stores table")
    stores = {}
    for r in t["stores"]:
        m = DATE_RE.search(r.get("checked", ""))
        r["checked_date"] = datetime.date.fromisoformat(m.group(0)) if m else None
        stores[r["store"]] = r
    return {"stores": stores, "restrict": t.get("forwarder restrictions", [])}


def rule_for(data, forwarder, item, mode):
    """The restrictions row for forwarder × item × mode, or None when the table has none."""
    for r in data.get("restrict", []):
        modes = [m.strip() for m in r.get("modes", "").split(",")]
        if r.get("forwarder") == forwarder and r.get("item") == item and ("all" in modes or mode in modes):
            return r
    return None


def _amd(x):
    return f"{x:,.0f}"


def _when(line):
    rt = workdays.range_text(line.get("days"))
    dt = workdays.date_text(line.get("arrival"))
    return f"arrives {dt} · {rt}" if dt else rt


def route_steps(quote):
    """The cheapest route, and the fastest one when it differs, with the difference in AMD."""
    lines = (quote or {}).get("lines") or []
    cheap = mpricing.cheapest(lines)
    if not cheap:
        return ["Shipping cannot be priced yet (no price or no weight) — see the routes above."]
    out = ["In your forwarder account choose {} — the cheapest, {} AMD delivered, {}.".format(
        mpricing.label(cheap), _amd(cheap["total_amd"]), _when(cheap))]
    fast = mpricing.fastest(lines)
    if fast and fast is not cheap and fast["arrival"]["latest"] < (cheap.get("arrival") or {}).get(
            "latest", datetime.date.max):
        out.append("Faster: {}, +{} AMD, {}.".format(
            mpricing.label(fast), _amd(fast["total_amd"] - cheap["total_amd"]), _when(fast)))
    return out


def customs_step(quote):
    cheap = mpricing.cheapest((quote or {}).get("lines") or [])
    if not cheap or cheap.get("customs_amd") is None:
        return None
    if cheap["customs_amd"] == 0:
        s = "Customs: none (under €200 and 31 kg)."
    else:
        s = "Customs: about {} AMD — over the €200 limit; already in the total.".format(_amd(cheap["customs_amd"]))
    if cheap.get("customs_near"):
        s += " ⚠️ Within 10% of €200: a second item in the same parcel would cross it."
    return s


def restriction_steps(data, quote, flags):
    """One line per flag for the cheapest route's forwarder, from the restrictions table."""
    cheap = mpricing.cheapest((quote or {}).get("lines") or [])
    if not cheap or not flags:
        return []
    fw, mode = cheap["forwarder"], cheap["mode"]
    name = mpricing.label(cheap).rsplit(" ", 1)[0]
    out = []
    for f in flags:
        r = rule_for(data, fw, f, mode)
        word = ITEM_WORD.get(f, f)
        if not r or r.get("rule") == "unknown":
            out.append(f"⚠️ {word.capitalize()}: {name} publishes no rule — check with {name} before ordering.")
        elif r["rule"] == "refused":
            out.append("⚠️ {}: {} does not take it ({}). Pick another forwarder.".format(
                word.capitalize(), name, r.get("note", "")))
        else:
            out.append("⚠️ {}: {} takes it only if — {}.".format(word.capitalize(), name, r.get("note", "")))
    return out


def how_to(data, store_key, quote, price_text, delivery_text, flags=(), extra=(), today=None,
           store_rows=None):
    """The numbered-in-order steps for one result; [] when the store has no row."""
    row = (data or {}).get("stores", {}).get(store_key)
    if not row:
        return []
    srow = (store_rows or {}).get(store_key) or {}
    country = COUNTRY.get(row.get("warehouse", ""), row.get("warehouse", "").capitalize())
    post = " ({})".format(srow["postcode"]) if srow.get("postcode") else ""
    steps = ["{} — {}.".format(row["pay"], price_text) if price_text else "{}.".format(row["pay"]),
             "Deliver to your forwarder's {} warehouse{} — the full address and your code are in "
             "your forwarder account. {}".format(country, post, delivery_text.rstrip(".") + ".")]
    steps.extend(route_steps(quote))
    c = customs_step(quote)
    if c:
        steps.append(c)
    if row.get("watch"):
        steps.append("Check: {}.".format(row["watch"].rstrip(".")))
    steps.extend(x for x in extra if x)
    steps.extend(restriction_steps(data, quote, list(flags)))
    if today and row.get("checked_date") and (today - row["checked_date"]).days > STALE_DAYS:
        steps.append("⚠️ Buying steps last checked on {}.".format(row["checked_date"].isoformat()))
    return steps


def attach(offers, step_fn, today, log=None):
    """Sets offer["how"] on every offer: step_fn(data, store_rows, offer, today) -> steps.
    A missing or broken buying.md never fails a search: each result says so in one line (shown to
    the person, CLAUDE.md §5) and the log gets the reason."""
    try:
        data, rows = load(), stores_mod.load()
    except (OSError, ValueError) as e:
        if log:
            log(f"buying.md not used: {e}")
        for o in offers:
            o["how"] = ["How to buy is unavailable: market/buying.md could not be read."]
        return offers
    for o in offers:
        o["how"] = step_fn(data, rows, o, today)
    return offers
