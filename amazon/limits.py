"""The politeness limits that survive a restart (docs/briefs/AMAZON_SEARCH.md §6.3): at most N
/amazon runs per local day, and a store that showed a check page is not opened again for
cooldown_hours. One small JSON file in .browser/amazon_data; one writer (the single worker).

    {"runs_local": {"2026-11-10": 3},
     "blocked_utc": {"uk": "2026-11-10T08:15:00+00:00"}}        (CLAUDE.md §4 naming)
"""
import json
import os
from datetime import UTC, datetime, timedelta

from amazon import data_dir


def _path(root):
    return os.path.join(data_dir(root), "limits.json")


def load(root):
    try:
        with open(_path(root), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d.setdefault("runs_local", {})
    d.setdefault("blocked_utc", {})
    return d


def _save(root, d):
    d["runs_local"] = dict(sorted(d["runs_local"].items())[-14:])      # two weeks are enough
    tmp = _path(root) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(tmp, _path(root))


def runs_today(root, today_local):
    return int(load(root)["runs_local"].get(today_local.isoformat(), 0))


def can_start(root, today_local, max_per_day):
    """(ok, sentence). The sentence says when the day's allowance returns."""
    n = runs_today(root, today_local)
    if n >= max_per_day:
        return False, ("I have already searched Amazon %d times today (the limit that keeps the "
                       "bot's browser from being blocked). Try again tomorrow, or open the "
                       "search yourself." % n)
    return True, ""


def count_run(root, today_local):
    d = load(root)
    k = today_local.isoformat()
    d["runs_local"][k] = int(d["runs_local"].get(k, 0)) + 1
    _save(root, d)


def mark_blocked(root, site, now_utc=None):
    d = load(root)
    d["blocked_utc"][site] = (now_utc or datetime.now(UTC)).isoformat(timespec="seconds")
    _save(root, d)


def cooling(root, site, hours, now_utc=None):
    """Hours left of the store's cool-down (0 when it may be opened)."""
    raw = load(root)["blocked_utc"].get(site)
    if not raw:
        return 0.0
    left = datetime.fromisoformat(raw) + timedelta(hours=hours) - (now_utc or datetime.now(UTC))
    return max(0.0, left.total_seconds() / 3600.0)
