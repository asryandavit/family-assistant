"""The tick list in Telegram (decision 106, docs/TELEGRAM_UX.md §5g).

    /list            this week's list          (also 🛒 Shopping → ✅ Tick list)
    /list monthly    the monthly staples

One message per chat: the list grouped by aisle (✅ ticked, ☐ still to buy; the item
name links to the product the basket picked) and a button per item. A tap ticks or
unticks the item for the whole household and edits the list message in BOTH chats, so
Davit and Karine always see the same state. The Shopping list Sheet's tick boxes follow
(one way: bot → Sheet), in the background.

Callback data (only short codes travel):
    gl:o:<w|m>              send the list as a new message
    gl:v:<w|m>              refresh this message
    gl:t:<w|m>:<ver>:<n>    tick / untick item n of list version ver
    gl:r:<w|m>              ask before clearing every tick
    gl:R:<w|m>              clear every tick (a new week / month)
"""
import json
import os
import threading
from datetime import datetime

import requests

from lib import telegram, ui
from lib.fmt_grocery import SHOP_DOT
from lib.telegram import esc
from shopping import checklist

CODES = {"w": "weekly", "m": "monthly"}
CODE = {v: k for k, v in CODES.items()}
TITLE = {"weekly": "this week", "monthly": "monthly staples"}
LIST_NAME = {"weekly": "this week's list", "monthly": "the monthly staples list"}
NEW = {"weekly": "♻️ New week", "monthly": "♻️ New month"}
OTHER = {"weekly": ("\U0001f4e6 Staples", "gl:o:m"), "monthly": ("\U0001f96c This week", "gl:o:w")}
BUTTON_CHARS = 18
TICKED, OPEN = "✅", "☐"


# ------------------------------------------------------------------ people

def names(root, env=None):
    """{user id: first name} from config_miniapp.json `people` (env var -> name), the
    same source as the Mini App's people list. {} when unreadable."""
    env = os.environ if env is None else env
    try:
        with open(os.path.join(root, "config_miniapp.json"), encoding="utf-8") as f:
            people = json.load(f).get("people") or []
    except (OSError, ValueError):
        return {}
    out = {}
    for p in people:
        v = str(env.get(p.get("env") or "", "") or "").strip()
        if v.isdigit() and int(v) not in out:
            out[int(v)] = p.get("name") or "someone"
    return out


def who(root, user_id, env=None):
    return names(root, env).get(user_id, "someone") if user_id else "someone"


# ------------------------------------------------------------------ render

def _time_local(at_utc):
    try:
        return datetime.fromisoformat(at_utc).astimezone(ui.YEREVAN).strftime("%H:%M")
    except (TypeError, ValueError):
        return ""


def _line(i):
    name = esc(i["item"])
    if i.get("url"):
        name = '<a href="{}">{}</a>'.format(esc(i["url"]), name)
    if i["done"]:
        name = f"<s>{name}</s>"
    what = esc(i["buy"] or i["amount"])
    shop = (" " + SHOP_DOT.get(i["shop"], "")) if i.get("shop") else ""
    return "{} {} · {}{}".format(TICKED if i["done"] else OPEN, name, what, shop)


def render(view, root, env=None):
    """(text, buttons) for a list view from checklist.load()."""
    kind = view["kind"]
    head = ui.header("✅", "Shopping list", TITLE[kind], view["period_label"])
    status = f"<b>{view['done']} of {view['total']}</b> in the cart"
    if view["done"] == view["total"] and view["total"]:
        status = f"<b>All {view['total']} in the cart</b> \U0001f389"
    last = view.get("last")
    if last:
        status += " · last: {} ticked {} {}".format(esc(who(root, last["by"], env)), esc(last["item"]),
                                                    _time_local(last["at_utc"]))
    body = [status]
    for g in view["groups"]:
        body.append("")
        body.append("<b>{}</b>".format(esc(g["aisle"])))
        body += [_line(i) for i in g["items"]]
    footer = ("<i>Tap an item below to tick it — you both see the same list. "
              "\U0001f534 Yerevan City · \U0001f7e2 Parma, from the last \U0001f9fa Basket.</i>")
    text = ui.page(head, body, "", footer)

    c, ver = CODE[kind], view["version"]
    btns = [((TICKED if i["done"] else OPEN) + " " + i["item"][:BUTTON_CHARS],
             f"gl:t:{c}:{ver}:{n}") for n, i in enumerate(view["items"])]
    rows = [btns[n:n + 2] for n in range(0, len(btns), 2)]
    rows.append([("\U0001f504 Refresh", f"gl:v:{c}"), OTHER[kind]])
    rows.append([(NEW[kind], f"gl:r:{c}")])
    return text, rows


def render_confirm(view):
    kind, c = view["kind"], CODE[view["kind"]]
    head = ui.header("♻️", "Shopping list", TITLE[kind])
    name, n = LIST_NAME[kind], view["done"]
    if n == 0:
        return (head + f"\n\nNothing is ticked on {name} yet, so there is nothing to clear.",
                [[("◀️ Back to the list", f"gl:v:{c}")]])
    what = "the 1 tick" if n == 1 else f"all {n} ticks"
    text = head + f"\n\nClear {what} on {name}? The items stay; only the ticks go."
    return text, [[("Yes, clear the ticks", f"gl:R:{c}"), ("Cancel", f"gl:v:{c}")]]


# --------------------------------------------------------------- Telegram

class Tg:
    """The two Telegram calls the list needs; tests pass a fake."""

    def __init__(self, cfg):
        self.cfg = cfg

    def send(self, chat_id, text, buttons):
        """Send and return the new message id (None when it failed)."""
        tok, _ = telegram._creds(self.cfg)
        if not tok:
            print("Telegram env not set; skipping list:", text[:60])
            return None
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                   "disable_web_page_preview": True, "disable_notification": True,
                   "reply_markup": telegram.reply_markup(buttons)}
        try:
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                              data=payload, timeout=20).json()
            return (r.get("result") or {}).get("message_id") if r.get("ok") else None
        except (requests.RequestException, ValueError) as e:
            print("Telegram list send failed:", e)
            return None

    def edit(self, chat_id, message_id, text, buttons):
        telegram.edit_html(self.cfg, chat_id, message_id, text, buttons)


def _sync_all(cfg, root, view, tg, skip=None, env=None):
    """Edit every remembered list message (both chats) to show `view`."""
    text, btns = render(view, root, env)
    for chat, mid in checklist.messages(root, view["kind"]).items():
        if skip and (str(chat), int(mid)) == (str(skip[0]), int(skip[1] or 0)):
            continue
        tg.edit(chat, mid, text, btns)


def send_list(cfg, root, kind, chat_id, tg=None, env=None):
    tg = tg or Tg(cfg)
    view = checklist.load(root, kind)
    text, btns = render(view, root, env)
    mid = tg.send(chat_id, text, btns)
    checklist.remember_message(root, kind, chat_id, mid)


def refresh_messages(cfg, root, kind, tg=None, env=None):
    """Bring every chat's list message up to date -- for the Mini App after it ticks."""
    _sync_all(cfg, root, checklist.load(root, kind), tg or Tg(cfg), env=env)


def handle(cfg, root, text, chat_id, tg=None, env=None):
    """/list [weekly|monthly] -> sends the list; returns an error sentence or None."""
    words = [w.lower() for w in (text or "").split()[1:]]
    kind = words[0] if words else "weekly"
    kind = {"week": "weekly", "staples": "monthly", "month": "monthly"}.get(kind, kind)
    if len(words) > 1 or kind not in checklist.KINDS:
        return "Use <code>/list</code> or <code>/list monthly</code>."
    try:
        return send_list(cfg, root, kind, chat_id, tg, env)
    except ValueError as e:
        return f"⚠️ The list couldn't be read: {esc(str(e))}"


def callback(cfg, root, data, chat_id, message_id=None, tg=None, mirror=None, env=None):
    """A gl:… button. The person ticking is the chat's user (private chats: user id ==
    chat id). Returns a sentence to send back, or None when the message was edited."""
    tg = tg or Tg(cfg)
    mirror = mirror or mirror_to_sheet
    parts = (data or "").split(":")
    if len(parts) < 3 or parts[0] != "gl" or parts[2] not in CODES:
        return "Unrecognised button."
    act, kind = parts[1], CODES[parts[2]]
    try:
        if act == "o" and len(parts) == 3:
            return send_list(cfg, root, kind, chat_id, tg, env)
        if act in ("v", "r") and len(parts) == 3:
            view = checklist.load(root, kind)
            text, btns = render(view, root, env) if act == "v" else render_confirm(view)
            _show(tg, root, kind, chat_id, message_id, text, btns)
            return None
        if act == "R" and len(parts) == 3:
            view = checklist.reset(root, kind, chat_id)
            _after_change(cfg, root, view, tg, chat_id, message_id, env)
            mirror(cfg, root, kind, {i["item"]: False for i in view["items"]})
            return None
        if act == "t" and len(parts) == 5 and parts[4].isdigit():
            view = checklist.load(root, kind)
            n = int(parts[4])
            if parts[3] != view["version"] or n >= len(view["items"]):
                text, btns = render(view, root, env)
                _show(tg, root, kind, chat_id, message_id, text, btns)
                return "The list changed since that message — here it is again; tap the item once more."
            item = view["items"][n]
            view = checklist.tick(root, kind, item["key"], chat_id)
            _after_change(cfg, root, view, tg, chat_id, message_id, env)
            done = next(i["done"] for i in view["items"] if i["key"] == item["key"])
            mirror(cfg, root, kind, {item["item"]: done})
            return None
    except ValueError as e:                      # Busy, a malformed basket.md, a stale item
        return f"⚠️ {esc(str(e))}"
    return "Unrecognised button."


def _show(tg, root, kind, chat_id, message_id, text, btns):
    if message_id:
        tg.edit(chat_id, message_id, text, btns)
        checklist.remember_message(root, kind, chat_id, message_id)
    else:
        mid = tg.send(chat_id, text, btns)
        checklist.remember_message(root, kind, chat_id, mid)


def _after_change(cfg, root, view, tg, chat_id, message_id, env):
    text, btns = render(view, root, env)
    _show(tg, root, view["kind"], chat_id, message_id, text, btns)
    _sync_all(cfg, root, view, tg, skip=(chat_id, message_id), env=env)


# ------------------------------------------------------------------ Sheet

_warned = {"day": None}


def sheet_updates(col_b, changes):
    """[{range, values}] setting column A to True/False on the rows whose Item (column
    B) is in `changes` -- the Shopping list tab layout of lib/fmt_basket.sheet_rows."""
    return [{"range": f"A{n + 1}", "values": [[bool(changes[v])]]}
            for n, v in enumerate(col_b) if v in changes]


def _mirror(cfg, root, kind, changes):
    from lib import fmt_basket, sheets_checklist
    from lib.sheets import _retry
    try:
        with open(os.path.join(root, "config_coach.json"), encoding="utf-8") as f:
            sheet_id = json.load(f).get("shopping_sheet_id")
    except (OSError, ValueError):
        sheet_id = None
    if not sheet_id:
        return
    try:
        ws = _retry(sheets_checklist._open(cfg, sheet_id).worksheet, fmt_basket.TABS[kind])
        ups = sheet_updates(_retry(ws.col_values, 2), changes)
        if ups:
            _retry(ws.batch_update, ups, value_input_option="USER_ENTERED")
    except Exception as e:  # noqa: BLE001  a Sheet outage must not break ticking
        print("shopping list sheet mirror failed:", e)
        day = checklist.today_local().isoformat()
        if _warned["day"] != day:                # tell the owner once a day, not per tap
            _warned["day"] = day
            telegram.notify(cfg, "⚠️ SYSTEM: Shopping list Sheet not updated from the tick "
                                 f"list ({str(e)[:120]}). Ticks are kept in the bot.")


def mirror_to_sheet(cfg, root, kind, changes):
    """Set the Sheet's tick boxes for these items in the background."""
    threading.Thread(target=_mirror, args=(cfg, root, kind, changes), daemon=True).start()
