"""Parse phone-friendly /stays commands.

    /stays LCA 04-11.11 sea center budget120
    /stays Larnaca 04.11-11.11 apt quiet
    /stays BUD 24.01            -> 7 nights from 24 Jan

Dates: dd-dd.mm or dd.mm-dd.mm; a single dd.mm starts a default stay.
Years are inferred -- a date already past rolls to next year.

Occupancy follows the toddler's age at CHECK-IN: lap infant before the flip
date, a child needing their own bed after it.
"""
import re
from datetime import date, timedelta

KEYWORDS = {
    "sea": "sea", "beach": "sea", "seaview": "sea",
    "center": "center", "centre": "center", "central": "center",
    "quiet": "quiet", "pool": "pool", "breakfast": "breakfast",
    "apt": "apt", "apartment": "apt", "flat": "apt",
    "hotel": "hotel", "strict": "strict", "lift": "lift", "elevator": "lift",
}

DEFAULT_NIGHTS = 7


def _year_for(day, month, today=None):
    today = today or date.today()
    y = today.year
    try:
        d = date(y, month, day)
    except ValueError:
        return None
    return d if d >= today else date(y + 1, month, day)


def parse_dates(token, today=None):
    """Returns (checkin, checkout) or None."""
    if not token:
        return None
    t = token.strip().replace("/", ".")

    # dd.mm-dd.mm
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\s*-\s*(\d{1,2})\.(\d{1,2})", t)
    if m:
        d1, m1, d2, m2 = (int(x) for x in m.groups())
        ci = _year_for(d1, m1, today)
        if not ci:
            return None
        co = date(ci.year, m2, d2)
        if co <= ci:
            co = date(ci.year + 1, m2, d2)
        return ci, co

    # dd-dd.mm  (both days in the same month)
    m = re.fullmatch(r"(\d{1,2})\s*-\s*(\d{1,2})\.(\d{1,2})", t)
    if m:
        d1, d2, mo = (int(x) for x in m.groups())
        ci = _year_for(d1, mo, today)
        if not ci:
            return None
        try:
            co = date(ci.year, mo, d2)
        except ValueError:
            return None
        if co <= ci:
            return None
        return ci, co

    # dd.mm -> default stay
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})", t)
    if m:
        d1, m1 = int(m.group(1)), int(m.group(2))
        ci = _year_for(d1, m1, today)
        return (ci, ci + timedelta(days=DEFAULT_NIGHTS)) if ci else None

    # ISO fallback
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})-(\d{4}-\d{2}-\d{2})", t)
    if m:
        return date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))
    return None


def occupancy(cfg, checkin):
    """(adults, children, child_age) for the check-in date."""
    p = cfg.get("passengers", {})
    flip = date.fromisoformat(p.get("flip_date", "2026-12-29"))
    born = flip.replace(year=flip.year - 2)
    age = checkin.year - born.year - ((checkin.month, checkin.day) < (born.month, born.day))
    return 2, 1, max(age, 0)


def parse(text, cfg, today=None):
    """Parse a /stays command. Returns dict or {'error': ...}."""
    parts = (text or "").strip().split()
    if parts and parts[0].lower().lstrip("/").startswith("stays"):
        parts = parts[1:]
    if not parts:
        return {"error": "Usage: /stays <city> <dd-dd.mm> [sea center quiet pool "
                         "breakfast apt hotel budget120]"}

    # City may be several words ("Tel Aviv", "New York"): everything up to the
    # first token that reads as a date belongs to the city.
    city_tokens = []
    idx = 0
    for i, tok in enumerate(parts):
        if i > 0 and parse_dates(tok, today):
            break
        city_tokens.append(tok)
        idx = i + 1
    city = " ".join(city_tokens)
    if len(city) == 3 and city.isalpha():
        city = city.upper()
    rest = parts[idx:]

    dates, flags, budget = None, set(), None
    for tok in rest:
        low = tok.lower()
        if dates is None:
            got = parse_dates(tok, today)
            if got:
                dates = got
                continue
        m = re.fullmatch(r"budget\s*<?(\d+)", low)
        if m:
            budget = int(m.group(1))
            continue
        if low in KEYWORDS:
            flags.add(KEYWORDS[low])

    if not dates:
        return {"error": "I couldn't read the dates. Try <code>/stays LCA 04-11.11 sea</code>"}

    ci, co = dates
    nights = (co - ci).days
    if nights < 1 or nights > 30:
        return {"error": "Stay length looks wrong (%d nights)." % nights}

    adults, children, age = occupancy(cfg, ci)
    return {
        "city": city, "checkin": ci.isoformat(), "checkout": co.isoformat(),
        "nights": nights, "flags": sorted(flags), "budget": budget,
        "adults": adults, "children": children, "child_age": age,
    }
