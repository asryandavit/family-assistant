"""Telegram side of Market watch: /watch commands, the add dialog, the 🌍 Market section
(docs/TELEGRAM_UX.md §5d). Called by listener.py; sends its own messages to the chat that
asked (lib/telegram.send_html with chat_id). No page is read here: reading happens in the
nightly job (or /watch check, which the listener launches as the "market" job).

    /watch                      the list, with Check now / Add / Sheet buttons
    /watch add                  dialog: name -> link(s) -> qty -> weight and size
    /watch bought <n>           mark item n bought (it leaves the list)
    /watch remove <n>           remove item n
    /watch price <n> <amount> [store]   an owner's price for a store the bot can't read
    /watch weight <n> <kg> [LxWxH]      set weight (and box size in cm)
    /watch check                run the watch now (listener job "market")

Dialog prompts are Telegram force-replies carrying PROMPT_MARK; the listener turns an
answer to one into "/watch answer <text>". The dialog state is one small file per chat.
"""
import os

from lib import telegram, ui
from lib.telegram import esc
from market import sheet, state, stores as stores_mod

PROMPT_MARK = "Market · add"
CHINESE_TEMPLATE = "您好，请问这个商品包装后的重量（公斤）和尺寸（长×宽×高，厘米）是多少？谢谢！"
STEPS = ("name", "links", "qty", "size")
SKIP = ("skip", "i don't know", "dont know", "don't know", "no", "-")

HELP = ("🌍 <b>Market watch</b>\n"
        "/watch — the list\n"
        "/watch add — add an item (asks name, link, quantity, weight)\n"
        "/watch bought &lt;n&gt; · /watch remove &lt;n&gt;\n"
        "/watch price &lt;n&gt; &lt;amount&gt; [store] — your price when a store blocks the bot\n"
        "/watch weight &lt;n&gt; &lt;kg&gt; [LxWxH cm]\n"
        "/watch check — read all prices now (~1 min per store)")


def market_cfg(root):
    import json
    try:
        with open(os.path.join(root, "config_market.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def sheet_id(root):
    return market_cfg(root).get("watch_sheet_id")


def who(cfg, chat_id):
    chats = telegram.allowed_chats(cfg) if cfg.get("telegram") else []
    if chat_id and chats and str(chat_id) == chats[0]:
        return "Davit"
    return "Karine" if chat_id and str(chat_id) in chats else ""


# ------------------------------------------------------------------- list

def _best_today(root):
    """{item_id: (best_total_amd, store, route, date_local)} from the latest history rows."""
    out = {}
    for h in state.load_runtime(root)["history"]:
        out[h["item_id"]] = (h["best_total_amd"], h["store"], h["route"], h["date_local"])
    return out


def list_view(root):
    items = state.active(state.load_items(root))
    best = _best_today(root)
    store_rows = stores_mod.load()
    head = ui.header("\U0001f30d", "Market watch", "%d item%s" % (len(items), "" if len(items) == 1 else "s"))
    body = []
    for n, it in enumerate(items, start=1):
        names = []
        for u in it.get("links", []):
            s = stores_mod.store_for_url(u, store_rows)
            names.append(s["name"] if s else "?")
        line = "%d. <b>%s</b> · %s" % (n, esc(it["name"]), esc(", ".join(names)))
        if it["id"] in best:
            total, _, route, day = best[it["id"]]
            line += " · best %s AMD (%s, %s)" % ("{:,.0f}".format(total), esc(route), day[5:].replace("-", "."))
        if not it.get("weight_kg"):
            line += " · ⚖️ weight needed"
        body.append(line)
    if not items:
        body.append("Nothing watched yet. Tap ➕ Add or type /watch add.")
    body.append("<i>Report every night ~01:30 to both of you; alerts on a 10% drop or back in stock.</i>")
    rows = [[("\U0001f504 Check now", "cmd:market"), ("➕ Add", "mk:add")]]
    sid = sheet_id(root)
    if sid:
        rows.append([("\U0001f4c4 Watch list Sheet", "https://docs.google.com/spreadsheets/d/%s/edit" % sid)])
    return ui.page(head, body), rows


def section(root):
    """(text, rows) for Home -> 🌍 Market (ui.section adds ⬅️ Home)."""
    return list_view(root)


# ------------------------------------------------------------- list edits

def _mutate(cfg, root, fn):
    """Merge phone edits from the Sheet, apply fn(items) -> message, save, rewrite the Sheet."""
    sid = sheet_id(root)
    items, problems = (sheet.sync_items(cfg, root, sid, write=False) if sid
                       else (state.load_items(root), []))
    msg = fn(items)
    state.save_items(root, items)
    if sid:
        try:
            from lib import sheets_checklist
            sheets_checklist.write_tab(cfg, sid, "items", sheet.item_rows(items), bold_rows=(0,))
        except Exception as e:
            msg += "\n<i>⚠️ The Sheet wasn't updated (%s); the bot's list is.</i>" % esc(str(e)[:80])
    if problems:
        msg += "\n<i>⚠️ Sheet: %s</i>" % esc("; ".join(problems[:3]))
    return msg


def _set_status(cfg, root, n, status):
    def fn(items):
        it = state.by_number(items, n)
        if not it or it.get("status") != "active":
            return "No active item %s — /watch shows the numbers." % esc(n)
        it["status"] = status
        return "%s <b>%s</b> %s." % ("✅" if status == "bought" else "\U0001f5d1", esc(it["name"]),
                                    "marked bought" if status == "bought" else "removed")
    return _mutate(cfg, root, fn)


def _set_weight(cfg, root, args):
    if len(args) < 2:
        return "Use <code>/watch weight 2 2.4 40x30x20</code> (item, kg, optional size in cm)."
    n, rest = args[0], " ".join(args[1:])
    try:
        kg, size = state.parse_weight_and_size(rest)
    except ValueError as e:
        return esc(str(e))

    def fn(items):
        it = state.by_number(items, n)
        if not it:
            return "No item %s — /watch shows the numbers." % esc(n)
        if kg is not None:
            it["weight_kg"] = kg
        if size is not None:
            it["size_cm"] = size
        it["size_from"] = "owner"
        return "⚖️ <b>%s</b>: %s%s." % (esc(it["name"]), "%g kg" % it["weight_kg"] if it.get("weight_kg") else "no weight",
                                        " · %s cm" % sheet.size_text(it["size_cm"]) if it.get("size_cm") else "")
    return _mutate(cfg, root, fn)


def _owner_price(cfg, root, args, today):
    if len(args) < 2:
        return "Use <code>/watch price 2 9890</code> (item, amount[, store]) — the store's own currency."
    items = state.load_items(root)
    it = state.by_number(items, args[0])
    if not it:
        return "No item %s — /watch shows the numbers." % esc(args[0])
    store_rows = stores_mod.load()
    linked = [s for s in (stores_mod.store_for_url(u, store_rows) for u in it.get("links", [])) if s]
    amount_text, store_key = " ".join(args[1:]), None
    if len(args) >= 3 and args[-1].lower() in store_rows:
        store_key, amount_text = args[-1].lower(), " ".join(args[1:-1])
    if store_key is None:
        if len(linked) != 1:
            return ("<b>%s</b> has links at %s — add the store: <code>/watch price %s %s %s</code>"
                    % (esc(it["name"]), esc(", ".join(s["key"] for s in linked)), esc(args[0]),
                       esc(args[1]), esc(linked[0]["key"] if linked else "store")))
        store_key = linked[0]["key"]
    st = store_rows[store_key]
    if st not in linked:
        return "<b>%s</b> has no %s link." % (esc(it["name"]), esc(st["name"]))
    try:
        amount, cur = state.parse_amount(amount_text)
    except ValueError as e:
        return esc(str(e))
    if cur and cur != st["currency"]:
        return "%s prices are in %s — type the amount in %s." % (esc(st["name"]), st["currency"], st["currency"])
    state.set_owner_price(root, it["id"], store_key, amount, st["currency"], today)
    from market.report import money
    return ("✍️ <b>%s</b> at %s: %s (owner, %s). Used in tonight's report until the store is read again."
            % (esc(it["name"]), esc(st["name"]), money(amount, st["currency"]), today.strftime("%d %b")))


# ------------------------------------------------------------------ dialog

def _dialog_path(root, chat_id):
    return os.path.join(state.data_dir(root), "dialog_%s.json" % "".join(c for c in str(chat_id) if c.isdigit() or c == "-"))


def _dialog(root, chat_id):
    import json
    try:
        with open(_dialog_path(root, chat_id), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _save_dialog(root, chat_id, d):
    import json
    p = _dialog_path(root, chat_id)
    if d is None:
        try:
            os.remove(p)
        except OSError:
            pass
        return
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)


PROMPTS = {
    "name": ("1/4 · What is it? A short name.", "Airfryer Philips HD9252"),
    "links": ("2/4 · Paste the product link(s), one per line.\nStores: %s.", "https://www.amazon.de/dp/…"),
    "qty": ("3/4 · How many? (1 if just one)", "1"),
    "size": ("4/4 · Weight and box size? e.g. <code>2.4 kg 40x30x20</code> — or <code>skip</code>: "
             "the bot then takes them from the Amazon page when it shows them.", "2.4 kg 40x30x20"),
}


def _prompt(cfg, chat_id, step):
    text, placeholder = PROMPTS[step]
    if step == "links":
        text = text % ", ".join(s["name"] for s in stores_mod.load().values())
    telegram.send_html(cfg, "\U0001f30d <b>%s</b>\n%s" % (PROMPT_MARK, text), silent=True,
                       force_reply=placeholder, chat_id=chat_id)


def start_add(cfg, root, chat_id):
    if len(state.active(state.load_items(root))) >= state.MAX_ITEMS:
        return "The list is full (%d items). Mark one bought or remove one first." % state.MAX_ITEMS
    _save_dialog(root, chat_id, {"step": "name", "draft": {}})
    _prompt(cfg, chat_id, "name")
    return None


def answer(cfg, root, chat_id, text):
    d = _dialog(root, chat_id)
    if not d:
        return "That prompt has expired — start again with /watch add."
    t = (text or "").strip()
    if t.lower() in ("stop", "cancel", "/cancel"):
        _save_dialog(root, chat_id, None)
        return "Stopped — nothing was added."
    step, draft = d["step"], d["draft"]
    try:
        if step == "name":
            if not 2 <= len(t) <= 80:
                raise ValueError("A name of 2 to 80 characters, please.")
            draft["name"] = t
            nxt = "links"
        elif step == "links":
            links = stores_mod.find_links(t)
            if not links:
                raise ValueError("I need a link starting with https://")
            store_rows = stores_mod.load()
            bad = [u for u in links if not stores_mod.store_for_url(u, store_rows)]
            if bad:
                raise ValueError("I don't watch that store yet (%s). Stores: %s."
                                 % (stores_mod.host_of(bad[0]), ", ".join(s["name"] for s in store_rows.values())))
            keys = [stores_mod.store_for_url(u, store_rows)["key"] for u in links]
            if len(set(keys)) != len(keys):
                raise ValueError("One link per store, please (exact item).")
            draft["links"] = links
            nxt = "qty"
        elif step == "qty":
            draft["qty"] = state.parse_qty(t or "1")
            nxt = "size"
        else:
            if t.lower() in SKIP:
                draft["weight_kg"], draft["size_cm"] = None, None
            else:
                draft["weight_kg"], draft["size_cm"] = state.parse_weight_and_size(t)
            nxt = None
    except ValueError as e:
        _prompt(cfg, chat_id, step)
        return "⚠️ %s" % esc(str(e))
    if nxt:
        _save_dialog(root, chat_id, {"step": nxt, "draft": draft})
        _prompt(cfg, chat_id, nxt)
        return None
    _save_dialog(root, chat_id, None)
    return _finish(cfg, root, chat_id, draft)


def _finish(cfg, root, chat_id, draft):
    store_rows = stores_mod.load()
    origins = {stores_mod.store_for_url(u, store_rows)["origin"] for u in draft["links"]}
    added = {}

    def fn(items):
        it = state.new_item(items, draft["name"], draft["links"], draft["qty"], draft.get("weight_kg"),
                            draft.get("size_cm"), who(cfg, chat_id))
        items.append(it)
        added.update(it)
        return ""
    try:
        extra = _mutate(cfg, root, fn)
    except ValueError as e:
        return esc(str(e))
    n = len(state.active(state.load_items(root)))
    msg = ("✅ Added <b>%d. %s</b> — first prices in tonight's report (~01:30), or /watch check now."
           % (n, esc(added["name"])))
    if not added.get("weight_kg"):
        msg += "\n⚖️ No weight yet: totals per forwarder need it (/watch weight %d 2.4)." % n
    if "china" in origins and not added.get("weight_kg"):
        msg += ("\n\nSend this to the seller to ask the package weight and size:\n<code>%s</code>"
                % CHINESE_TEMPLATE)
    return msg + extra


# ----------------------------------------------------------------- entry

def handle(cfg, root, text, chat_id, today=None):
    """A /watch command or a dialog answer. Returns a reply to send, or None.
    '/watch check' is not handled here: the listener launches the market job."""
    parts = (text or "").strip().split()
    args = parts[1:]
    sub = args[0].lower() if args else ""
    today = today or ui.now_local().date()
    if sub == "answer":
        return answer(cfg, root, chat_id, (text or "").strip().split(None, 2)[2] if len(args) > 1 else "")
    if not sub or sub == "list":
        body, rows = list_view(root)
        telegram.send_html(cfg, body, silent=True, buttons=rows, chat_id=chat_id)
        return None
    if sub == "add":
        return start_add(cfg, root, chat_id)
    if sub in ("bought", "remove") and len(args) == 2:
        return _set_status(cfg, root, args[1], "bought" if sub == "bought" else "removed")
    if sub == "price":
        return _owner_price(cfg, root, args[1:], today)
    if sub == "weight":
        return _set_weight(cfg, root, args[1:])
    return HELP


def route_reply(text, reply_to_text):
    """An answer to a Market add prompt -> '/watch answer <text>' (slash commands untouched)."""
    t = (text or "").strip()
    if reply_to_text and PROMPT_MARK in reply_to_text and t and not t.startswith("/"):
        return "/watch answer " + t
    return None
