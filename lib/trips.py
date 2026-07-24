"""Assemble complete trips from one-way legs: round trips and open-jaw.

Deterministic. Seat math per leg: 2 adult seats always; from the flip date
(toddler's 2nd birthday) a third seat is priced on any leg on/after it.
Lap-infant fee is NOT included unless set in config (it varies by route).
Open-jaw totals exclude ground transport between the two cities.
"""
import hashlib
from datetime import date


def _dt(s):
    return date.fromisoformat(s)


def _seats(leg_date, flip):
    return 3 if leg_date >= flip else 2


def assemble(fares, cfg):
    t = cfg.get("trips", {})
    min_n, max_n = t.get("min_nights", 4), t.get("max_nights", 10)
    infant_fee = float(t.get("infant_fee_per_leg", 0) or 0)
    origin = cfg["wizz"].get("origin_code", "EVN")
    flip = date.fromisoformat(cfg["passengers"]["flip_date"])

    gmap = {}
    for g in t.get("nearby_groups", []):
        fs = frozenset(g)
        for c in g:
            gmap[c] = fs

    usd = [f for f in fares if f.get("currency") == "USD"]
    outs = [f for f in usd if f["origin"] == origin and f["out_date"]]
    ins = [f for f in usd if f["destination"] == origin and f["out_date"]]

    trips = []
    for o in outs:
        for i in ins:
            a, b = o["destination"], i["origin"]
            same = a == b
            near = (not same and a in gmap and b in gmap
                    and gmap[a] == gmap[b])
            if not (same or near):
                continue
            d1, d2 = _dt(o["out_date"]), _dt(i["out_date"])
            nights = (d2 - d1).days
            if nights < min_n or nights > max_n:
                continue

            s1, s2 = _seats(d1, flip), _seats(d2, flip)
            total = round(o["regular"] * s1 + i["regular"] * s2 + 2 * infant_fee, 2)
            wdc = ""
            if isinstance(o.get("wdc"), (int, float)) and isinstance(i.get("wdc"), (int, float)):
                wdc = round(o["wdc"] * s1 + i["wdc"] * s2 + 2 * infant_fee, 2)

            pax = "2A" if (s1, s2) == (2, 2) else ("2A+1C" if (s1, s2) == (3, 3) else "2A/+1C")
            tid = "T" + hashlib.md5(
                f"{a}|{o['out_date']}|{b}|{i['out_date']}".encode()
            ).hexdigest()[:6].upper()

            trips.append({
                "id": tid,
                "kind": "return" if same else "openjaw",
                "route": a if same else f"{a}>{b}",
                "out_city": a, "in_city": b,
                "out_date": o["out_date"], "back_date": i["out_date"],
                "nights": nights, "pax": pax,
                "total": total, "wdc": wdc,
                "currency": o.get("currency", "USD"),
            })

    trips.sort(key=lambda x: x["total"])
    return trips[: t.get("max_results", 10)]


def to_sheet_rows(trips, run_date):
    return [[run_date, tr["id"], tr["kind"], tr["route"], tr["out_date"],
             tr["back_date"], tr["nights"], tr["pax"], tr["total"],
             tr["wdc"] if tr["wdc"] != "" else "-", tr["currency"]]
            for tr in trips]


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def analyze(trip_rows, trips_today, today, alerts_cfg):
    """trip_rows: Trips tab values without header.
    Returns (notable_new, notable_drops)."""
    cheap = alerts_cfg.get("trip_total_alert", 100)
    drop_abs = alerts_cfg.get("trip_drop_abs", 10)

    hist = {}
    for r in trip_rows:
        if len(r) < 9 or not r[0] or r[0] >= today:
            continue
        tid, total = r[1], _f(r[8])
        if tid and total is not None:
            hist.setdefault(tid, []).append((r[0], total))

    new, drops = [], []
    for tr in trips_today:
        prior = hist.get(tr["id"])
        if not prior:
            if tr["total"] <= cheap:
                new.append(tr)
            continue
        last_total = max(prior)[1]
        delta = round(tr["total"] - last_total, 2)
        if delta <= -drop_abs:
            d = dict(tr)
            d["prev_total"] = last_total
            d["delta"] = delta
            drops.append(d)
    return new, drops
