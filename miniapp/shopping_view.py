"""The shared tick list as the Mini App shows it (decision 108).

The list itself — what is on it, who ticked what, the quality-rule picks and their reasons — is
shopping/checklist.py (decision 106), the same state /list shows in the chat. This module only
shapes it for the page: Telegram ids become names, UTC becomes Yerevan time, only https links go
out, and the internal fields stay home. No number is computed here.
"""
from datetime import datetime

from lib.fmt_grocery import money
from lib.ui import YEREVAN
from miniapp import screens
from shopping import checklist


def _when(utc_iso):
    try:
        d = datetime.fromisoformat(utc_iso).astimezone(YEREVAN)
        return f"{d.day} {d:%b %H:%M}"
    except (TypeError, ValueError):
        return ""


def _who(user_id, names):
    return names.get(user_id) or "someone"


def _url(u):
    return u if isinstance(u, str) and screens.SAFE_URL.match(u) else None


def shape(raw, names):
    """checklist.load() dict -> display dict."""
    groups = []
    for g in raw["groups"]:
        items = [{"key": i["key"], "item": i["item"], "amount": i.get("amount") or "",
                  "shop_name": i.get("shop_name"), "buy": i.get("buy"), "product": i.get("product"),
                  "url": _url(i.get("url")), "reason": i.get("reason"),
                  "cost": money(i["cost"]) if isinstance(i.get("cost"), (int, float)) else None,
                  "done": bool(i.get("done")),
                  "by_name": _who(i.get("by"), names) if i.get("done") else None,
                  "at": _when(i.get("at_utc")) if i.get("done") else None}
                 for i in g["items"]]
        groups.append({"aisle": g["aisle"], "items": items})
    last, reset = raw.get("last"), raw.get("reset")
    return {"kind": raw["kind"], "period_label": raw["period_label"], "version": raw["version"],
            "done": raw["done"], "total": raw["total"], "groups": groups,
            "last": ({"item": last["item"], "by_name": _who(last["by"], names), "at": _when(last["at_utc"])}
                     if last else None),
            "reset": ({"by_name": _who(reset["by"], names), "at": _when(reset["at_utc"])}
                      if reset else None)}


def view(root, kind, names):
    """The list for `kind`, or None for an unknown kind, or {"unavailable": True, "message"} when
    basket.md cannot be read (the sentence is the checklist's own)."""
    if kind not in checklist.KINDS:
        return None
    try:
        raw = checklist.load(root, kind)
    except ValueError as e:
        return {"unavailable": True, "message": screens.plain(str(e))}
    return shape(raw, names)
