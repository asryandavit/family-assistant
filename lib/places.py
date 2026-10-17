"""IATA code -> human place label for Telegram messages.

One source of truth for turning an airport code into a city name. Lives in
lib/ and imports nothing heavy, so the daily-scan message path never has to
reach into scrapers/ (scrapers/stays pulls in playwright at import time).

Resolution order, matching the long-standing stays helper:
  1. areas.json  -- curated city names for the stays zones
  2. stations.json via lib.stations -- the self-maintaining Wizz map
  3. the code itself, unchanged

The name map is cached per repo root. City display names effectively never
change, and a short-lived scan process rebuilds it each run; the long-running
listener picks up a refreshed stations.json on its next restart.
"""
import json
import os

_cache = {}  # root -> {CODE: city name}


def _name_map(cfg):
    root = cfg.get("_root", "")
    m = _cache.get(root)
    if m is not None:
        return m
    m = {}
    try:
        from lib import stations
        for code, st in (stations.load(cfg).get("stations") or {}).items():
            if st.get("name"):
                m[code.upper()] = st["name"]
    except Exception:
        pass
    try:
        with open(os.path.join(root, "areas.json"), encoding="utf-8") as f:
            for code, v in json.load(f).items():
                if isinstance(v, dict) and v.get("city"):
                    m[code.upper()] = v["city"]  # curated name wins
    except (OSError, ValueError):
        pass
    _cache[root] = m
    return m


def _is_code(code):
    return bool(code) and len(code) == 3 and code.isalpha()


def city(cfg, code):
    """IATA -> city name, or the code unchanged if unknown / not a 3-letter code."""
    if not _is_code(code):
        return code
    return _name_map(cfg).get(code.upper(), code.upper())


def label(cfg, code):
    """'City (CODE)' when the city is known, else the bare code.

    The code is kept because it is what /flights, /stays and the booking URLs
    take as input -- the city name is added for the reader, not instead.
    """
    if not _is_code(code):
        return code
    code = code.upper()
    name = city(cfg, code)
    return "%s (%s)" % (name, code) if name != code else code
