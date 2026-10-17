"""Assemble round-trip and open-jaw options from farechart price-by-date rows.

Deterministic: every price is arithmetic on values Wizz returned. The model is
never involved in a number here.

Family total = (outbound + inbound) x adults
             + infant fee x 2 legs
             + ground transport x adults, for open jaw only

Open jaw has three gates, all from nearby.json:
  1. the two cities must have a curated ground link (<= 5 hours)
  2. the trip must be long enough to justify moving (days_gate)
  3. the second city needs a real stay, not an overnight (min_nights_second_city)
"""
import json
import os
import re
from datetime import date, timedelta

from lib import fx

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_nearby(cfg):
    path = os.path.join(cfg["_root"], "nearby.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"links": [], "days_gate": [], "min_nights_second_city": 3}


def neighbours(nb, code):
    """{other_code: link} for everything reachable by ground from `code`."""
    out = {}
    for l in nb.get("links", []):
        if l["a"] == code:
            out[l["b"]] = l
        elif l["b"] == code:
            out[l["a"]] = l
    return out


def gate_ok(nb, hours, nights):
    """Is the trip long enough to justify a ground move of this length?"""
    gates = sorted(nb.get("days_gate", []), key=lambda g: g["max_hours"])
    for g in gates:
        if hours <= g["max_hours"]:
            return nights >= g["min_nights"]
    return False


def seats(cfg, on):
    """Adult seats plus a third if the child needs one by that date."""
    p = cfg.get("passengers", {})
    flip = date.fromisoformat(p.get("flip_date", "2026-12-29"))
    adults = cfg.get("flights", {}).get("adults", 2)
    return adults + (1 if on >= flip else 0)


def _dates_in(window_from, window_to):
    a, b = date.fromisoformat(window_from), date.fromisoformat(window_to)
    out, d = [], a
    while d <= b:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def plan_requests(cfg, dest, window_from, window_to, include_openjaw=True):
    """Which booking pages to load. One per route; farechart spans dates."""
    home = cfg["wizz"].get("origin_code", "EVN")
    nb = load_nearby(cfg)
    mid = _dates_in(window_from, window_to)
    anchor = mid[len(mid) // 2]

    reqs = [{"from": home, "to": dest, "date_out": window_from,
             "date_back": window_to}]
    if include_openjaw:
        for code in sorted(neighbours(nb, dest)):
            reqs.append({"from": code, "to": home, "date_out": anchor})
    return reqs


def assemble(cfg, rows, dest, window_from, window_to, nights, flags=None):
    """rows: parsed farechart rows. Returns ranked options."""
    flags = flags or {}
    home = cfg["wizz"].get("origin_code", "EVN")
    fl = cfg.get("flights", {})
    nb = load_nearby(cfg)
    infant_fee_eur = fl.get("infant_fee_eur_per_leg", 32)
    infants = fl.get("infants", 1)
    infant_total = (fx.to_usd(infant_fee_eur, "EUR") or infant_fee_eur * 1.09) * 2 * infants

    lo, hi = date.fromisoformat(window_from), date.fromisoformat(window_to)
    depart_after = flags.get("depart_after")   # datetime or None
    n_min, n_max = nights

    idx = {}
    for r in rows:
        idx.setdefault((r["origin"], r["destination"]), {})[r["date"]] = r

    outs = idx.get((home, dest), {})
    options = []

    def add(o_row, i_row, back_code, link=None):
        d1 = date.fromisoformat(o_row["date"])
        d2 = date.fromisoformat(i_row["date"])
        n = (d2 - d1).days
        if n < n_min or n > n_max:
            return
        if not (lo <= d1 <= hi and lo <= d2 <= hi):
            return
        if depart_after and d1 < depart_after.date():
            return
        s1, s2 = seats(cfg, d1), seats(cfg, d2)
        ground = 0.0
        if link:
            if not gate_ok(nb, link["hours"], n):
                return
            if n < nb.get("min_nights_second_city", 3) * 2:
                return
            per = fx.to_usd(link.get("cost_eur_pp", 40), "EUR") or 45
            ground = per * fl.get("adults", 2)
        total = round(o_row["price"] * s1 + i_row["price"] * s2
                      + infant_total + ground, 2)
        options.append({
            "kind": "return" if not link else "openjaw",
            "out_city": dest, "in_city": back_code,
            "route": dest if not link else "%s>%s" % (dest, back_code),
            "out_date": o_row["date"], "back_date": i_row["date"],
            "nights": n,
            "out_price": o_row["price"], "in_price": i_row["price"],
            "out_src": o_row.get("src", "-"), "in_src": i_row.get("src", "-"),
            "seats": "%dx%d" % (s1, s2) if s1 == s2 else "%d/%d" % (s1, s2),
            "pax": "2A" if (s1, s2) == (2, 2) else "2A+1C",
            "ground": round(ground, 2),
            "link": ("%s %.1fh %s" % (link["mode"], link["hours"], link["note"])
                     if link else ""),
            "infant_fee": round(infant_total, 2),
            "total": total,
        })

    # same-airport return
    for o in outs.values():
        for i in idx.get((dest, home), {}).values():
            add(o, i, dest)

    # open jaw from a ground-linked neighbour
    for code, link in neighbours(nb, dest).items():
        for o in outs.values():
            for i in idx.get((code, home), {}).values():
                add(o, i, code, link)

    options.sort(key=lambda x: x["total"])
    seen, uniq = set(), []
    for o in options:
        k = (o["route"], o["out_date"], o["back_date"])
        if k not in seen:
            seen.add(k)
            uniq.append(o)
    return uniq


def parse_command(text, cfg, today=None):
    """/flights <dest> <dd-dd.mm | dd.mm-dd.mm> [nights] [noopen]"""
    from lib.parse_cmd import parse_dates

    parts = (text or "").strip().split()
    if parts and parts[0].lower().lstrip("/").startswith("flights"):
        parts = parts[1:]
    if not parts:
        return {"error": "Usage: <code>/flights BUD 01-30.11 7</code>"}

    dest_tokens, rest, dates = [], [], None
    for i, tok in enumerate(parts):
        if dates is None and i > 0:
            got = parse_dates(tok, today)
            if got:
                dates = got
                rest = parts[i + 1:]
                break
        dest_tokens.append(tok)
    if not dates:
        got = parse_dates(parts[-1], today) if len(parts) > 1 else None
        if got:
            dates, dest_tokens, rest = got, parts[:-1], []
    if not dates:
        return {"error": "I couldn't read the dates. Try "
                         "<code>/flights BUD 01-30.11 7</code>"}

    dest = " ".join(dest_tokens)
    dest = dest.upper() if (len(dest) == 3 and dest.isalpha()) else dest

    n_min = n_max = cfg.get("flights", {}).get("default_nights", 7)
    include_openjaw = True
    for tok in rest:
        low = tok.lower()
        if low in ("noopen", "direct", "return"):
            include_openjaw = False
            continue
        m = re.fullmatch(r"(\d+)-(\d+)", low)
        if m:
            n_min, n_max = int(m.group(1)), int(m.group(2))
            continue
        m = re.fullmatch(r"(\d+)n?", low)
        if m:
            n_min = n_max = int(m.group(1))

    ci, co = dates
    if (co - ci).days < 1:
        return {"error": "That window is too short."}
    return {"dest": dest, "window_from": ci.isoformat(), "window_to": co.isoformat(),
            "nights": (n_min, n_max), "include_openjaw": include_openjaw}
