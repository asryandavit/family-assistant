"""Each forwarder's price formula, reproduced from its own calculator (tests oracle).

A route (market/tariffs.json) carries `calc` naming the formula and the numbers it uses:

    onex       per-100 g bands (≤1 kg "mini", "standard"), rounded UP to `rounding_g`,
               minimum per band; volume only where `volume` is true (sea), L×W×H/5000.
               Oracle: tests/fixtures/market/onex_calculator.json (its calculator API).
    globbing   Globbing's Calculator.calculate (tests/fixtures/market/globbing_calculator.js):
               L×W×H/5000 counted when the route compares gross and volume (or is volume-
               charged, or over-dimensional), min weight, grams rounded to `step` with the
               `divider` tolerance (a remainder under it rounds down), price per kg, minimum.
    buyforyou  calculateShipping() on buyforyou.am: volume L×W×H/6000 only when a side
               exceeds 60 cm; at or under the minimum -> minimum, else rounded up to 100 AMD.
    easytrans  its calculate-price API: max(rate × kg, minimal price); no step, no volume.

quote(route, actual_kg, dims_cm) -> {"chargeable_kg", "cost_amd", "band", "volume_kg"}.
actual_kg None -> None (the caller shows the rate per kg and "weight needed").
"""
import math
from decimal import ROUND_CEILING, Decimal


def volume_kg(dims_cm, divisor):
    if not dims_cm or not divisor:
        return 0.0
    length, width, height = dims_cm
    return length * width * height / divisor


def _js_round(x):
    """Math.round: halves go up (Python's round() goes to even)."""
    return math.floor(x + 0.5)


def onex(route, actual_kg, dims_cm=None):
    kg = actual_kg
    vol = volume_kg(dims_cm, route.get("divisor", 5000)) if route.get("volume") else 0.0
    if vol > kg:
        kg = vol
    step = Decimal(route.get("rounding_g", 100))
    units = (Decimal(str(kg)) * 1000 / step).to_integral_value(rounding=ROUND_CEILING)
    weight = units * step / 1000
    bands = route["bands"]
    band = next((b for b in bands if b.get("max_kg") is None
                 or weight <= Decimal(str(b["max_kg"]))), bands[-1])
    cost = Decimal(str(band["per_100g"])) * weight * 10
    cost = max(cost, Decimal(str(band.get("min_cost") or 0)))
    return {"chargeable_kg": float(weight), "cost_amd": float(cost), "band": band["name"],
            "volume_kg": round(vol, 3)}


def onex_band(route, name, actual_kg, dims_cm=None):
    """The cost in one named band (the calculator shows both mini and standard)."""
    forced = dict(route, bands=[b for b in route["bands"] if b["name"] == name])
    forced["bands"] = [dict(forced["bands"][0], max_kg=None)]
    return onex(forced, actual_kg, dims_cm)


def globbing(route, actual_kg, dims_cm=None):
    c = route
    weight = float(actual_kg)
    length, width, height = dims_cm or (0, 0, 0)
    dim = (width * height * length) / 5000
    over = False
    if c.get("chargeable_weight_type") == 2:
        use_dim = True
    else:
        over = (c.get("over_dimensional") == 1
                and c.get("dimensions_sum") is not None
                and (width + height + length) >= c["dimensions_sum"]
                and weight > 0 and (dim / weight) > (c.get("greater_weight") or 0))
        use_dim = over or c.get("compare_gross_and_dimensions") == 1
    if use_dim:
        weight = weight if weight > dim else dim
    weight = c["min_weight"] if weight < c["min_weight"] else weight
    grams = _js_round(weight * 1000)
    divider = c["divider"] * 1000          # float on purpose: same doubles as the JS
    step = c["step"] * 1000
    if int(grams % step) < divider:
        grams = int(grams / step) * step
    else:
        grams = (int(grams / step) + 1) * step
    per_kg = c["over_dimensional_price_per_kg"] if over else _price_per_kg(c, grams)
    price = (grams / 1000) * per_kg
    price = c["min_price"] if price < c["min_price"] else price
    if c.get("extra_fee") is not None:
        price += c["extra_fee"]
    price = _js_round(price * 100) / 100
    return {"chargeable_kg": grams / 1000, "cost_amd": price, "band": "over-dimensional" if over else "",
            "volume_kg": round(dim, 3)}


def _price_per_kg(c, grams):
    per_kg = c["price_per_kg"]
    for cfg in sorted(c.get("additional_configs") or [], key=lambda x: -x["weight"]):
        if cfg.get("source", "globbing") != "globbing":
            continue
        if grams / 1000 >= cfg["weight"]:
            return cfg["price"]
    return per_kg


def buyforyou(route, actual_kg, dims_cm=None):
    kg = float(actual_kg)
    vol = 0.0
    if dims_cm and any(side > route["side_over_cm"] for side in dims_cm):
        vol = volume_kg(dims_cm, route["divisor"])
        if vol > kg:
            kg = vol
    cost = kg * route["rate"]
    if kg > 0:
        cost = route["min_cost"] if cost <= route["min_cost"] else math.ceil(cost / 100) * 100
    return {"chargeable_kg": kg, "cost_amd": float(cost), "band": "", "volume_kg": round(vol, 3)}


def easytrans(route, actual_kg, dims_cm=None):
    kg = max(float(actual_kg), route.get("min_weight") or 0.0)
    cost = max(route["rate"] * kg, route["min_cost"])
    return {"chargeable_kg": kg, "cost_amd": float(cost), "band": "", "volume_kg": 0.0}


FORMULAS = {"onex": onex, "globbing": globbing, "buyforyou": buyforyou, "easytrans": easytrans}


def quote(route, actual_kg, dims_cm=None):
    if actual_kg is None:
        return None
    if actual_kg <= 0:
        raise ValueError("weight must be above 0 kg")
    return FORMULAS[route["calc"]](route, actual_kg, dims_cm)


def per_kg(route):
    """The headline AMD/kg for a route (shown when the item has no weight yet)."""
    if route["calc"] == "onex":
        return route["bands"][-1]["per_100g"] * 10
    if route["calc"] == "globbing":
        return route["price_per_kg"]
    return route["rate"]
