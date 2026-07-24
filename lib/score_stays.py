"""Rank stays by true cost, rating, location and verified constraints.

Everything here is deterministic and explainable: each listing carries a
`why` breakdown so a ranking can always be justified in the Telegram message.

True nightly cost normalizes the things that make sticker prices lie:
  + estimated transport when a place sits far from the centre
  + estimated breakfast for the family when it is not included
"""
import json
import math
import os

DEFAULTS = {
    "weights": {"price": 0.35, "rating": 0.20, "location": 0.25, "hard": 0.20},
    "min_rating": 7.5,
    "min_rating_airbnb": 9.0,   # Airbnb ratings skew high; 4.5/5 is only average
    "breakfast_per_person": 8.0,
    "transport_per_day": 6.0,
    "far_km": 2.5,
    "target_nightly": 90.0,
    "max_results": 6,
}


def cfg_get(cfg, key):
    return (cfg.get("stays") or {}).get(key, DEFAULTS[key])


def load_areas(cfg):
    path = os.path.join(cfg["_root"], "areas.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def haversine_km(a_lat, a_lng, b_lat, b_lng):
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _zone_hit(lat, lng, zone):
    """1.0 at the centre, decaying to 0 at twice the radius; bbox is binary."""
    c = zone.get("center")
    if c and lat and lng:
        d = haversine_km(lat, lng, c["lat"], c["lng"]) * 1000
        rad = zone.get("radius_m", 800)
        if d <= rad:
            return 1.0
        if d <= rad * 2:
            return 1.0 - (d - rad) / rad
        return 0.0
    bb = zone.get("bbox")
    if bb and lat and lng:
        if bb["s"] <= lat <= bb["n"] and bb["w"] <= lng <= bb["e"]:
            return 1.0
    return 0.0


def _name_hit(text, zone):
    t = (text or "").lower()
    return any(m in t for m in (zone.get("match") or []))


def location_score(r, area, flags):
    """-1..+1 plus a human-readable reason."""
    if not area:
        return (0.3 if r.get("best_area") else 0.0), "no zone data"

    lat, lng = r.get("lat"), r.get("lng")
    text = " ".join(str(r.get(k) or "") for k in ("name", "subtitle", "desc"))
    best, reason = 0.0, ""

    for z in area.get("prefer", []):
        hit = _zone_hit(lat, lng, z) or (0.6 if _name_hit(text, z) else 0.0)
        val = hit * z.get("weight", 1.0)
        if val > best:
            best, reason = val, "in %s" % z["name"]

    penalty, pen_reason = 0.0, ""
    for z in area.get("avoid", []):
        hit = _zone_hit(lat, lng, z) or (0.6 if _name_hit(text, z) else 0.0)
        val = hit * abs(z.get("weight", 1.0))
        if val > penalty:
            penalty, pen_reason = val, "near %s" % z["name"]

    score = best - penalty
    if not reason and not pen_reason:
        c = area.get("center")
        if c and lat and lng:
            d = haversine_km(lat, lng, c["lat"], c["lng"])
            score = max(-0.5, 0.4 - d / 10.0)
            reason = "%.1f km from centre" % d
        else:
            reason = "location unknown"

    # sea preference: reward genuine beach proximity in coastal cities
    if "sea" in flags and area.get("sea_city"):
        bd = str(r.get("beach_distance") or "").lower()
        if "beachfront" in bd:
            score += 0.5
            reason += " + beachfront"
        elif "m from beach" in bd:
            metres = "".join(ch for ch in bd if ch.isdigit())
            if metres and int(metres) <= 600:
                score += 0.3
                reason += " + %sm to beach" % metres
        elif area.get("sea_points") and r.get("lat"):
            d = min(haversine_km(r["lat"], r["lng"], s["lat"], s["lng"])
                    for s in area["sea_points"])
            if d <= 0.6:
                score += 0.4
                reason += " + near sea"

    if r.get("best_area"):
        score += 0.15

    parts = [p for p in (reason, pen_reason) if p]
    return max(-1.0, min(1.2, score)), ", ".join(parts)


def true_nightly(r, cfg, nights, flags):
    """Nightly price adjusted so options compare like for like."""
    base = r.get("price_night")
    if base is None:
        return None, ""
    add, notes = 0.0, []

    if "breakfast" in flags and not r.get("breakfast"):
        per = cfg_get(cfg, "breakfast_per_person") * 3
        add += per
        notes.append("+%.0f breakfast" % per)

    dist_txt = str(r.get("center_distance") or "")
    km = None
    if "km" in dist_txt:
        digits = "".join(ch for ch in dist_txt if ch.isdigit() or ch == ".")
        try:
            km = float(digits.strip("."))
        except ValueError:
            km = None
    if km and km > cfg_get(cfg, "far_km"):
        t = cfg_get(cfg, "transport_per_day")
        add += t
        notes.append("+%.0f transport" % t)

    return round(base + add, 2), " ".join(notes)


def hard_score(r, flags):
    """Known-satisfied constraints minus known failures, in -1..+1."""
    got, checks, notes = 0.0, 0, []
    crib = str(r.get("crib") or "").lower()
    if crib:
        checks += 1
        if "not" in crib or "unavailable" in crib:
            got -= 1
            notes.append("no crib")
        else:
            got += 1
            notes.append("crib")
    text = " ".join(str(r.get(k) or "") for k in ("desc", "name", "subtitle")).lower()
    if "lift" in text or "elevator" in text:
        checks += 1
        got += 1
        notes.append("lift")
    if "pool" in flags and "pool" in text:
        got += 0.5
        notes.append("pool")
    if r.get("free_cancel"):
        got += 0.3
    return (max(-1.0, min(1.0, got / max(checks, 1))) if checks else 0.0), notes


def rank(rows, cfg, nights, flags, budget=None, city=None):
    areas = load_areas(cfg)
    area = areas.get((city or "").upper()) if city else None
    w = cfg_get(cfg, "weights")
    target = cfg_get(cfg, "target_nightly")
    strict = "strict" in flags

    out = []
    for r in rows:
        rating = r.get("rating")
        floor = (cfg_get(cfg, "min_rating_airbnb") if r["source"] == "airbnb"
                 else cfg_get(cfg, "min_rating"))
        if rating is None or rating < floor:
            continue
        tn, cost_note = true_nightly(r, cfg, nights, flags)
        if tn is None:
            continue
        if budget and tn > budget:
            continue
        if "apt" in flags and r["source"] == "booking" and r.get("type_id") not in (201, 220, 224):
            continue
        if "hotel" in flags and r["source"] == "airbnb":
            continue

        loc, loc_why = location_score(r, area, flags)
        if strict and loc < 0:
            continue
        hard, hard_notes = hard_score(r, flags)

        s_price = min(target / tn, 1.2) if tn else 0
        s_rating = max(0.0, min(1.0, (rating - 7.5) / 2.5))
        score = (w["price"] * s_price + w["rating"] * s_rating
                 + w["location"] * loc + w["hard"] * hard)

        d = dict(r)
        d.update({"true_nightly": tn, "score": round(score, 3),
                  "loc_score": round(loc, 2), "loc_why": loc_why,
                  "cost_note": cost_note, "hard_notes": hard_notes})
        out.append(d)

    out.sort(key=lambda x: -x["score"])
    return out
