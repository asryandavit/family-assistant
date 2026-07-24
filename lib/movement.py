"""Price-movement detection over the Flights history in the sheet.

Comparison granularity is route + month, not exact date: the fare finder
returns "cheapest date per destination per window", and that date shifts
between runs even when nothing meaningful changed.

All numbers are computed here in Python; the model never touches them.
"""
from collections import defaultdict


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_history(rows):
    """rows: Flights tab values without header.
    Returns {(origin, dest, 'YYYY-MM', type): {run_date: min_price}}."""
    hist = defaultdict(dict)
    for r in rows:
        if len(r) < 8:
            continue
        run, o, d, out_date, typ, reg = r[0], r[1], r[2], r[3], r[6], r[7]
        p = _f(reg)
        if not (run and o and d and out_date) or p is None:
            continue
        key = (o, d, out_date[:7], typ)
        cur = hist[key].get(run)
        if cur is None or p < cur:
            hist[key][run] = p
    return hist


def merge_today(hist, fares, today):
    """Fold today's parsed fares into the history structure."""
    for f in fares:
        key = (f["origin"], f["destination"], f["out_date"][:7], f["type"])
        cur = hist[key].get(today)
        if cur is None or f["regular"] < cur:
            hist[key][today] = f["regular"]
    return hist


def analyze(hist, today, alerts_cfg):
    """Returns (drops, new_routes, all_time_lows)."""
    pct_t = alerts_cfg.get("leg_drop_pct", 15)
    abs_t = alerts_cfg.get("leg_drop_abs", 5)
    min_hist = alerts_cfg.get("min_history_runs_for_atl", 3)

    routes_before = set()
    for (o, d, _m, _t), runs in hist.items():
        if any(rd < today for rd in runs):
            routes_before.add((o, d))

    drops, new_routes, atl = [], [], []
    seen_new = set()

    for (o, d, month, typ), runs in hist.items():
        if today not in runs:
            continue
        now = runs[today]
        prior = {rd: p for rd, p in runs.items() if rd < today}

        if not prior:
            if (o, d) not in routes_before and (o, d) not in seen_new:
                seen_new.add((o, d))
                new_routes.append({"o": o, "d": d, "month": month,
                                   "type": typ, "price": now})
            continue

        prev = prior[max(prior)]
        delta = round(now - prev, 2)
        pct = round(delta / prev * 100, 1) if prev else 0.0
        is_atl = len(prior) >= min_hist and now < min(prior.values())

        if delta <= -abs_t or pct <= -pct_t or is_atl:
            drops.append({"o": o, "d": d, "month": month, "type": typ,
                          "prev": prev, "now": now, "delta": delta,
                          "pct": pct, "atl": is_atl})

    drops.sort(key=lambda x: x["pct"])
    return drops, new_routes, atl
