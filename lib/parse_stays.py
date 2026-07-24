"""Parse Booking.com and Airbnb search results into one normalized shape.

Design note: the deep paths into these payloads change often, so instead of
hardcoding them this walks each result record looking for the FIELDS it needs
(price amounts, coordinates, review scores). A layout reshuffle usually leaves
field names intact, so this survives what path-based parsing would not.

Anything that fails to resolve is recorded in `_unresolved` and the raw record
is dumped to .browser/unresolved_<site>.json for diagnosis -- no silent nulls.

Offline use (works on saved discovery HTML, no network):
    python parse_stays.py
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, ".browser")

# Booking nests results under ROOT_QUERY > searchQueries > "search({...})" > results.
# Deep-searching for the array beats matching that giant generated key.


# ---------- generic helpers ----------

def blobs(html):
    for m in re.finditer(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
                         html, re.S):
        body = m.group(1)
        if len(body) > 2000:
            yield body


def unwrap(node, depth=0):
    """Airbnb nests JSON inside strings; parse those through."""
    if depth > 8:
        return node
    if isinstance(node, str):
        s = node.strip()
        if s.startswith(("{", "[")) and len(s) > 40:
            try:
                return unwrap(json.loads(s), depth + 1)
            except ValueError:
                return node
        return node
    if isinstance(node, dict):
        return {k: unwrap(v, depth + 1) for k, v in node.items()}
    if isinstance(node, list):
        return [unwrap(v, depth + 1) for v in node]
    return node


def find_key(node, names, depth=0, max_depth=12):
    """First value whose key is in `names`, breadth-ish first."""
    if depth > max_depth:
        return None
    if isinstance(node, dict):
        for n in names:
            if n in node and node[n] not in (None, "", []):
                return node[n]
        for v in node.values():
            r = find_key(v, names, depth + 1, max_depth)
            if r is not None:
                return r
    elif isinstance(node, list):
        for v in node[:12]:
            r = find_key(v, names, depth + 1, max_depth)
            if r is not None:
                return r
    return None


def _to_num(v, depth=0):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict) and depth < 3:
        for k in ("score", "value", "amountUnformatted", "amount"):
            r = _to_num(v.get(k), depth + 1)
            if r is not None:
                return r
    return None


def find_num(node, names):
    v = find_key(node, names)
    n = _to_num(v)
    if n is not None:
        return n
    if isinstance(v, str):
        m = re.search(r"[\d][\d,.\s]*", v.replace("\u00a0", " "))
        if m:
            try:
                return float(m.group(0).replace(",", "").replace(" ", ""))
            except ValueError:
                return None
    return None


def money_from_text(s):
    """'$1,234' / 'US$1 234 total' -> 1234.0"""
    if not isinstance(s, str):
        return None
    m = re.search(r"[\d][\d,.\u00a0 ]*", s)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "").replace("\u00a0", "").replace(" ", ""))
    except ValueError:
        return None


def currency_from_text(s):
    if not isinstance(s, str):
        return ""
    for sym, code in (("$", "USD"), ("\u20ac", "EUR"), ("\u00a3", "GBP")):
        if sym in s:
            return code
    m = re.search(r"\b([A-Z]{3})\b", s)
    return m.group(1) if m else ""


def norm(rec):
    rec.setdefault("_unresolved", [])
    for f in ("name", "price_total", "rating", "lat"):
        if rec.get(f) in (None, "", 0):
            rec["_unresolved"].append(f)
    return rec


# ---------- Booking ----------

def _dig_booking(node, depth=0):
    """Find the list of SearchResultProperty records, wherever it sits."""
    if depth > 14:
        return None
    if isinstance(node, dict):
        res = node.get("results")
        if isinstance(res, list):
            good = [x for x in res if isinstance(x, dict)
                    and x.get("__typename") == "SearchResultProperty"]
            if good:
                return good
        for v in node.values():
            r = _dig_booking(v, depth + 1)
            if r:
                return r
    elif isinstance(node, list):
        for v in node[:20]:
            r = _dig_booking(v, depth + 1)
            if r:
                return r
    return None


def parse_booking(html, nights=None):
    for body in blobs(html):
        try:
            data = json.loads(body)
        except ValueError:
            continue
        found = _dig_booking(data)
        if found:
            return [_booking_one(r, nights) for r in found]
    return []


def _booking_one(r, nights):
    bpd = r.get("basicPropertyData") or {}
    loc = r.get("location") or {}
    pdi = r.get("priceDisplayInfoIrene") or {}
    disp = (pdi.get("displayPrice") or {}).get("amountPerStay") or {}
    price = _to_num(disp.get("amountUnformatted"))
    cur = disp.get("currency") or ""
    if price is None:
        price = find_num(pdi, ["amountUnformatted", "amount", "value"])
        cur = find_key(pdi, ["currency", "currencyCode"]) or ""
    before = _to_num(((pdi.get("priceBeforeDiscount") or {}).get("amountPerStay") or {})
                     .get("amountUnformatted"))
    local = (pdi.get("displayPrice") or {}).get("amountPerStayHotelCurr") or {}
    price = round(price, 2) if price else price
    before = round(before, 2) if before else before
    # Confirmed shape: basicPropertyData.reviews.{totalScore, reviewsCount}
    rv = bpd.get("reviews") or find_key(r, ["reviews", "reviewScore"]) or {}
    if isinstance(rv, dict):
        rating = _to_num(rv.get("totalScore") or rv.get("score"))
        reviews = _to_num(rv.get("reviewsCount") or rv.get("reviewCount"))
        rating_word = ((rv.get("totalScoreTextTag") or {}).get("translation") or "")
    else:
        rating = _to_num(rv)
        reviews = find_num(r, ["reviewsCount", "reviewCount"])
        rating_word = ""
    coords = bpd.get("location") or {}
    lat = find_num(coords, ["latitude", "lat"])
    lng = find_num(coords, ["longitude", "lng", "lon"])
    slug = bpd.get("pageName") or ""
    meal = (r.get("mealPlanIncluded") or {}).get("mealPlanType") or ""
    pol = r.get("policies") or {}
    rec = {
        "source": "booking",
        "name": ((r.get("displayName") or {}).get("text") or "").strip(),
        "subtitle": (loc.get("displayLocation") or ""),
        "price_total": price,
        "price_before": before,
        "price_night": round(price / nights, 2) if price and nights else None,
        "currency": (cur or "").upper(),
        "price_local": ("%s %s" % (local.get("currency", ""),
                                   round(_to_num(local.get("amountUnformatted")) or 0))
                        ).strip() if local.get("currency") else "",
        "rating": rating / 10 if rating and rating > 10 else rating,
        "reviews": int(reviews) if reviews else None,
        "lat": lat, "lng": lng,
        "url": "https://www.booking.com/hotel/%s.html" % slug if slug else "",
        "type_id": bpd.get("accommodationTypeId"),
        "beach_distance": loc.get("beachDistance") or "",
        "center_distance": loc.get("mainDistance") or "",
        "transport": loc.get("publicTransportDistanceDescription") or "",
        "breakfast": "breakfast" in str(meal).lower(),
        "free_cancel": bool(pol.get("showFreeCancellation")),
        "genius": bool(r.get("geniusInfo")),
        "rating_word": rating_word,
        # Booking exposes these in search results -- crib in particular is a hard
        # constraint we would otherwise have to verify by reading listing pages.
        "crib": str(r.get("propertyCribsAvailabilityLabel") or ""),
        "stars": _to_num((bpd.get("starRating") or {}).get("value")),
        "best_area": bool((r.get("location") or {}).get("isWithinBestLocationScoreArea")),
        "desc": (str(r.get("descriptionSummary") or r.get("description") or "")[:600]),
        "units": _units(r),
    }
    return norm(rec)


def _units(r):
    """Bedroom/bed summary from the matching room configuration, if present."""
    cfg = find_key(r, ["matchingUnitConfigurations"]) or {}
    common = (cfg.get("commonConfiguration") or {}) if isinstance(cfg, dict) else {}
    bits = []
    for k, label in (("nbBedrooms", "bedroom"), ("nbBathrooms", "bath"),
                     ("nbAllBeds", "bed")):
        n = _to_num(common.get(k))
        if n:
            bits.append("%d %s%s" % (int(n), label, "s" if n > 1 else ""))
    name = common.get("name") or ""
    return ", ".join(bits) or str(name)[:60]


# ---------- Airbnb ----------

def parse_airbnb(html, nights=None):
    results = []
    for body in blobs(html):
        try:
            data = unwrap(json.loads(body))
        except ValueError:
            continue
        found = _dig_airbnb(data)
        if found:
            for r in found:
                results.append(_airbnb_one(r, nights))
            break
    return results


def _dig_airbnb(node, depth=0):
    if depth > 14:
        return None
    if isinstance(node, dict):
        if "searchResults" in node and isinstance(node["searchResults"], list):
            good = [x for x in node["searchResults"]
                    if isinstance(x, dict) and x.get("__typename") == "StaySearchResult"]
            if good:
                return good
        for v in node.values():
            r = _dig_airbnb(v, depth + 1)
            if r:
                return r
    elif isinstance(node, list):
        for v in node[:20]:
            r = _dig_airbnb(v, depth + 1)
            if r:
                return r
    return None


def _airbnb_one(r, nights):
    sdp = r.get("structuredDisplayPrice") or {}
    primary = sdp.get("primaryLine") or {}
    secondary = sdp.get("secondaryLine") or {}

    price_txt = primary.get("price") or primary.get("discountedPrice") or ""
    qualifier = str(primary.get("qualifier") or "")
    style = str(sdp.get("displayPriceStyle") or "")
    amount = money_from_text(price_txt)

    # "$591" + qualifier "for 7 nights" (or displayPriceStyle TOTAL_ONLY) is the
    # WHOLE STAY, not a nightly rate -- treating it as nightly inflates it 7x.
    m_nights = re.search(r"for\s+(\d+)\s+night", qualifier, re.I)
    is_total = bool(m_nights) or "TOTAL" in style.upper() or "total" in qualifier.lower()
    n = int(m_nights.group(1)) if m_nights else (nights or 0)

    total = per_night = None
    if amount is not None:
        if is_total:
            total = amount
            per_night = round(amount / n, 2) if n else None
        else:
            per_night = amount
            total = round(amount * n, 2) if n else None

    # The breakdown line "7 nights x $88.36" is the LIST rate before any weekly
    # discount, so it becomes price_before. The effective nightly (total / nights)
    # is what actually gets paid and what compares fairly against Booking.
    list_before = None
    for grp in (sdp.get("explanationData") or {}).get("priceDetails", []) or []:
        for it in (grp or {}).get("items", []) or []:
            d = str((it or {}).get("description") or "")
            mm = re.search(r"(\d+)\s*nights?\s*x\s*\D*([\d.,]+)", d, re.I)
            if mm:
                rate = money_from_text(mm.group(2))
                if rate:
                    list_before = round(rate * int(mm.group(1)), 2)
                break
        if list_before:
            break

    total_txt = price_txt

    rating, reviews = None, None
    m = re.match(r"([\d.]+)\s*\((\d+)\)", str(r.get("avgRatingLocalized") or ""))
    if m:
        rating, reviews = float(m.group(1)), int(m.group(2))

    dsl = r.get("demandStayListing") or {}
    coord = find_key(dsl, ["coordinate", "coordinates"]) or {}
    lat = find_num(coord, ["latitude", "lat"])
    lng = find_num(coord, ["longitude", "lng"])

    lid = dsl.get("id") or ""
    if isinstance(lid, str) and len(lid) > 12:  # base64 "StayListing:1234"
        import base64
        try:
            dec = base64.b64decode(lid + "==").decode("utf-8", "ignore")
            lid = dec.split(":")[-1]
        except Exception:
            pass

    badges = " ".join(str((b or {}).get("text", "")) for b in (r.get("badges") or []))
    rec = {
        "source": "airbnb",
        "name": (r.get("subtitle") or r.get("title") or "").strip(),
        "subtitle": (r.get("title") or "").strip(),
        "price_total": total,
        "price_before": list_before,
        "price_night": per_night,
        "currency": currency_from_text(price_txt) or "USD",
        # Airbnb rates are out of 5; scale to the 10-point scale used elsewhere
        "rating": round(rating * 2, 1) if rating else None,
        "reviews": reviews,
        "lat": lat, "lng": lng,
        "url": "https://www.airbnb.com/rooms/%s" % lid if lid else "",
        "type_id": None,
        "beach_distance": "",
        "center_distance": str((r.get("structuredContent") or {}).get("distance") or ""),
        "transport": "",
        "breakfast": False,
        "free_cancel": "free cancellation" in badges.lower(),
        "genius": False,
        "rating_word": badges.strip(),
        "crib": "",
        "stars": None,
        "best_area": False,
        "desc": str((r.get("structuredContent") or {}).get("primaryLine") or "")[:600],
        "units": str(r.get("title") or ""),
    }
    return norm(rec)


# ---------- offline runner ----------

def _dump_unresolved(site, raw_records):
    if not raw_records:
        return
    path = os.path.join(OUT, "unresolved_%s.json" % site)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw_records[:2], f, ensure_ascii=False, indent=2)
    print("  -> raw sample written to %s" % path)


def _run(site, nights=7):
    path = os.path.join(OUT, "stays_%s.html" % site)
    if not os.path.exists(path):
        print("missing %s" % path)
        return
    html = open(path, encoding="utf-8", errors="ignore").read()
    rows = (parse_booking if site == "booking" else parse_airbnb)(html, nights)

    print("\n" + "=" * 78)
    print("%s -- %d listings parsed" % (site.upper(), len(rows)))
    print("=" * 78)
    for r in rows[:12]:
        price = ("%s%s" % (r["currency"], r["price_total"])) if r["price_total"] else "?"
        night = ("%.0f/n" % r["price_night"]) if r["price_night"] else "?"
        rate = ("%.1f" % r["rating"]) if r["rating"] else "?"
        geo = "geo" if r["lat"] else "---"
        extra = []
        if r["beach_distance"]:
            extra.append("beach:%s" % r["beach_distance"])
        if r["breakfast"]:
            extra.append("bfast")
        if r["free_cancel"]:
            extra.append("freecxl")
        if r["genius"]:
            extra.append("genius")
        if r.get("crib"):
            extra.append("crib")
        if r.get("best_area"):
            extra.append("bestarea")
        if r.get("stars"):
            extra.append("%d*" % r["stars"])
        print("  %-42s %10s %8s  %4s  %s  %s"
              % (r["name"][:42], price, night, rate, geo, " ".join(extra)))
        if r["_unresolved"]:
            print("       unresolved: %s" % ", ".join(r["_unresolved"]))

    bad = [r for r in rows if r["_unresolved"]]
    print("\n  fully parsed: %d / %d" % (len(rows) - len(bad), len(rows)))
    if bad:
        # re-extract the raw records for diagnosis
        raws = []
        for body in blobs(html):
            try:
                data = json.loads(body)
            except ValueError:
                continue
            if site == "booking":
                got = _dig_booking(data)
                if got:
                    raws = got[:2]
            else:
                got = _dig_airbnb(unwrap(data))
                if got:
                    raws = got[:2]
            if raws:
                break
        _dump_unresolved(site, raws)


def _raw(site):
    """Dump the price/rating objects of the first records, verbatim."""
    path = os.path.join(OUT, "stays_%s.html" % site)
    if not os.path.exists(path):
        print("missing %s" % path)
        return
    html = open(path, encoding="utf-8", errors="ignore").read()
    recs = []
    for body in blobs(html):
        try:
            data = json.loads(body)
        except ValueError:
            continue
        data = unwrap(data) if site == "airbnb" else data
        got = _dig_airbnb(data) if site == "airbnb" else _dig_booking(data)
        if got:
            recs = got[:2]
            break
    if not recs:
        print("%s: no records found" % site)
        return
    print("\n" + "=" * 78)
    print("%s RAW price objects" % site.upper())
    print("=" * 78)
    for i, r in enumerate(recs):
        print("\n--- record %d ---" % i)
        if site == "airbnb":
            print("title:", r.get("title"), "|", r.get("subtitle"))
            print("avgRatingLocalized:", r.get("avgRatingLocalized"))
            print("structuredDisplayPrice:")
            print(json.dumps(r.get("structuredDisplayPrice"), indent=2,
                             ensure_ascii=False)[:2200])
        else:
            print("displayName:", (r.get("displayName") or {}).get("text"))
            print("priceDisplayInfoIrene:")
            print(json.dumps(r.get("priceDisplayInfoIrene"), indent=2,
                             ensure_ascii=False)[:1800])
            print("basicPropertyData:")
            print(json.dumps(r.get("basicPropertyData"), indent=2,
                             ensure_ascii=False)[:1200])


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if "--raw" in args:
        for s in [a for a in args if not a.startswith("--")] or ["booking", "airbnb"]:
            _raw(s)
    else:
        for s in args or ["booking", "airbnb"]:
            _run(s)
