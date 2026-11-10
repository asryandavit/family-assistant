"""/china result -> display JSON for the Mini App China screen (docs/briefs/MINI_APP.md §12).

Pure: takes the saved `last_<chat>.json` payload (china/search.save_last) and returns plain
strings and flags. Every number and sentence comes from the same china/report.py helpers the
chat answer uses (their HTML stripped) and the 🏆 pick from china/pricing.best_pick, so the
app and the chat can never disagree, and the page does no arithmetic (CLAUDE.md §2).
"""
import html
import re
from datetime import datetime

from china import parse, pricing, report
from lib.ui import YEREVAN

TAG = re.compile(r"<[^>]+>")
BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
JOB_RE = re.compile(r"^[0-9a-f]{8}$")


def plain(s):
    """report.py HTML -> plain lines (<br> splits; tags dropped; entities decoded)."""
    out = []
    for part in BR.split(str(s or "")):
        t = html.unescape(TAG.sub("", part)).strip()
        if t:
            out.append(t)
    return out


def _one(s):
    return " ".join(plain(s))


def _sent_local(utc_iso):
    try:
        return datetime.fromisoformat(utc_iso).astimezone(YEREVAN).strftime("%d %b %H:%M")
    except (TypeError, ValueError):
        return ""


def _site_line(s):
    name = report.SITE_NAME.get(s["site"], s["site"])
    if s["status"] == "ok":
        n = len(s.get("ranked") or [])
        return f"{n} result{'s' if n != 1 else ''}"
    if s["status"] in report.STATUS_TEXT:
        return report.STATUS_TEXT[s["status"]] % name
    return s["status"]


def _pick(numbered):
    """(n of the 🏆 pick, reason) or (None, ""). Results saved before the trust score
    (decision 092) have no trust_parts and get no pick; they expire within 24 h anyway."""
    try:
        best, why = pricing.best_pick([p for _, p in numbered])
    except (KeyError, TypeError, ValueError):
        return None, ""
    for n, p in numbered:
        if p is best:
            return n, why
    return None, ""


def card(n, p, category, pick_n):
    """One result as display fields. Links are built in code from item ids (china/parse.py);
    anything not https is dropped here too, and without a link there is nothing to watch."""
    link = p.get("link") if str(p.get("link") or "").startswith("https://") else None
    b = p.get("best") or {}
    notes = plain(report.price_line(p))[1:]          # first line is the price itself
    reviews = {"read": bool(p.get("reviews_read")),
               "count": "{:,}".format(p["reviews"]) if p.get("reviews") is not None else None,
               "liked": list(p.get("liked") or []) if p.get("reviews_read") else [],
               "complaints": list(p.get("complaints") or []) if p.get("reviews_read") else []}
    return {
        "n": n,
        "pick": n == pick_n,
        "site": p["site"],
        "site_name": report.SITE_NAME.get(p["site"], p["site"]),
        "title": report.short(p.get("title_en"), 120),
        "title_cn": report.short(p.get("title_cn"), 120),
        "variant": p.get("variant") or None,
        "seller": _one(report.seller_line(p)),
        "trust": p.get("trust"),
        "trust_line": _one(report.trust_line(p)) if p.get("trust_parts") is not None else None,
        "price": plain(report.price_line(p))[0],
        "notes": notes,
        "total": (f"{report.amd(p.get('total_amd'))} AMD ({report.usd(p.get('total_usd'))}) "
                  f"via {report.route_label(b)}") if p.get("total_amd") is not None and b else None,
        "routes": [_one(x) for x in report.route_lines(p)],
        "weight": [_one(x) for x in report.weight_line(p)],
        "delivery": p.get("delivery_note") or None,
        "sales": "{:,}".format(p["sales"]) if p.get("sales") is not None else None,
        "min_order": p.get("min_order_text") or None,
        "specs": [f"{k}: {v}" for k, v in list((p.get("specs") or {}).items())[:6]],
        "material": p.get("material") or None,
        "size": p.get("size_advice") or None,
        "reviews": reviews,
        "flags": [parse.RESTRICT_TEXT[f] for f in p.get("flags") or [] if f in parse.RESTRICT_TEXT],
        "why": p.get("why") or None,
        "ask_seller": ((report.SELLER_MSG_PLUG if category == "electronics" else report.SELLER_MSG)
                       if p.get("weight_assumed") else None),
        "link": link,
        "can_watch": p.get("price") is not None and link is not None,
        "can_reviews": not p.get("reviews_read"),
    }


def view(last):
    """Saved payload -> {"empty": True} or the screen's data."""
    if not last or not last.get("sites"):
        return {"empty": True}
    numbered = report.numbered(last["sites"])
    pick_n, why = _pick(numbered)
    category = last.get("category") or "other"
    return {
        "empty": False,
        "job": last.get("job"),
        "kind": last.get("kind") or "search",
        "query": report.short(last.get("description"), 160),
        "query_cn": last.get("query_cn") or None,
        "sent": _sent_local(last.get("sent_utc")),
        "sites": [{"site": s["site"], "name": report.SITE_NAME.get(s["site"], s["site"]),
                   "status": s["status"], "line": _site_line(s)} for s in last["sites"]],
        "pick": pick_n,
        "pick_reason": why or None,
        "results": [card(n, p, category, pick_n) for n, p in numbered],
    }
