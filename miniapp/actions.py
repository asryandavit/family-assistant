"""What the Mini App forms and buttons do (decision 098). Called by miniapp/server.py.

Two kinds of action:
  * run a chat command: the text is composed from validated fields, checked with the same
    parsers the chat uses (so the form can show the chat's own error), and queued for the
    listener (miniapp/inbox.py), which runs it from the person's chat with its validation,
    one-job-at-a-time runner and reply;
  * edit the Market watch list directly, through the same `market.bot._mutate` (write lock,
    Sheet merge) that /watch uses.
Every function returns (ok, message) with a human sentence; the server adds no logic.
"""
import json
import os
import re

from miniapp import inbox, screens

ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,20}$")
PRICE_RE = re.compile(r"^[\w][\w\s%.,'\"&+\-]{1,39}$")      # same shape the chat accepts
BASKET_KINDS = ("weekly", "monthly", "all")
SITE_WORDS = ("pinduoduo", "taobao", "1688")
JOBS = ("basket", "scan", "digest", "market", "flights", "stays", "price", "china")
SENT = "Sent to the bot. {what}The answer arrives in your chat."
BOT_DOWN = "The bot is not running on the PC — nothing was sent."
DESC_HELP = "Describe the item in 3–200 characters, e.g. GaN charger 65W EU plug."


def _err(e):
    return screens.plain(str(e))


def compose(job, args, cfg):
    """(command text, None) or (None, error sentence) for a run request. The text is also
    checked against the inbox's own limit, so a request the inbox would refuse is refused
    here with a clear sentence (decision 102)."""
    text, err = _compose(job, args, cfg)
    if text and len(text) - len(job) - 2 > inbox.MAX_TEXT:
        return None, DESC_HELP if job == "china" else (
            f"That is too long — keep it under {inbox.MAX_TEXT} characters.")
    return text, err


def _compose(job, args, cfg):
    args = " ".join(str(args or "").split())
    if job not in JOBS:
        return None, "Unknown action."
    if job == "basket":
        if args not in BASKET_KINDS:
            return None, "Choose weekly, monthly or all."
        return f"/basket {args}", None
    if job in ("scan", "digest"):
        return f"/{job}", None
    if job == "market":
        return "/watch check", None
    if job == "price":
        q = args.lstrip("-").strip()
        if not q or not PRICE_RE.match(q):
            return None, "Type a product name, up to 40 letters — e.g. lentils."
        return f"/price {q}", None
    if job == "flights":
        from lib import flights
        text = f"/flights {args}"
        q = flights.parse_command(text, cfg)
        return (None, _err(q["error"])) if "error" in q else (text, None)
    if job == "stays":
        from lib import parse_cmd
        text = f"/stays {args}"
        q = parse_cmd.parse(text, cfg)
        return (None, _err(q["error"])) if "error" in q else (text, None)
    # china: "<description>" or "only <site> <description>"
    from china import bot as cbot
    # Read "only <site>" exactly as china.bot.handle does, and keep the chat's command words
    # ("last", "cancel") out: this form sends descriptions, and "/china cancel" would drop the
    # person's waiting searches while the page says "Sent" (review, decision 099).
    m = re.match(r"only\s+(\S+)\s*(.*)$", args, re.IGNORECASE)
    desc = m.group(2).strip() if m else args
    if m and m.group(1).lower() not in cbot.SITES:
        return None, "Which site? Pinduoduo, Taobao or 1688."
    if args.lower() in ("last", "cancel") or not cbot.DESC_RE.match(desc):
        return None, DESC_HELP
    return f"/china {args}", None


def run(root, cfg, chat_id, job, args):
    text, err = compose(job, args, cfg)
    if err:
        return False, err
    if not inbox.listener_alive(root):
        return False, BOT_DOWN
    if not inbox.put(root, chat_id, text):
        return False, "That request was not accepted."
    what = {"china": "I'll post progress there. ", "basket": "", "price": ""}.get(job, "")
    return True, SENT.format(what=what)


# ------------------------------------------------------------------ China status

def china_status(root, chat_id):
    """{"running": bool, "mine_running": bool, "waiting": n of your searches waiting}."""
    from china import queue
    info = queue.running(root)
    waiting = 0
    d = queue.qdir(root)
    for name in queue.pending(root):
        try:
            with open(os.path.join(d, name), encoding="utf-8") as f:
                job = json.load(f)
        except (OSError, ValueError):
            continue
        if str(job.get("chat_id")) == str(chat_id):
            waiting += 1
    return {"running": bool(info), "waiting": waiting}


# ------------------------------------------------------------------ Market watch edits

def market_action(cfg, root, chat_id, action, item_id):
    """Mark an active watched item bought or removed (by id, so a changed list can't make it
    hit another item)."""
    from market import bot
    if action not in ("bought", "remove") or not ID_RE.match(str(item_id)):
        return False, "Bad request."
    status = "bought" if action == "bought" else "removed"

    def fn(items):
        it = next((i for i in items if i.get("id") == item_id
                   and i.get("status", "active") == "active"), None)
        if not it:
            return "That item is no longer on the list."
        it["status"] = status
        icon, verb = ("✅", "marked bought") if status == "bought" else ("🗑", "removed")
        return f"{icon} <b>{bot.esc(it['name'])}</b> {verb}."
    try:
        msg = bot._mutate(cfg, root, fn)
    except ValueError as e:                       # state.Busy: another change is saving
        return False, _err(e)
    return msg.startswith(("✅", "🗑")), screens.plain(msg)


def market_add(cfg, root, chat_id, name, link, weight=""):
    """Add a watched item: the chat dialog's checks, then bot._finish (the same message)."""
    from market import bot, state
    from market import stores as stores_mod
    name = " ".join(str(name or "").split())
    if not 2 <= len(name) <= 80:
        return False, "A name of 2 to 80 characters, please."
    links = stores_mod.find_links(str(link or ""))
    if not links:
        return False, "I need a link starting with https://"
    rows = stores_mod.load()
    bad = [u for u in links if not stores_mod.store_for_url(u, rows)]
    if bad:
        names = ", ".join(s["name"] for s in rows.values())
        return False, f"I don't watch that store yet ({stores_mod.host_of(bad[0])}). Stores: {names}."
    keys = [stores_mod.store_for_url(u, rows)["key"] for u in links]
    if len(set(keys)) != len(keys):
        return False, "One link per store, please (exact item)."
    w, size = None, None
    if str(weight or "").strip():
        try:
            w, size = state.parse_weight_and_size(str(weight))
        except ValueError as e:
            return False, _err(e)
    draft = {"name": name, "links": links, "qty": 1, "weight_kg": w, "size_cm": size}
    try:
        msg = bot._finish(cfg, root, chat_id, draft)
    except ValueError as e:
        return False, _err(e)
    return msg.startswith("✅"), screens.plain(msg)
