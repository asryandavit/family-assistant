import json
import os
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["_root"] = ROOT
    return cfg


def resolve_passengers(cfg, on=None):
    """Return the passenger mix for a given travel date.

    The toddler flies as a lap infant until flip_date (their 2nd birthday),
    then needs a paid child seat. `on` should be the outbound travel date;
    check the return leg separately if it crosses the flip date.
    """
    on = on or date.today()
    if isinstance(on, str):
        on = date.fromisoformat(on)
    p = cfg["passengers"]
    flip = date.fromisoformat(p["flip_date"])
    return dict(p["before"]) if on < flip else dict(p["after"])
