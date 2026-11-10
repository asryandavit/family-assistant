"""Trust score for one Amazon offer - all in code (CLAUDE.md §2), from what the pages showed,
with the weights in config_amazon.json "trust" (brief §1.1), not constants here.

    seller        sold by Amazon > third party dispatched by Amazon > third party ships itself;
                  seller not read (product page not opened) = 0
    rating        only with at least min_reviews_for_rating reviews: a 5.0 from 2 reviews is not a
                  5.0 (the line says so); points = (rating - neutral) x per_star, clamped
    reviews       per_log10 x log10(count), capped
    bought        "N+ bought in past month" is sales evidence: per_log10 x log10(N), capped
    badges        Amazon's Choice, Best Seller: small facts, not guarantees
    sponsored     marked, small penalty, never wins a tie (pricing.best_pick skips it when an
                  organic result is priced)

Prime is displayed nowhere and ranks nothing: it does not apply to a warehouse parcel.
Every part is a (label, points) pair - the reason text printed next to the result is made from them.
"""
import math

from amazon import parse

SELLER_LABEL = {
    parse.AMAZON: "sold by Amazon",
    parse.DISPATCHED: "dispatched by Amazon",
    parse.THIRD: "third-party seller, ships itself",
    parse.UNREAD: "seller not read",
}


def _n(v):
    return "{:,}".format(v)


def score(o, tc):
    """(points, parts). tc is config_amazon.json "trust"."""
    parts = []
    cls = (o.get("seller") or {}).get("class", parse.UNREAD)
    parts.append((SELLER_LABEL[cls], float(tc["seller"].get(cls, 0))))
    n, r = o.get("reviews"), o.get("rating")
    if r is not None and (n or 0) >= tc["min_reviews_for_rating"]:
        rc = tc["rating"]
        pts = max(rc["min"], min(rc["max"], (r - rc["neutral"]) * rc["per_star"]))
        parts.append(("%g stars from %s reviews" % (r, _n(n)), round(pts, 1)))
    elif r is not None:
        parts.append(("%g stars but only %s review%s - not counted" % (r, _n(n or 0), "" if n == 1 else "s"), 0.0))
    elif n is None:
        parts.append(("no reviews shown", 0.0))
    if n and n >= tc["reviews"]["min_count"]:
        rv = tc["reviews"]
        parts.append(("%s reviews" % _n(n), round(min(rv["max"], rv["per_log10"] * math.log10(n)), 1)))
    s = o.get("sales")
    if s and s >= tc["bought"]["min_count"]:
        b = tc["bought"]
        parts.append(("%s bought in the past month" % (o.get("sales_text") or "").split(" bought")[0],
                      round(min(b["max"], b["per_log10"] * math.log10(s)), 1)))
    for key, pts in tc["badges"].items():
        if key in (o.get("badges") or []):
            parts.append(({"amazons_choice": "Amazon's Choice", "best_seller": "Best Seller"}.get(key, key),
                          float(pts)))
    if o.get("sponsored"):
        parts.append(("sponsored result", float(tc["sponsored"])))
    return round(sum(v for _, v in parts), 1), parts


def reason(o):
    """Words for the 🏆 line / the result's detail: positives first, then the caveats."""
    good = [lbl for lbl, v in o["trust_parts"] if v > 0]
    flat = [lbl for lbl, v in o["trust_parts"] if v == 0 and ("not counted" in lbl or "not read" in lbl
                                                                or "no reviews" in lbl)]
    bad = [lbl for lbl, v in o["trust_parts"] if v < 0]
    s = ", ".join(good) if good else "no trust signals shown"
    if flat or bad:
        s += "; but " + ", ".join(flat + bad)
    return s
