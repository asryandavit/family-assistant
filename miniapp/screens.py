"""Data for the Mini App screens Today, Market, Basket and Travel (decision 098).

Read-only builders, one per screen. Each reuses what the chat shows: the plan screens turn the
chat's own Telegram HTML (coach/plan_text.py) into display blocks, Market uses the same state
and best-price helpers as /watch, Basket reads the file the basket job saved, Travel reads the
same Google Sheet tabs as the digest. No arithmetic here (CLAUDE.md §2): every number is read
or already computed by the code that produced it.
"""
import html as htmlmod
import json
import os
import re
import threading
import time
from datetime import date, datetime
from html.parser import HTMLParser

from lib.fmt_grocery import money
from lib.ui import BAR, YEREVAN, now_local

SAFE_URL = re.compile(r"^https?://", re.IGNORECASE)
PLAN_NAMES = ("today", "meals", "training", "week")


# ------------------------------------------------------------ Telegram HTML -> blocks

class _Blocks(HTMLParser):
    """Telegram's HTML subset (b, i, code, a, blockquote expandable, newlines) -> blocks:
    {"k": "p", "s": [{"t": text, "b": 1, "i": 1, "c": 1, "a": url}]} and
    {"k": "fold", "title": str, "b": [paragraph blocks]}."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self.flags, self.line, self.fold = [], [], [], None
        self.href = None

    def _flush(self):
        segs = [s for s in self.line if s["t"]]
        self.line = []
        if not segs:
            return
        if "".join(s["t"] for s in segs).strip(" ") and set("".join(s["t"] for s in segs).strip()) <= set(BAR):
            return                                                  # the ━━━ divider
        (self.fold["b"] if self.fold is not None else self.blocks).append({"k": "p", "s": segs})

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self._flush()
        elif tag == "blockquote":
            self._flush()
            self.fold = {"k": "fold", "title": "", "b": []}
        elif tag == "a":
            href = dict(attrs).get("href") or ""
            self.href = href if SAFE_URL.match(href) else None
        elif tag in ("b", "i", "code"):
            self.flags.append(tag)

    def handle_endtag(self, tag):
        if tag == "blockquote" and self.fold is not None:
            self._flush()
            fold, self.fold = self.fold, None
            if fold["b"]:
                first = fold["b"][0]
                if len(first["s"]) == 1 and first["s"][0].get("b"):
                    fold["title"] = first["s"][0]["t"].strip()
                    fold["b"] = fold["b"][1:]
                self.blocks.append(fold)
        elif tag == "a":
            self.href = None
        elif tag in ("b", "i", "code") and tag in self.flags:
            self.flags.remove(tag)

    def handle_data(self, data):
        parts = data.split("\n")
        for n, part in enumerate(parts):
            if n:
                self._flush()
            if part:
                seg = {"t": part}
                for f in self.flags:
                    seg[{"b": "b", "i": "i", "code": "c"}[f]] = 1
                if self.href:
                    seg["a"] = self.href
                self.line.append(seg)

    def close(self):
        super().close()
        self._flush()


def html_blocks(text):
    """Chat HTML -> {"title": first line as plain text, "blocks": the rest}."""
    p = _Blocks()
    p.feed(str(text or ""))
    p.close()
    blocks = p.blocks
    title = ""
    if blocks and blocks[0]["k"] == "p":
        title = "".join(s["t"] for s in blocks[0]["s"]).strip()
        blocks = blocks[1:]
    return {"title": title, "blocks": blocks}


def plain(text):
    """Telegram HTML -> one plain string."""
    return " ".join(htmlmod.unescape(re.sub(r"<[^>]+>", "", str(text or ""))).split())


# ------------------------------------------------------------ Today / Meals / Training / Week

def plan_page(root, name, chat_id):
    """The chat's own text for the person, as blocks; None if the plan can't be read."""
    from coach import plan_text, plan_view
    if name not in PLAN_NAMES:
        return None
    try:
        plan = plan_view.load_plan(root)
        day = now_local().date()
        text = {"today": lambda: plan_text.today_text(plan, day, chat_id=chat_id),
                "meals": lambda: plan_text.meals_text(plan, day),
                "training": lambda: plan_text.training_text(plan, day),
                "week": lambda: plan_text.week_text(plan, day)}[name]()
    except Exception:  # noqa: BLE001  a broken plan file must show "unreadable", not a 500
        return None
    return html_blocks(text)


# ------------------------------------------------------------ Market

def market_view(root):
    from market import bot, state
    from market import stores as stores_mod
    items = state.active(state.load_items(root))
    best = bot._best_today(root)
    rows = stores_mod.load()
    out = []
    for n, it in enumerate(items, start=1):
        names = []
        for u in it.get("links", []):
            s = stores_mod.store_for_url(u, rows)
            names.append(s["name"] if s else "?")
        b = best.get(it["id"])
        out.append({
            "n": n, "id": it["id"], "name": it["name"], "stores": names, "qty": it.get("qty") or 1,
            "added_by": it.get("added_by") or "",
            "best": f"{b[0]:,.0f} AMD · {b[2]} · {b[3][5:].replace('-', '.')}" if b else None,
            "weight_needed": not it.get("weight_kg"),
            "links": [u for u in it.get("links", []) if SAFE_URL.match(u)],
        })
    return {"items": out, "stores": [s["name"] for s in rows.values()],
            "note": "Report every night ~01:30 to both of you; alerts on a 10% drop or back in stock."}


# ------------------------------------------------------------ Basket

SHOP_NAMES = {"yc": "Yerevan City", "parma": "Parma"}
SHOP_DOT = {"yc": "🔴", "parma": "🟢"}


def basket_view(root, kind):
    """The last saved basket run (jobs/grocery_basket.py -> .browser/basket_<kind>.json)."""
    if kind not in ("weekly", "monthly"):
        return None
    path = os.path.join(root, ".browser", f"basket_{kind}.json")
    try:
        with open(path, encoding="utf-8") as f:
            b = json.load(f)
    except (OSError, ValueError):
        return {"empty": True, "kind": kind}
    try:
        when = datetime.fromisoformat(b["run_utc"]).astimezone(YEREVAN).strftime("%d %b %H:%M")
    except (KeyError, ValueError):
        when = ""
    groups = {}
    skipped, unpriced = [], []
    for e in b.get("lines", []):
        if e.get("status") == "ok" and e.get("shop") in SHOP_NAMES:
            groups.setdefault(e["shop"], []).append(e)
        elif e.get("status") == "skipped":
            skipped.append(e["item"])
        else:
            unpriced.append(e["item"])
    t = b.get("totals") or {}
    cmp = b.get("compare") or {}
    out_groups = []
    for shop in ("yc", "parma"):
        es = groups.get(shop)
        if es:
            out_groups.append({
                "shop": shop, "name": SHOP_NAMES[shop], "dot": SHOP_DOT[shop],
                "subtotal": money(t.get(shop)) if t.get(shop) is not None else None,
                "items": [{"item": e["item"], "buy": e.get("buy") or "", "product": e.get("product") or "",
                           "cost": money(e["cost"]) if e.get("cost") is not None else "",
                           "url": e["url"] if SAFE_URL.match(e.get("url") or "") else None}
                          for e in es]})
    compare = None
    if cmp.get("n"):
        compare = (f"{cmp['n']} items at both shops: all {SHOP_DOT['yc']} {money(cmp['yc'])} · "
                   f"all {SHOP_DOT['parma']} {money(cmp['parma'])} · cheapest of each "
                   f"{money(cmp['cheapest'])}")
    return {"empty": False, "kind": kind, "when": when, "total": money(t.get("all") or 0),
            "partial": bool(b.get("partial")), "compare": compare, "groups": out_groups,
            "unpriced": unpriced, "skipped": skipped}


# ------------------------------------------------------------ Travel

_cache = {}
_cache_lock = threading.Lock()
CACHE_S = 300


def _sheet_rows(cfg, tab, now=None):
    """Sheet rows, cached for a few minutes: the screen must not hit Google on every open."""
    from lib import sheets
    now = now or time.time()
    with _cache_lock:
        hit = _cache.get(tab)
        if hit and now - hit[0] < CACHE_S:
            return hit[1]
    rows = sheets.read_all(cfg, tab)
    if rows:                                   # an empty answer is a failed read: don't cache it
        with _cache_lock:
            _cache[tab] = (now, rows)
    return rows


def _short_date(s):
    try:
        d = date.fromisoformat(s)
        return f"{d.day} {d.strftime('%b')}"
    except (TypeError, ValueError):
        return s or ""


def _num(s):
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        return None


def _usd(x):
    return f"{x:,.0f}"


def travel_view(cfg, root=None, rows_fn=None):
    rows_fn = rows_fn or (lambda tab: _sheet_rows(cfg, tab))
    out = {"scan": None, "trips": [], "stays": [], "run_date": None, "unavailable": False}
    try:
        from lib import tasks
        info = tasks.query("travel")
        if info.get("exists"):
            out["scan"] = {"enabled": bool(info.get("enabled")),
                           "next": tasks._short_dt(info.get("next_run")) if info.get("next_run") else None,
                           "last": tasks._short_dt(info.get("last_run")) if info.get("last_run") else None}
    except Exception as e:  # noqa: BLE001  the Windows task query is a nicety, not required
        out["scan_error"] = type(e).__name__
    trips = [r for r in rows_fn("Trips") if len(r) >= 11]
    stays = [r for r in rows_fn("Stays") if len(r) >= 16]
    if not trips and not stays:
        out["unavailable"] = True
        return out
    if trips:
        day = max(r[0] for r in trips)
        out["run_date"] = day
        cur = [r for r in trips if r[0] == day and _num(r[8]) is not None]
        cur.sort(key=lambda r: _num(r[8]))
        for r in cur[:8]:
            wdc = _num(r[9])
            out["trips"].append({
                "route": r[3], "kind": r[2], "out": _short_date(r[4]), "back": _short_date(r[5]),
                "nights": r[6], "pax": r[7], "currency": r[10],
                "total": _usd(_num(r[8])), "club": _usd(wdc) if wdc is not None else None})
    if stays:
        day = max(r[0] for r in stays)
        cur = [r for r in stays if r[0] == day and _num(r[14]) is not None]
        cur.sort(key=lambda r: -_num(r[14]))
        for r in cur[:6]:
            out["stays"].append({
                "city": r[1], "in": _short_date(r[2]), "out": _short_date(r[3]), "nights": r[4],
                "source": r[5], "name": r[6], "rating": r[7], "currency": r[11],
                "total": _usd(_num(r[10])) if _num(r[10]) is not None else r[10],
                "night": _usd(_num(r[9])) if _num(r[9]) is not None else r[9],
                "why": r[13], "url": r[15] if SAFE_URL.match(r[15] or "") else None})
        out["stays_date"] = day
    return out
