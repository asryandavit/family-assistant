"""The watch list's local files and the typed parsers for what people type.

Three files under .browser/market_data/, each with ONE writer so the listener and the
nightly job never overwrite each other (written atomically: temp file + os.replace):

    items.json         the list (listener /watch commands; Sheet edits merged in by the job)
    owner_prices.json  prices typed with /watch price (listener)
    runtime.json       last read offers, blocked-store streaks, daily history (nightly job)

The "Watch list" Google Sheet mirrors items/offers/history (market/sheet.py) and is where
the list can be edited from a phone.

Every value typed by a person passes a parse function first (CLAUDE.md §3 spirit):
decimal comma accepted, units stripped, range-checked, rejected with a human sentence.
"""
import json
import os
import re
import tempfile
from datetime import datetime, timezone

MAX_ITEMS = 20
STATUSES = ("active", "bought", "removed")


def data_dir(root):
    d = os.path.join(root, ".browser", "market_data")
    os.makedirs(d, exist_ok=True)
    return d


def _path(root, name):
    return os.path.join(data_dir(root), name)


def read_json(root, name, default):
    try:
        with open(_path(root, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(root, name, data):
    d = data_dir(root)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, default=str)
    os.replace(tmp, _path(root, name))


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ items

def load_items(root):
    return read_json(root, "items.json", [])


def save_items(root, items):
    write_json(root, "items.json", items)


def active(items):
    return [it for it in items if it.get("status", "active") == "active"]


def next_id(items):
    nums = [int(it["id"]) for it in items if str(it.get("id", "")).isdigit()]
    return str(max(nums, default=0) + 1)


def by_number(items, n):
    """The n-th ACTIVE item as shown in /watch (1-based), or by its id."""
    act = active(items)
    try:
        k = int(n)
    except (TypeError, ValueError):
        return None
    if 1 <= k <= len(act):
        return act[k - 1]
    return next((it for it in items if it.get("id") == str(k)), None)


def new_item(items, name, links, qty=1, weight_kg=None, size_cm=None, added_by=""):
    if len(active(items)) >= MAX_ITEMS:
        raise ValueError("The list is full (%d items). Mark one bought or remove one first." % MAX_ITEMS)
    return {"id": next_id(items), "name": name, "mode": "exact", "links": links, "qty": qty,
            "weight_kg": weight_kg, "size_cm": size_cm, "size_from": "owner" if weight_kg else "",
            "added_by": added_by, "status": "active", "notes": "", "added_utc": now_utc()}


# ------------------------------------------------------------ owner prices

def load_owner_prices(root):
    return read_json(root, "owner_prices.json", {})


def set_owner_price(root, item_id, store_key, price, currency, day_local):
    d = load_owner_prices(root)
    d["%s|%s" % (item_id, store_key)] = {"price": price, "currency": currency,
                                         "date_local": day_local.isoformat(), "set_utc": now_utc()}
    write_json(root, "owner_prices.json", d)


# ---------------------------------------------------------------- runtime

def load_runtime(root):
    rt = read_json(root, "runtime.json", {})
    rt.setdefault("last", {})
    rt.setdefault("blocked", {})
    rt.setdefault("history", [])
    return rt


def save_runtime(root, rt):
    write_json(root, "runtime.json", rt)


# ------------------------------------------------------------ typed input

def _num(s):
    s = s.strip().replace(",", ".")
    return float(s)


def parse_weight(text):
    """'2.4', '2,4 kg', '2400 g', '5 lb' -> kg. Raises ValueError with a sentence."""
    t = (text or "").strip().lower()
    m = re.fullmatch(r"([\d]+(?:[.,]\d+)?)\s*(kg|кг|g|gr|lb|lbs)?", t)
    if not m:
        raise ValueError("I need a weight like 2.4 kg or 800 g.")
    v = _num(m.group(1))
    unit = m.group(2) or "kg"
    if unit in ("g", "gr"):
        v /= 1000
    elif unit in ("lb", "lbs"):
        v *= 0.45359237
    if not 0.01 <= v <= 100:
        raise ValueError("A parcel weight should be between 10 g and 100 kg.")
    return round(v, 3)


def parse_size(text):
    """'40x30x20', '40 × 30 × 20 cm', '16x12x8 in' -> (L, W, H) cm. Raises ValueError."""
    t = (text or "").strip().lower().replace("×", "x").replace("*", "x")
    m = re.fullmatch(r"([\d.,]+)\s*x\s*([\d.,]+)\s*x\s*([\d.,]+)\s*(cm|mm|in|inch|inches)?", t)
    if not m:
        raise ValueError("I need a size like 40x30x20 (cm).")
    vals = [_num(x) for x in m.group(1, 2, 3)]
    unit = m.group(4) or "cm"
    if unit == "mm":
        vals = [v / 10 for v in vals]
    elif unit.startswith("in"):
        vals = [v * 2.54 for v in vals]
    if not all(1 <= v <= 300 for v in vals):
        raise ValueError("Each side should be between 1 and 300 cm.")
    return [round(v, 1) for v in vals]


def parse_weight_and_size(text):
    """'2.4 kg 40x30x20' / '2.4' / '40x30x20 1.2kg' -> (kg or None, size or None)."""
    t = (text or "").strip()
    size = None
    m = re.search(r"[\d.,]+\s*[x×*]\s*[\d.,]+\s*[x×*]\s*[\d.,]+\s*(?:cm|mm|in|inch|inches)?", t, re.I)
    if m:
        size = parse_size(m.group(0))
        t = (t[:m.start()] + " " + t[m.end():]).strip()
    weight = parse_weight(t) if t else None
    if weight is None and size is None:
        raise ValueError("I need a weight like 2.4 kg, a size like 40x30x20, or both.")
    return weight, size


def parse_qty(text):
    t = (text or "").strip()
    if not re.fullmatch(r"\d{1,2}", t) or not 1 <= int(t) <= 20:
        raise ValueError("Quantity should be a whole number from 1 to 20.")
    return int(t)


def parse_amount(text):
    """'79.99', '9 890', '144,95', '$79.99', '9890₽' -> (amount, currency symbol code or None)."""
    from market.readers import parse_money
    amount, cur = parse_money(text or "")
    if amount is None or not 0 < amount < 100_000_000:
        raise ValueError("I need a price like 79.99 or 9890.")
    return amount, cur
