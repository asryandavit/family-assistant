"""Customs estimate for one parcel (docs/briefs/MARKET_WATCH.md §9, market/customs.md).

Default rule = what the forwarders' own calculators apply (captured 2026-10-29):

    Onex FAQ   ≤ €200 and ≤ 31 kg: nothing; ≤ 31 kg and > €200: 15% of the part over €200;
               > 31 kg: 15% of the whole value + €2 per kg over 31.
    Globbing   the larger of 15% over €200 and €2 per kg over 30 kg; none on routes whose
               customs_method is 0 (Russia).
    BuyForYou  16.2% of the part over €200 (its calculateShipping()); no weight rule.

The route's `customs` dict names its variant: {"pct", "limit_eur", "weight_limit_kg",
"per_kg_eur", "combine": "onex" | "max" | "none"}. The EAEU 2026 rule (5% of the full value,
at least €1/kg, plus 20% VAT on the part over €200) is a switch, never mixed in silently.
Everything is in EUR; the caller converts with the CBA rate. Always an estimate.
"""
DEFAULT = {"pct": 15.0, "limit_eur": 200.0, "weight_limit_kg": 31.0, "per_kg_eur": 2.0,
           "combine": "onex"}

EAEU_2026 = {"duty_pct": 5.0, "min_eur_per_kg": 1.0, "vat_pct": 20.0, "limit_eur": 200.0}

NEAR = 0.10      # flag values within 10% of the limit


def default_rule(value_eur, kg, rule=None):
    r = dict(DEFAULT, **(rule or {}))
    if r["combine"] == "none":
        return 0.0
    pct = r["pct"] / 100.0
    over_value = max(0.0, value_eur - r["limit_eur"])
    over_kg = max(0.0, (kg or 0.0) - r["weight_limit_kg"]) if r.get("weight_limit_kg") else 0.0
    if r["combine"] == "max":
        return max(over_value * pct, over_kg * r["per_kg_eur"])
    if over_kg > 0:                                  # Onex FAQ point 3
        return value_eur * pct + over_kg * r["per_kg_eur"]
    return over_value * pct


def eaeu_2026(value_eur, kg, rule=None):
    r = dict(EAEU_2026, **(rule or {}))
    duty = max(value_eur * r["duty_pct"] / 100.0, (kg or 0.0) * r["min_eur_per_kg"])
    vat = max(0.0, value_eur - r["limit_eur"]) * r["vat_pct"] / 100.0
    return duty + vat


RULES = {"default": default_rule, "eaeu_2026": eaeu_2026}


def estimate(value_eur, kg, route_rule=None, which="default"):
    """{"eur", "near_limit", "rule"} for one parcel."""
    if value_eur is None:
        return None
    if which == "default":
        eur = default_rule(value_eur, kg, route_rule)
    else:
        eur = RULES[which](value_eur, kg)
    limit = dict(DEFAULT, **(route_rule or {}))["limit_eur"]
    near = (1 - NEAR) * limit <= value_eur <= (1 + NEAR) * limit
    return {"eur": eur, "near_limit": near, "rule": which}      # unrounded: AMD is derived from it
