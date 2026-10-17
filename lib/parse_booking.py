"""Parse Wizz farechart payloads into price-by-date rows.

Shape observed on the booking page:
  {"outboundFlights": [ {"departureStation": "EVN", "arrivalStation": "LCA",
                         "price": {"amount": 84.99, "currencyCode": "USD"},
                         "priceType": "price", "date": "2026-09-09T00:00:00",
                         "classOfService": "K"}, ... ],
   "returnFlights":   [ ... same shape, opposite direction ... ]}

Wizz quotes in the departure country's currency -- EVN pages in USD, Naples in
EUR -- so every amount is normalised to USD here and the original kept in `src`.
Entries with no bookable price (priceType marks them) are dropped rather than
stored as zero.
"""
from lib import fx

BLANK = "-"


def _rows(entries, src_req):
    out = []
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        price = (e.get("price") or {})
        amt = price.get("amount")
        if not isinstance(amt, (int, float)) or amt <= 0:
            continue
        ptype = str(e.get("priceType") or "").lower()
        if ptype and ptype not in ("price", "checkprice"):
            continue  # e.g. soldout / notavailable
        cur = (price.get("currencyCode") or "USD").upper()
        usd = fx.to_usd(float(amt), cur)
        date = str(e.get("date") or "")[:10]
        if not date:
            continue
        out.append({
            "origin": e.get("departureStation") or "",
            "destination": e.get("arrivalStation") or "",
            "date": date,
            "price": round(usd, 2) if usd is not None else round(float(amt), 2),
            "currency": "USD" if usd is not None else cur,
            "src": BLANK if cur == "USD" else "%g %s" % (amt, cur),
            "class": e.get("classOfService") or BLANK,
            "req": src_req,
        })
    return out


def parse(payloads):
    """Returns the cheapest row per (origin, destination, date)."""
    best = {}
    for p in payloads or []:
        data = p.get("data") or {}
        req = "%s->%s" % (p.get("req", {}).get("from", "?"),
                          p.get("req", {}).get("to", "?"))
        for key in ("outboundFlights", "returnFlights"):
            for r in _rows(data.get(key), req):
                k = (r["origin"], r["destination"], r["date"])
                if k not in best or r["price"] < best[k]["price"]:
                    best[k] = r
    return sorted(best.values(), key=lambda r: (r["origin"], r["destination"], r["date"]))


def by_route(rows):
    """{(origin, destination): {date: row}} for fast pairing."""
    out = {}
    for r in rows:
        out.setdefault((r["origin"], r["destination"]), {})[r["date"]] = r
    return out
