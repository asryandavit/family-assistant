"""The family's tickable shopping list: one shared state per household (decision 106).

Davit and Karine tick the same list; a tick records who and when (household-ready,
decision 089: keyed per household, Telegram user ids on ticks -- in a private chat the
user id is the chat id). The Mini App can show and tick the same list through these
functions; the Telegram side is shopping/bot.py.

    load(root, kind)                      the list as a plain dict (JSON-ready)
    tick(root, kind, key, user_id, done)  tick / untick one item (done=None toggles)
    reset(root, kind, user_id)            clear every tick (a new week / month)

What is on the list: every row of plan/meals/basket.md for that list (weekly fresh or
monthly staples, "as needed" rows included), grouped by the aisle in its quality-rules
table, with the shop, amount and product of the last basket run when there is one
(.browser/basket_<kind>.json, written by jobs/grocery_basket.py).

Ticks belong to a period -- the ISO week (Monday to Sunday, Yerevan time) for the weekly
list, the calendar month for staples. A new period starts with nothing ticked; the old
ticks are simply not carried over. State lives in
.browser/shopping/<household>/checklist_<kind>.json, written atomically under a lock
file shared by every process (the listener and the Mini App server).
"""
import hashlib
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from datetime import UTC, datetime

from lib import basket as bk
from lib import ui
from shopping import quality

KINDS = ("weekly", "monthly")
HOUSEHOLD = "family"
MAPPING = os.path.join("plan", "meals", "basket.md")
SHOP_NAMES = {"yc": "Yerevan City", "parma": "Parma"}
# Aisles in walking order; any other aisle named in basket.md comes after, "Other" last.
AISLES = ("Vegetables", "Greens", "Fruit", "Dairy & eggs", "Meat & fish", "Bread",
          "Grains & legumes", "Oils, cans & jars", "Frozen", quality.DEFAULT_AISLE)
LOCK = "write.lock"


class Busy(ValueError):
    """Another process held the list's lock longer than we wait."""


# ------------------------------------------------------------------ files

def _dir(root, household):
    if not re.fullmatch(r"[a-z0-9_-]{1,32}", household or ""):
        raise ValueError(f"household id {household!r} is not a short lowercase name")
    d = os.path.join(root, ".browser", "shopping", household)
    os.makedirs(d, exist_ok=True)
    return d


def _path(root, household, kind):
    if kind not in KINDS:
        raise ValueError(f"list {kind!r} is not weekly or monthly")
    return os.path.join(_dir(root, household), f"checklist_{kind}.json")


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


@contextmanager
def _lock(root, household, wait_s=10.0, stale_s=120.0):
    """O_EXCL lock file around a read-modify-write; a file older than stale_s is a
    leftover from a crash and is removed. Not re-entrant."""
    path = os.path.join(_dir(root, household), LOCK)
    deadline = time.monotonic() + wait_s
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(path) > stale_s:
                    os.remove(path)
                    continue
            except OSError:
                continue
            if time.monotonic() > deadline:
                raise Busy("The list is being changed right now — tap again in a moment.")
            time.sleep(0.05)
    try:
        os.close(fd)
        yield
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ---------------------------------------------------------------- periods

def today_local():
    return ui.now_local().date()


def period_of(kind, day):
    """'2026-W46' for the weekly list, '2026-11' for staples."""
    if kind == "weekly":
        y, w, _ = day.isocalendar()
        return f"{y}-W{w:02d}"
    return f"{day.year}-{day.month:02d}"


def period_label(kind, day):
    if kind == "weekly":
        y, w, _ = day.isocalendar()
        monday = datetime.fromisocalendar(y, w, 1).date()
        sunday = datetime.fromisocalendar(y, w, 7).date()
        return f"week {monday.day} {monday:%b} – {sunday.day} {sunday:%b}"
    return day.strftime("%B %Y")


# ------------------------------------------------------------------ items

def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:24] or "item"


def amount_text(row):
    if row["qty"] is None:
        return row["note"] or "as needed"
    q = format(row["qty"].normalize(), "f")
    unit = {"pack": "pack" if row["qty"] == 1 else "packs"}.get(row["unit"], row["unit"])
    return f"{q} {unit}"


def _aisle_order(aisle):
    return (AISLES.index(aisle) if aisle in AISLES else len(AISLES) - 1.5, aisle)


def items_for(root, kind):
    """[{key, item, aisle, amount, shop, shop_name, buy, product, url, app_url, reason}]
    in aisle order, then list order. Raises ValueError when basket.md is malformed."""
    with open(os.path.join(root, MAPPING), encoding="utf-8") as f:
        md = f.read()
    all_rows = bk.parse_mapping(md)
    rows = [r for r in all_rows if r["list"] == kind]
    rules = quality.parse_rules(md, all_rows)
    last = _read(os.path.join(root, ".browser", f"basket_{kind}.json"), {})
    picked = {ln["item"]: ln for ln in last.get("lines") or [] if ln.get("status") == "ok"}
    out, keys = [], set()
    for n, r in enumerate(rows):
        key = slug(r["item"])
        while key in keys:
            key = f"{key[:21]}-{n}"
        keys.add(key)
        p = picked.get(r["item"]) or {}
        out.append({"key": key, "item": r["item"], "aisle": quality.aisle_of(rules, r["item"]),
                    "amount": amount_text(r), "shop": p.get("shop"),
                    "shop_name": SHOP_NAMES.get(p.get("shop")), "buy": p.get("buy"),
                    "product": p.get("product"), "url": p.get("url"),
                    "app_url": p.get("app_url"), "reason": p.get("reason"), "_n": n})
    out.sort(key=lambda i: (_aisle_order(i["aisle"]), i["_n"]))
    for i in out:
        del i["_n"]
    return out


def version_of(items):
    """Short id of the item list; a button made for another list is refused."""
    return hashlib.sha1("|".join(i["key"] for i in items).encode()).hexdigest()[:6]


# ------------------------------------------------------------------ state

def _fresh(household, kind, period):
    return {"household": household, "kind": kind, "period": period, "ticks": {},
            "messages": {}, "reset": None}


def _state(root, household, kind, day):
    """The stored state for the current period (a new period starts empty, keeping
    only the message ids so both chats' list messages still update)."""
    period = period_of(kind, day)
    st = _read(_path(root, household, kind), None)
    if not isinstance(st, dict) or st.get("period") != period:
        msgs = (st or {}).get("messages") if isinstance(st, dict) else None
        st = _fresh(household, kind, period)
        st["messages"] = msgs or {}
    return st


def _view(root, household, kind, day, st):
    items = items_for(root, kind)
    ticks = st.get("ticks") or {}
    groups, flat = [], []
    for i in items:
        t = ticks.get(i["key"])
        i = dict(i, done=bool(t), by=(t or {}).get("by"), at_utc=(t or {}).get("at_utc"))
        flat.append(i)
        if not groups or groups[-1]["aisle"] != i["aisle"]:
            groups.append({"aisle": i["aisle"], "items": []})
        groups[-1]["items"].append(i)
    last = None
    for i in flat:
        if i["done"] and (last is None or (i["at_utc"] or "") > (last["at_utc"] or "")):
            last = {"item": i["item"], "by": i["by"], "at_utc": i["at_utc"]}
    return {"household": household, "kind": kind, "period": st["period"],
            "period_label": period_label(kind, day), "version": version_of(items),
            "done": sum(1 for i in flat if i["done"]), "total": len(flat),
            "groups": groups, "items": flat, "last": last, "reset": st.get("reset")}


def _now_utc():
    return datetime.now(UTC).isoformat(timespec="seconds")


def _user(user_id):
    v = str(user_id or "").strip()
    if not v.isdigit() or int(v) <= 0:
        raise ValueError("a tick needs the Telegram user id of the person ticking")
    return int(v)


def load(root, kind="weekly", household=HOUSEHOLD, today=None):
    """The list as a dict: {household, kind, period, period_label, version, done,
    total, groups: [{aisle, items}], items: [...], last, reset}. Each item:
    {key, item, aisle, amount, shop, shop_name, buy, product, url, app_url, reason,
    done, by (user id), at_utc}."""
    day = today or today_local()
    return _view(root, household, kind, day, _state(root, household, kind, day))


def tick(root, kind, key, user_id, done=None, household=HOUSEHOLD, today=None):
    """Tick (done=True), untick (False) or toggle (None) one item; returns load().
    ValueError for an item that is not on the list."""
    uid = _user(user_id)
    day = today or today_local()
    keys = {i["key"] for i in items_for(root, kind)}
    if key not in keys:
        raise ValueError("That item is no longer on the list — refresh it.")
    with _lock(root, household):
        st = _state(root, household, kind, day)
        on = (key not in st["ticks"]) if done is None else bool(done)
        if on:
            st["ticks"][key] = {"by": uid, "at_utc": _now_utc()}
        else:
            st["ticks"].pop(key, None)
        _write(_path(root, household, kind), st)
    return _view(root, household, kind, day, st)


def reset(root, kind, user_id, household=HOUSEHOLD, today=None):
    """Clear every tick of the current period; records who did it. Returns load()."""
    uid = _user(user_id)
    day = today or today_local()
    with _lock(root, household):
        st = _state(root, household, kind, day)
        st["ticks"] = {}
        st["reset"] = {"by": uid, "at_utc": _now_utc()}
        _write(_path(root, household, kind), st)
    return _view(root, household, kind, day, st)


def remember_message(root, kind, chat_id, message_id, household=HOUSEHOLD):
    """The latest list message in a chat, so a tick elsewhere can update it too."""
    if not message_id:
        return
    with _lock(root, household):
        st = _state(root, household, kind, today_local())
        st.setdefault("messages", {})[str(chat_id)] = int(message_id)
        _write(_path(root, household, kind), st)


def messages(root, kind, household=HOUSEHOLD):
    """{chat id: message id} of the list messages to keep current."""
    st = _read(_path(root, household, kind), {})
    return dict((st or {}).get("messages") or {})
