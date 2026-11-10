"""Offers -> money, all in code (CLAUDE.md §2), reusing market.pricing.quote.

Per offer: item price (store currency), Amazon's delivery to the forwarder warehouse (from the
page: a fee, free, or unknown - never assumed), weight from the product page (none -> config
assumed_kg and the same uppercase warning as /china), then one quote line per forwarder x mode of
the store (market/stores.md modes x market/tariffs.json): shipping, customs, total in AMD and the
arrival range.

Ranking: by trust band (amazon/trust.py), then delivered total; unpriced last; a sponsored result
never beats an organic one at the same total and is never the 🏆 pick while an organic one is
priced. Every pick carries a human-readable reason (trust parts).
"""
import json
import math
import os

from amazon import trust
from market import pricing as mpricing
from market import rates as rates_mod
from market import stores as stores_mod


def load_routes(root):
    """(routes, tariffs date) from market/tariffs.json. # same as china/search.load_routes"""
    with open(os.path.join(root, "market", "tariffs.json"), encoding="utf-8") as f:
        t = json.load(f)
    return t["routes"], (t.get("refreshed_utc") or "")[:10]


def store_row(site, rows=None):
    """The market/stores.md row of Amazon <site>; ValueError if the table lost it."""
    rows = rows or stores_mod.load()
    row = rows.get("amazon_" + site)
    if not row:
        raise ValueError("market/stores.md has no row amazon_%s" % site)
    return row


def price_offer(o, store, routes, rates, today, tc, assumed_kg=1.0):
    """One offer -> priced copy (the offer's fields plus money and trust)."""
    kg = o.get("weight_kg")
    assumed = not kg
    kg = kg or assumed_kg
    dims = o.get("dims_cm")
    q = None
    if o.get("price") is not None:
        offer = {"price": o["price"], "currency": o["currency"], "shipping": o.get("delivery_fee"),
                 "shipping_note": o.get("delivery_note") or "unknown",
                 "delivery": o.get("delivery_eta")}
        item = {"qty": 1, "weight_kg": kg, "size_cm": list(dims) if dims else None}
        q = mpricing.quote(item, store, offer, routes, rates, today)
    usd = rates_mod.to_amd(1, "USD", rates)
    best = mpricing.cheapest(q["lines"]) if q else None
    out = dict(o)
    out.update({
        "kg": kg, "weight_assumed": assumed, "quote": q, "best": best,
        "price_amd": q["price_amd"] if q else None,
        "price_usd": (q["price_amd"] / usd) if q and q["price_amd"] is not None and usd else None,
        "total_amd": best["total_amd"] if best else None,
        "total_usd": (best["total_amd"] / usd) if best and usd else None,
    })
    out["trust"], out["trust_parts"] = trust.score(out, tc)
    return out


def order_key(p, band):
    """Trust band first (higher better), then delivered total (lower better), sponsored last."""
    return (-math.floor(p.get("trust", 0) / band), p["total_amd"], 1 if p.get("sponsored") else 0)


def rank(priced, top_n, band):
    have = sorted([p for p in priced if p["total_amd"] is not None], key=lambda p: order_key(p, band))
    rest = sorted([p for p in priced if p["total_amd"] is None], key=lambda p: -p.get("trust", 0))
    return (have + rest)[:top_n]


def best_pick(priced, band):
    """(offer, reason) or (None, ''): the top of the order, organic first; reason from the
    trust parts plus how the choice was made."""
    have = [p for p in priced if p["total_amd"] is not None]
    organic = [p for p in have if not p.get("sponsored")]
    pool = organic or have
    if not pool:
        return None, ""
    best = min(pool, key=lambda p: order_key(p, band))
    why = trust.reason(best)
    peers = [p for p in pool if p is not best and order_key(p, band)[0] == order_key(best, band)[0]]
    if peers:
        why += "; the cheapest of %d equally trusted" % (len(peers) + 1)
    if organic and len(organic) < len(have) and best.get("sponsored"):
        why += " (sponsored)"
    return best, why
