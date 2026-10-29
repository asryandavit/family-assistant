"""One offer -> one quote per forwarder × mode (docs/briefs/MARKET_WATCH.md §4).

    total_AMD = qty × price × rate + in-store shipping × rate + shipping + customs estimate

Everything here is arithmetic on numbers that were read or typed; nothing is guessed:
    no weight     -> the line shows the forwarder's AMD/kg and "weight needed", no total
    no rate       -> no AMD figures for that currency ("rate unavailable")
    store delivery unknown -> totals exclude it and say so
One item (× qty) = one parcel. The size is used only for qty 1 (several boxes have no
single L×W×H).
"""
from market import customs as customs_mod
from market import rates as rates_mod
from market import shipping, tariffs, workdays

DIRECT_CUSTOMS = dict(tariffs.CUSTOMS_ONEX)


def routes_for(store, routes):
    """The tariff routes a store may use: its origin × its forwarder modes."""
    modes = [m for m in store["modes"] if m in ("air", "sea", "truck")]
    return [r for r in routes if r["origin"] == store["origin"] and r["mode"] in modes]


def _arrival(today, days, delivery, wait_days=None):
    """Arrival range using the store's delivery (earliest, latest) when the page gave one."""
    if not days:
        return None
    if delivery:
        lo = workdays.arrival(today, days, store_arrival=delivery[0], wait_days=wait_days)
        hi = workdays.arrival(today, days, store_arrival=delivery[1], wait_days=wait_days)
        return {"earliest": lo["earliest"], "latest": hi["latest"], "notes": hi["notes"]}
    return workdays.arrival(today, days, wait_days=wait_days)


def quote(item, store, offer, routes, rates, today, which="default"):
    qty = int(item.get("qty") or 1)
    weight = item.get("weight_kg")
    kg = round(weight * qty, 3) if weight else None
    dims = tuple(item["size_cm"]) if item.get("size_cm") and qty == 1 else None
    cur = offer.get("currency") or store["currency"]
    notes = []

    price_amd = rates_mod.to_amd(offer["price"] * qty, cur, rates) if offer.get("price") is not None else None
    ship = offer.get("shipping")
    ship_amd = rates_mod.to_amd(ship, cur, rates) if ship is not None else None
    if ship is None and store["modes"] != ["local"]:
        notes.append("store delivery %s" % (offer.get("shipping_note") or "unknown"))
    if price_amd is None and offer.get("price") is not None:
        notes.append("%s rate unavailable" % cur)
    base_amd = None if price_amd is None else price_amd + (ship_amd or 0.0)
    eur = rates_mod.to_amd(1, "EUR", rates)
    value_eur = base_amd / eur if base_amd is not None and eur else None
    delivery = offer.get("delivery")

    lines = []
    if "local" in store["modes"]:
        lines.append({"forwarder": "", "mode": "local", "per_kg": None, "chargeable_kg": None,
                      "ship_amd": 0.0, "customs_amd": 0.0, "customs_near": False,
                      "total_amd": base_amd, "days": None, "arrival": None})
    if "direct" in store["modes"]:
        c = customs_mod.estimate(value_eur, kg, DIRECT_CUSTOMS, which) if value_eur is not None else None
        c_amd = c["eur"] * eur if c else None
        lines.append({"forwarder": "store", "mode": "direct", "per_kg": None, "chargeable_kg": kg,
                      "ship_amd": 0.0, "customs_amd": c_amd, "customs_near": bool(c and c["near_limit"]),
                      "total_amd": None if base_amd is None or c_amd is None else base_amd + c_amd,
                      "days": None, "arrival": None})
    for r in routes_for(store, routes):
        q = shipping.quote(r, kg, dims) if kg else None
        c = customs_mod.estimate(value_eur, kg, r.get("customs"), which) \
            if value_eur is not None else None
        c_amd = c["eur"] * eur if c else None
        total = None
        if q and base_amd is not None and c_amd is not None:
            total = base_amd + q["cost_amd"] + c_amd
        lines.append({"forwarder": r["forwarder"], "mode": r["mode"], "per_kg": shipping.per_kg(r),
                      "chargeable_kg": q["chargeable_kg"] if q else None,
                      "by_volume": bool(q and q["by_volume"]),
                      "ship_amd": q["cost_amd"] if q else None, "customs_amd": c_amd,
                      "customs_near": bool(c and c["near_limit"]), "total_amd": total,
                      "days": r.get("days"), "arrival": _arrival(today, r.get("days"), delivery)})
    if not kg and any(ln["forwarder"] not in ("", "store") for ln in lines):
        notes.append("weight needed")
    return {"store": store["key"], "price_amd": price_amd, "store_ship_amd": ship_amd,
            "base_amd": base_amd, "value_eur": value_eur, "lines": lines, "notes": notes}


def cheapest(lines):
    priced = [ln for ln in lines if ln.get("total_amd") is not None]
    return min(priced, key=lambda ln: ln["total_amd"]) if priced else None


def fastest(lines):
    dated = [ln for ln in lines if ln.get("arrival") and ln.get("total_amd") is not None]
    return min(dated, key=lambda ln: (ln["arrival"]["latest"], ln["total_amd"])) if dated else None


def label(line):
    if line["mode"] == "local":
        return "in Yerevan"
    if line["mode"] == "direct":
        return "store delivery"
    return "%s %s" % (line["forwarder"].capitalize().replace("Buyforyou", "BuyForYou")
                      .replace("Easytrans", "EasyTrans"), line["mode"])


def best_of(quotes):
    """(best line, its store key, reason) over all an item's quotes, or (None, None, '')."""
    pool = [(ln, q["store"]) for q in quotes for ln in q["lines"] if ln.get("total_amd") is not None]
    if not pool:
        return None, None, ""
    ln, store = min(pool, key=lambda x: x[0]["total_amd"])
    reason = "cheapest of %d priced route%s" % (len(pool), "" if len(pool) == 1 else "s")
    return ln, store, reason
