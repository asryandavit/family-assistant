"""Self-maintaining station map, sourced from Wizz Air's own asset endpoint.

Wizz publishes every station it serves (code, city name, country, coordinates,
and the routes each one connects to). Refreshing this weekly means new
destinations appear automatically -- no hardcoded IATA table to maintain.

The endpoint is versioned (.../29.7.1/Api/asset/map), so the version is
discovered from the site rather than pinned. If the direct fetch is refused,
the scraper picks the same response up during a normal browser run.

Produces stations.json:
  {"version": "29.7.1", "fetched": "2026-07-24",
   "stations": {"TIA": {"name": "Tirana", "country": "Albania",
                        "lat": 41.41, "lng": 19.72, "connections": ["EVN", ...]}}}
"""
import json
import os
import re
from datetime import date

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
VERSION_PROBE = "https://www.wizzair.com/en-gb"
MAP_URL = ("https://be.wizzair.com/{v}/Api/asset/map"
           "?languageCode=en-gb&withConnections=true")
FALLBACK_VERSIONS = ["29.7.1", "29.6.1", "29.8.1", "30.0.1"]


def _discover_version():
    try:
        html = requests.get(VERSION_PROBE, headers={"User-Agent": UA}, timeout=20).text
        hits = re.findall(r"be\.wizzair\.com/(\d+\.\d+\.\d+)/", html)
        if hits:
            return max(set(hits), key=hits.count)
    except requests.RequestException:
        pass
    return None


def fetch(verbose=True):
    """Returns (stations_dict, version) or (None, None) if unreachable."""
    versions = [v for v in [_discover_version()] if v] + FALLBACK_VERSIONS
    for v in versions:
        try:
            r = requests.get(MAP_URL.format(v=v),
                             headers={"User-Agent": UA, "Accept": "application/json"},
                             timeout=25)
            if r.status_code != 200:
                continue
            data = r.json()
        except (requests.RequestException, ValueError):
            continue

        cities = data.get("cities") or data.get("Cities") or []
        out = {}
        for c in cities:
            code = c.get("iata") or c.get("Iata")
            if not code:
                continue
            conns = []
            for cn in (c.get("connections") or c.get("Connections") or []):
                t = cn.get("iata") if isinstance(cn, dict) else cn
                if t:
                    conns.append(t)
            out[code] = {
                "name": c.get("shortName") or c.get("name") or code,
                "country": (c.get("countryName") or c.get("countryCode") or ""),
                "lat": c.get("latitude"), "lng": c.get("longitude"),
                "connections": sorted(set(conns)),
            }
        if out:
            if verbose:
                print(f"  stations: {len(out)} from Wizz map v{v}")
            return out, v
    if verbose:
        print("  stations: endpoint unreachable (keeping existing file)")
    return None, None


def ingest_captured(captured):
    """Fallback: pull the map payload out of responses captured in-browser."""
    for resp in captured or []:
        if "Api/asset/map" not in resp.get("url", ""):
            continue
        data = resp.get("data") or {}
        cities = data.get("cities") or data.get("Cities") or []
        out = {}
        for c in cities:
            code = c.get("iata") or c.get("Iata")
            if code:
                out[code] = {
                    "name": c.get("shortName") or c.get("name") or code,
                    "country": c.get("countryName") or "",
                    "lat": c.get("latitude"), "lng": c.get("longitude"),
                    "connections": sorted(
                        {(x.get("iata") if isinstance(x, dict) else x)
                         for x in (c.get("connections") or []) if x}),
                }
        if out:
            return out
    return None


def path(cfg):
    return os.path.join(cfg["_root"], "stations.json")


def load(cfg):
    try:
        with open(path(cfg), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"stations": {}}


def save(cfg, stations, version):
    with open(path(cfg), "w", encoding="utf-8") as f:
        json.dump({"version": version, "fetched": date.today().isoformat(),
                   "stations": stations}, f, ensure_ascii=False, indent=2)


def refresh(cfg, captured=None, verbose=True):
    """Refresh the map; returns (new_codes, removed_codes) reachable from home."""
    home = cfg["wizz"].get("origin_code", "EVN")
    prev = load(cfg)
    prev_st = prev.get("stations", {})

    fresh, version = fetch(verbose=verbose)
    if fresh is None and captured:
        fresh = ingest_captured(captured)
        version = prev.get("version", "?")
    if not fresh:
        return [], []

    def reachable(st):
        h = st.get(home) or {}
        conns = set(h.get("connections") or [])
        if conns:
            return conns
        return {c for c, v in st.items() if home in (v.get("connections") or [])}

    old_r, new_r = reachable(prev_st) if prev_st else set(), reachable(fresh)
    save(cfg, fresh, version)
    if not prev_st:
        return [], []          # first build: everything is "new", stay quiet
    return sorted(new_r - old_r), sorted(old_r - new_r)


def city_name(cfg, code, fallback=None):
    st = load(cfg).get("stations", {}).get(code.upper())
    return (st or {}).get("name") or fallback or code


def coords(cfg, code):
    st = load(cfg).get("stations", {}).get(code.upper()) or {}
    if st.get("lat") and st.get("lng"):
        return {"lat": st["lat"], "lng": st["lng"]}
    return None
