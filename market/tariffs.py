"""Parsers for the forwarders' published tariffs and the CBA rates -> normalised routes.

Every parser was written against a real capture in tests/fixtures/market/ (CLAUDE.md §8):

    onex       GET https://onex.am/en/tariff                 onex_tariff_en.json
    globbing   `let shippingConditions = {...}` in am.globbing.com/en   globbing_home_en.html
    buyforyou  constants in calculateShipping() on www.buyforyou.am     buyforyou_home_hy.html
    easytrans  GET api.easytrans.am/address/all-available-simple   easytrans_address_all-available-simple.json
    cba        SOAP ExchangeRatesLatest at api.cba.am            cba_latest.xml

A route: {"forwarder", "origin", "mode", "calc", <formula numbers>, "days", "customs"}.
Origins are lower-case keys (usa, uk, germany, italy, china, russia, uae, greece, spain,
poland, korea); modes are air | sea | truck. A parser that finds nothing raises ValueError —
the weekly job then keeps last week's tariffs and tells the owner (never an empty table).
"""
import html as htmllib
import json
import re
import xml.etree.ElementTree as ET

ONEX_COUNTRY = {"USA": "usa", "United Kingdom": "uk", "Germany": "germany", "Italy": "italy",
                "China": "china", "Russia": "russia", "UAE (Dubai)": "uae", "Greece": "greece",
                "Spain": "spain", "Poland": "poland"}
ONEX_MODE = {"air": "air", "sea": "sea", "ground": "truck"}

# Globbing names its warehouses in Armenian in the calculator's <option> list.
GLOBBING_COUNTRY = {"ԱՄՆ": "usa", "Անգլիա": "uk", "Չինաստան": "china", "Գերմանիա": "germany",
                    "Իտալիա": "italy", "Դուբայ": "uae", "Ռուսաստան": "russia", "Հունաստան": "greece",
                    "Կորեա": "korea", "Իսպանիա": "spain"}
# ...and its methods by the last word of each option label: express / standard / ground.
GLOBBING_MODE = {"էքսպրես": "air", "ստանդարտ": "sea", "ցամաք": "truck"}

EASYTRANS_COUNTRY = {"China": "china", "Poland": "poland"}
EASYTRANS_MODE = {"Air": "air", "Ground": "truck"}

CUSTOMS_ONEX = {"pct": 15.0, "limit_eur": 200.0, "weight_limit_kg": 31.0, "per_kg_eur": 2.0,
                "combine": "onex"}


def _num(s):
    return float(str(s).replace(",", "."))


# ---------------------------------------------------------------------- Onex

def parse_onex(text):
    rows = json.loads(text) if isinstance(text, str) else text
    out = []
    for r in rows:
        origin = ONEX_COUNTRY.get(r["country"])
        mode = ONEX_MODE.get(r["type"])
        if not origin or not mode:
            continue
        bands, volume = [], False
        for name in ("mini", "standard"):
            t = (r.get("tariffs") or {}).get(name)
            if not t:
                continue
            bands.append({"name": name, "per_100g": _num(t["cost"]),
                          "min_cost": _num(t["min_cost"]),
                          "max_kg": _num(t["max_weight"]) if t.get("max_weight") else None})
            volume = volume or bool(t.get("is_v_weight"))
            rounding = int(t.get("rounding") or 100)
        if not bands:
            continue
        out.append({"forwarder": "onex", "origin": origin, "mode": mode, "calc": "onex",
                    "dispatch_id": str(r["dispatch_id"]), "bands": bands, "rounding_g": rounding,
                    "volume": volume, "divisor": 5000,
                    "days": {"min": r.get("estimated_day_from"), "max": r.get("estimated_day_to"),
                             "unit": "working", "from": "arrival"},
                    "customs": dict(CUSTOMS_ONEX)})
    if not out:
        raise ValueError("onex: no routes in the tariff JSON")
    return out


# ------------------------------------------------------------------ Globbing

DAYS_RE = re.compile(r"(\d+(?:[.,]\d+)?)(?:\s*-\s*(\d+(?:[.,]\d+)?))?")


def parse_days(text):
    """'≈ 5-10 աշխ. օր' -> working 5..10; '≈ 3,5 ամիս' -> months 3.5; else None."""
    if not text:
        return None
    m = DAYS_RE.search(text)
    if not m:
        return None
    lo = _num(m.group(1))
    hi = _num(m.group(2)) if m.group(2) else lo
    if "ամիս" in text:
        unit = "months"
    elif "աշխ" in text:
        unit = "working"
    elif "օր" in text:
        unit = "calendar"
    else:
        return None
    as_int = (lambda x: int(x) if x == int(x) else x)
    return {"min": as_int(lo), "max": as_int(hi), "unit": unit, "from": "arrival"}


def _globbing_json(page, name):
    m = re.search(r"let %s = (.*?);\s*\n" % re.escape(name), page)
    if not m:
        raise ValueError("globbing: %s not found in the page" % name)
    return json.loads(m.group(1))


def parse_globbing(page):
    conds = _globbing_json(page, "shippingConditions")
    limit_amd = _globbing_json(page, "customsLimitConverted")
    weight_limit = _globbing_json(page, "customsWeightLimit")
    eur_rate = _globbing_json(page, "currencyEuroRate")
    labels = {}
    for m in re.finditer(r'<input type="radio" value="(\d+)" class="shipping-condition".*?'
                         r'modal-type__title">([^<]*)<', page, flags=re.S):
        labels[m.group(1)] = htmllib.unescape(m.group(2)).split()
    out = []
    for cid, c in conds.items():
        words = labels.get(str(cid)) or []
        origin = GLOBBING_COUNTRY.get(words[0]) if words else None
        mode = GLOBBING_MODE.get(words[-1]) if words else None
        if not origin:      # label country names are short ("ՌԴ"); fall back to the warehouse list
            origin = _globbing_warehouse(page).get(str(c["warehouse_id"]))
        if not origin or not mode:
            continue
        extra = c.get("additional_configs")
        out.append({"forwarder": "globbing", "origin": origin, "mode": mode, "calc": "globbing",
                    "condition_id": int(cid), "warehouse_id": c["warehouse_id"],
                    "price_per_kg": c["price_per_kg"], "min_price": c["min_price_per_kg"],
                    "min_weight": c["min_weight"], "divider": c["divider"], "step": c["step"],
                    "chargeable_weight_type": c["chargeable_weight_type"],
                    "over_dimensional": c.get("over_dimensional"),
                    "dimensions_sum": c.get("dimensions_sum"),
                    "greater_weight": c.get("greater_weight"),
                    "over_dimensional_price_per_kg": c.get("over_dimensional_price_per_kg"),
                    "compare_gross_and_dimensions": c.get("compare_gross_and_dimensions"),
                    "extra_fee": c.get("extra_fee"),
                    "additional_configs": json.loads(extra) if isinstance(extra, str) else extra,
                    "days": parse_days(c.get("average_duration_range")),
                    "customs": {"pct": 15.0, "limit_eur": 200.0,
                                "weight_limit_kg": float(weight_limit), "per_kg_eur": 2.0,
                                "combine": "max" if c.get("customs_method") else "none"},
                    "site_limit_amd": limit_amd, "site_eur_rate": eur_rate})
    if not out:
        raise ValueError("globbing: no shipping conditions parsed")
    return out


def _globbing_warehouse(page):
    out = {}
    for m in re.finditer(r'<option value="(\d+)"\s+data-foo[^>]*>\s*([^<]+?)\s*</option>', page):
        key = GLOBBING_COUNTRY.get(m.group(2).strip())
        if key:
            out[m.group(1)] = key
    return out


# ----------------------------------------------------------------- BuyForYou

def _const(js, pattern, what):
    m = re.search(pattern, js)
    if not m:
        raise ValueError("buyforyou: %s not found" % what)
    return _num(m.group(1))


def parse_buyforyou(page):
    i = page.find("function calculateShipping()")
    if i < 0:
        raise ValueError("buyforyou: calculateShipping() not found")
    fn = page[i:i + 6000]
    usd = _const(page, r"const usdPrice = (\d+(?:\.\d+)?)", "usdPrice")
    cny = _const(page, r"const cnyPrice = (\d+(?:\.\d+)?)", "cnyPrice")
    m = re.search(r"isSeaShipping\s*\?\s*(\d+)\s*:\s*\(country === 'USA' \? usdPrice : cnyPrice\)", fn)
    sea = _num(m.group(1)) if m else None
    m = re.search(r"isSeaShipping\s*\?\s*(\d+)\s*:\s*\(country === 'USA' \? (\d+) : (\d+)\)", fn)
    if not m or sea is None:
        raise ValueError("buyforyou: rates/minimums not found")
    sea_min, usa_min, cny_min = (_num(x) for x in m.groups())
    divisor = _const(fn, r"\(h \* w \* l\) / (\d+)", "volume divisor")
    side = _const(fn, r"if \(h > (\d+) \|\| w > \d+ \|\| l > \d+\)", "volume side")
    pct = _const(fn, r"extraAmount \* (0\.\d+)", "customs rate") * 100
    customs = {"pct": round(pct, 4), "limit_eur": 200.0, "weight_limit_kg": None,
               "per_kg_eur": 0.0, "combine": "onex"}
    text = re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", page)))
    common = {"forwarder": "buyforyou", "calc": "buyforyou", "divisor": divisor,
              "side_over_cm": side, "customs": customs}
    # sea exists for USA only (selectCalcCountry hides it for China)
    routes = [dict(common, origin="usa", mode="air", rate=usd, min_cost=usa_min,
                   days=_bfy_days(text, "ԱՄՆ Օդային")),
              dict(common, origin="usa", mode="sea", rate=sea, min_cost=sea_min,
                   days=_bfy_days(text, "ԱՄՆ Ծովային")),
              dict(common, origin="china", mode="air", rate=cny, min_cost=cny_min,
                   days=_bfy_days(text, "Չինաստան Օդային"))]
    return routes


def _bfy_days(text, label):
    """'ԱՄՆ Օդային 7-10 աշխատանքային օր' -> working 7..10; 'ԱՄՆ Ծովային 1.5-3 ամիս' -> months."""
    m = re.search(re.escape(label) + r" ([\d.,]+(?:-[\d.,]+)? (?:աշխատանքային օր|ամիս|օր))", text)
    if not m:
        return None
    d = parse_days(m.group(1).replace("աշխատանքային", "աշխ."))
    return d


# ----------------------------------------------------------------- EasyTrans

def parse_easytrans(text):
    data = (json.loads(text) if isinstance(text, str) else text).get("data") or []
    out = []
    for country in data:
        origin = EASYTRANS_COUNTRY.get(country.get("countryName"))
        for m in country.get("transportationMethodData") or []:
            mode = EASYTRANS_MODE.get(m.get("transportationMethodName"))
            p = m.get("priceInfo") or {}
            if not origin or not mode or p.get("transportationPrice") is None:
                continue
            days = None
            if p.get("expectedArrivalDay"):
                # its key is expectedUntilWorkingDay; counted from the truck's departure
                n = p["expectedArrivalDay"]
                days = {"min": n, "max": n, "unit": "working", "from": "dispatch",
                        "up_to": True}
            out.append({"forwarder": "easytrans", "origin": origin, "mode": mode,
                        "calc": "easytrans", "country_id": country["countryId"],
                        "method_id": m["transportationMethodId"],
                        "rate": float(p["transportationPrice"]),
                        "min_weight": float(p.get("minimalWeight") or 0),
                        "min_cost": float(p.get("minimalPrice") or 0),
                        "on_sale": bool(p.get("isSale")), "days": days,
                        "customs": dict(CUSTOMS_ONEX)})
    if not out:
        raise ValueError("easytrans: no routes in all-available-simple")
    return out


# ----------------------------------------------------------------------- CBA

CBA_NS = {"c": "http://www.cba.am/"}

CBA_REQUEST = ('<?xml version="1.0" encoding="utf-8"?>'
               '<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
               'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
               'xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
               '<soap:Body><ExchangeRatesLatest xmlns="http://www.cba.am/" /></soap:Body>'
               '</soap:Envelope>')


def parse_cba(xml_text):
    """{"date": "YYYY-MM-DD", "amd_per": {"USD": 360.51, ...}} — AMD per ONE unit."""
    root = ET.fromstring(xml_text)
    cur = root.find(".//c:CurrentDate", CBA_NS)
    rates = {}
    for r in root.iterfind(".//c:ExchangeRate", CBA_NS):
        iso = r.findtext("c:ISO", namespaces=CBA_NS)
        amount = float(r.findtext("c:Amount", namespaces=CBA_NS) or 1)
        rate = float(r.findtext("c:Rate", namespaces=CBA_NS) or 0)
        if iso and rate > 0 and amount > 0:
            rates[iso] = rate / amount
    if not rates or cur is None:
        raise ValueError("cba: no rates in the response")
    return {"date": cur.text[:10], "amd_per": rates}


# ------------------------------------------------------------------- compare

def route_key(r):
    return "%s|%s|%s" % (r["forwarder"], r["origin"], r["mode"])


PRICE_FIELDS = ("bands", "price_per_kg", "min_price", "rate", "min_cost", "min_weight",
                "divider", "step", "days", "customs", "compare_gross_and_dimensions")


def diff(old_routes, new_routes):
    """Human lines for what changed between two tariff tables (the weekly report)."""
    old = {route_key(r): r for r in old_routes or []}
    new = {route_key(r): r for r in new_routes or []}
    lines = []
    for k in sorted(set(old) | set(new)):
        if k not in old:
            lines.append("new route %s" % k.replace("|", " "))
        elif k not in new:
            lines.append("route gone %s" % k.replace("|", " "))
        else:
            changed = [f for f in PRICE_FIELDS if old[k].get(f) != new[k].get(f)]
            if changed:
                lines.append("%s: %s changed" % (k.replace("|", " "), ", ".join(changed)))
    return lines
