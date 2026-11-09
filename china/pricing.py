"""Validated results -> money, all in code (CLAUDE.md §2), reusing market.pricing.quote.

Per result:
    price         the matched variant's shown price (¥, or $ on 1688's international pages)
    delivery      China domestic delivery: free ("包邮"), an amount, or unknown (never free
                  by default; 1688 quotes delivery to the account's Yerevan address, P0,
                  so only "free" is taken from it)
    weight        from the page; none -> config assumed_kg (1 kg) and weight_assumed=True
    routes        config routes only (forwarder x mode), each with shipping, customs, total
Ranking (owner, 2026-11-09: "the price is not so important — find the best and trustworthy
product"): by the trust score (china/trust.py: seller, guarantees, store age, certificates,
sales, reviews, rating, complaint kinds, spec mismatch), then by delivered price only among
results in the same score band; unpriced last. Promo prices (new-buyer, first-item, 'from',
ranges — parse.promo) are shown with their reason but never picked; a listing priced below
suspicious_ratio of the search's median item price is marked suspicious (−100) and never
picked. The 🏆 pick is the top of that order across sites; its reason lists the trust parts.
"""
import math
import re

from china import parse, trust
from market import customs as customs_mod
from market import pricing as mpricing
from market import rates as rates_mod

FREE_WORDS = ("包邮", "免运费", "免邮", "free shipping", "free delivery", "运费0", "运费¥0")


def delivery_cny(text, site):
    """(amount or None, note)."""
    if not text:
        return None, "China delivery not shown"
    t = text.lower().replace(" ", "")
    if any(w.replace(" ", "") in t for w in FREE_WORDS):
        return 0.0, "free China delivery"
    if site == "1688":
        return None, "China delivery to the warehouse not shown"
    m = re.search(r"运费[^\d¥￥]*[¥￥]?\s*(\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1)), "China delivery ¥%s" % m.group(1)
    return None, "China delivery unknown"


DIMS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)", re.I)


def weight_and_dims(r, assumed_kg):
    kg = parse.weight_kg(r.get("weight_text"))
    note = ""
    dims = None
    if r.get("dims_text"):
        m = DIMS_RE.search(r["dims_text"])
        if m:
            dims, note = parse.dims_cm(*m.groups(), weight_g=kg * 1000 if kg else None)
    if kg is None:
        return assumed_kg, dims, True, note
    return kg, dims, False, note


def store_row(site):
    return {"key": site, "name": site, "origin": "china", "currency": "CNY",
            "modes": ["air", "sea", "truck"]}


def price_result(r, routes, rates, today, cfg):
    """One validated result -> priced dict (the input fields plus the money)."""
    amount, cur = parse.money(r.get("price_text"))
    single, _ = parse.money(r.get("single_price_text"))
    dlv, dlv_note = delivery_cny(r.get("domestic_delivery_text"), r["site"])
    kg, dims, assumed, dims_note = weight_and_dims(r, cfg.get("assumed_kg", 1.0))
    allowed = {tuple(x) for x in cfg["routes"]}
    use = [x for x in routes if x["origin"] == "china" and (x["forwarder"], x["mode"]) in allowed]
    offer = {"price": amount, "currency": cur or "CNY", "shipping": dlv,
             "shipping_note": dlv_note if dlv is None else None, "delivery": None}
    item = {"qty": 1, "weight_kg": kg, "size_cm": list(dims) if dims else None}
    q = mpricing.quote(item, store_row(r["site"]), offer, use, rates, today) \
        if amount is not None else None
    usd_rate = rates_mod.to_amd(1, "USD", rates)
    cls, evidence = parse.seller_class(r.get("shop_name"), r.get("marks"), r.get("badges"))
    best = mpricing.cheapest(q["lines"]) if q else None
    flags = sorted(set(r.get("restrict") or []) |
                   set(parse.restrictions(r.get("title_cn"), r.get("title_en"))))
    out = dict(r)
    out.update({
        "price": amount, "currency": cur, "price_amd": q["price_amd"] if q else None,
        "price_usd": (q["price_amd"] / usd_rate) if q and q["price_amd"] is not None and usd_rate else None,
        "single_price": single,
        "delivery_cny": dlv, "delivery_note": dlv_note,
        "kg": kg, "weight_assumed": assumed, "dims": dims, "dims_note": dims_note,
        "quote": q, "best": best,
        "total_amd": best["total_amd"] if best else None,
        "total_usd": (best["total_amd"] / usd_rate) if best and usd_rate else None,
        "value_eur": q["value_eur"] if q else None,
        "promo": parse.promo(r.get("price_text")) or ("first-item price" if r.get("price_kind") == "first_item" else ""),
        "seller": cls, "seller_evidence": evidence,
        "sales": parse.count(r.get("sales_text")), "reviews": parse.count(r.get("review_count_text")),
        "flags": flags, "link": parse.link(r["site"], r["id"]),
    })
    return out


def apply_trust(priced, category="other"):
    """Sets p["trust"] and p["trust_parts"] (china/trust.py) on every result."""
    for p in priced:
        p["trust"], p["trust_parts"] = trust.score(p, category)
    return priced


def order_key(p):
    """Trust band first (higher better), then delivered total (lower better)."""
    return (-math.floor(p.get("trust", 0) / trust.BAND), p["total_amd"])


def rank(priced, top_n):
    """Most trusted first, cheaper first within a trust band; unpriced at the end (most
    trusted first)."""
    have = sorted([p for p in priced if p["total_amd"] is not None], key=order_key)
    rest = sorted([p for p in priced if p["total_amd"] is None], key=lambda p: -p.get("trust", 0))
    return (have + rest)[:top_n]


def mark_suspicious(priced, ratio):
    """Sets p["suspicious"] on listings whose item price (AMD) is below ratio x the median item
    price of all priced listings. Promo prices (new-buyer, first-item, 'from') are not normal
    prices and stay out of the median. Needs at least 3 prices for a meaningful median."""
    prices = sorted(p["price_amd"] for p in priced
                    if p.get("price_amd") is not None and not p.get("promo"))
    for p in priced:
        p["suspicious"] = False
    if len(prices) < 3 or not ratio:
        return priced
    n = len(prices)
    median = prices[n // 2] if n % 2 else (prices[n // 2 - 1] + prices[n // 2]) / 2.0
    for p in priced:
        if p.get("price_amd") is not None and p["price_amd"] < median * ratio:
            p["suspicious"] = True
    return priced


def best_pick(priced):
    """(result, reason) or (None, ''): the top of the trust order, never a promo or
    suspiciously cheap price."""
    have = [p for p in priced if p["total_amd"] is not None and not p.get("promo")
            and not p.get("suspicious")]
    if not have:
        return None, ""
    best = min(have, key=order_key)
    why = trust.reason(best)
    peers = [p for p in have if p is not best and order_key(p)[0] == order_key(best)[0]]
    if peers:
        why += "; the cheapest of %d equally trusted" % (len(peers) + 1)
    return best, why


WORD_RE = re.compile(r"[a-z]+|\d+w", re.I)
STOP = {"for", "with", "and", "the", "fast", "charger", "charging", "gan", "pd", "type", "c",
        "phone", "usb", "port", "ports", "compatible", "apple", "iphone", "huawei", "plug"}


def _tokens(p):
    return {w.lower() for w in WORD_RE.findall(p.get("title_en") or "")} - STOP


def same_product(priced, min_overlap=0.5):
    """Groups of the same product on different sites: titles sharing ≥ min_overlap of their
    distinctive words (brand, wattage, model words). Only groups spanning ≥ 2 sites."""
    groups, used = [], set()
    for i, a in enumerate(priced):
        if i in used:
            continue
        ta, grp = _tokens(a), [a]
        for j in range(i + 1, len(priced)):
            b = priced[j]
            if j in used or b["site"] == a["site"]:
                continue
            tb = _tokens(b)
            if ta and tb and len(ta & tb) / min(len(ta), len(tb)) >= min_overlap:
                grp.append(b)
                used.add(j)
        if len({g["site"] for g in grp}) >= 2:
            groups.append(grp)
    return groups


def parcel_customs(priced_items, route, rates, which="default"):
    """Customs for several items in ONE parcel via one route: value and weight summed.
    {"value_eur", "kg", "eur", "amd", "near_limit"} or None when a value is missing."""
    eur = rates_mod.to_amd(1, "EUR", rates)
    vals = [p.get("value_eur") for p in priced_items]
    if not eur or any(v is None for v in vals):
        return None
    value = sum(vals)
    kg = sum(p.get("kg") or 0 for p in priced_items)
    c = customs_mod.estimate(value, kg, route.get("customs"), which)
    return {"value_eur": value, "kg": kg, "eur": c["eur"], "amd": c["eur"] * eur,
            "near_limit": c["near_limit"]}
