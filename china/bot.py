"""/china in Telegram (docs/briefs/CHINA_SEARCH.md §5). Called by listener.py; never blocks:
every model or browser step runs in the worker (jobs/china_search.py) through the queue.

    /china <description>                    search Pinduoduo, Taobao, 1688
    /china only pinduoduo|taobao|1688 <d>   one site
    /china last                             the last answer (24 h)
    /china cancel                           drop your waiting searches
    a photo with caption /china [only <site>] [note]   photo search (decision 095)
    a photo without a /china caption        one question: "🇨🇳 Search China" / "✖ No"
Buttons (cn:):  cn:ask  cn:only:<site>:<job>  cn:rev:<job>:<n>  cn:watch:<job>:<n>
                cn:q:<job>:<question>:<option|-1>  cn:ph:<id>  cn:phx:<id>
Davit and Karine share one Chrome session, one queue and the same features; the answer goes
to whoever asked.
"""
import os
import re
import time

from china import photo as ph
from china import queue, search, watch
from lib import telegram

ESC = telegram.esc
SITES = {"pinduoduo": "pinduoduo", "pdd": "pinduoduo", "taobao": "taobao", "tmall": "taobao",
         "1688": "1688"}
NAMES = {"pinduoduo": "Pinduoduo", "taobao": "Taobao", "1688": "1688"}
PROMPT = "🇨🇳 China search · what are you looking for?"
USAGE = ("🇨🇳 <b>China search</b> — Pinduoduo, Taobao and 1688, priced to Yerevan.\n"
         "<code>/china GaN charger 65W with EU plug</code>\n"
         "<code>/china only taobao Grohe kitchen faucet official store</code>\n"
         "<code>/china last</code> · <code>/china cancel</code>")
DESC_RE = re.compile(r"^.{3,200}$", re.S)
MINUTES = {"pinduoduo": 4, "taobao": 3, "1688": 5}
PHOTO_ASK = ("📷 Search China for the item in this photo? (1688 by photo, Pinduoduo by its "
             "words, Taobao as a link)")
SEARCH_ROLES = ("owner", "adult", "member")      # viewer: may look, may not start searches


def _enqueue(cfg, root, chat_id, job):
    job.setdefault("job", queue.new_id())
    job.update(chat_id=str(chat_id), kind=job.get("kind", "search"))
    busy = queue.running(root)
    place = queue.enqueue(job, root)
    watch.ensure_worker(cfg, root)          # starts and watches the worker (decision 104)
    if busy or place > 1:
        return "\n<i>Another China search is running — you are %s in line.</i>" % _nth(place)
    return ""


def _nth(n):
    return "%d%s" % (n, {1: "st", 2: "nd", 3: "rd"}.get(n if n < 20 else n % 10, "th"))


def start_search(cfg, root, chat_id, description, sites=None, plan=None, answers=None):
    sites = sites or ["pinduoduo", "taobao", "1688"]
    job = {"description": description, "sites": sites}
    if plan:
        job["plan"] = plan
    if answers:
        job["answers"] = answers
    wait = _enqueue(cfg, root, chat_id, job)
    link_only = search.load_cfg(root).get("taobao_mode", "link") == "link"
    mins = sum(0 if (s == "taobao" and link_only) else MINUTES[s] for s in sites) or 1
    return ("⏳ Searching %s for <b>%s</b>… (~%d min; I'll post progress)%s"
            % (", ".join(NAMES[s] for s in sites), ESC(description), mins, wait))


def handle(cfg, root, text, chat_id):
    parts = (text or "").strip().split(None, 1)
    rest = parts[1].strip() if len(parts) > 1 else ""
    low = rest.lower()
    if not rest:
        return USAGE
    if low == "last":
        return send_last(cfg, root, chat_id)
    if low == "cancel":
        n = queue.remove_for_chat(chat_id, root)
        return ("🗑 Removed %d waiting China search%s." % (n, "" if n == 1 else "es")) if n \
            else "Nothing of yours is waiting. (A search already running finishes on its own.)"
    sites = None
    m = re.match(r"only\s+(\S+)\s*(.*)$", rest, re.I | re.S)
    if m:
        site = SITES.get(m.group(1).lower())
        if not site:
            return "Which site? <code>/china only pinduoduo|taobao|1688 &lt;description&gt;</code>"
        sites, rest = [site], m.group(2).strip()
    if not DESC_RE.match(rest):
        return "Describe the item in 3–200 characters, e.g. <code>/china GaN charger 65W EU plug</code>"
    return start_search(cfg, root, chat_id, rest, sites)


def send_last(cfg, root, chat_id):
    ccfg = search.load_cfg(root)
    last = search.load_last(root, chat_id, ccfg.get("keep_last_hours", 24))
    if not last:
        return "No China search in the last %d h." % ccfg.get("keep_last_hours", 24)
    telegram.send_rich(cfg, last["rich"], last["plain"], buttons=last.get("buttons"), chat_id=chat_id)
    return None


def _watch(cfg, root, chat_id, job_id, n):
    from market import bot as mbot
    from market import state
    from lib import ui
    p, _ = search.find_result(root, chat_id, job_id, n)
    if not p or p.get("price") is None or not p.get("link"):
        return "That result is gone (older than 24 h) or has no price — run /china again."
    added = {}

    def fn(items):
        same = next((it for it in state.active(items) if p["link"] in (it.get("links") or [])), None)
        if same:                                   # a second tap, in the chat or the Mini App
            raise ValueError(f"👁 Already on 🌍 Market watch: {same['name']} — nothing added.")
        it = state.new_item(items, _short(p["title_en"]), [p["link"]], 1,
                            None if p["weight_assumed"] else p["kg"],
                            list(p["dims"]) if p.get("dims") else None, mbot.who(cfg, chat_id))
        items.append(it)
        added.update(it)
        return ""
    try:
        extra = mbot._mutate(cfg, root, fn)
    except ValueError as e:
        return ESC(str(e))
    state.set_owner_price(root, added["id"], p["site"], p["price"], p.get("currency") or "CNY",
                          ui.now_local().date())
    msg = ("👁 Added to 🌍 Market watch: <b>%s</b> at %s (from /china, %s). It shows in tonight's "
           "report; the price stays as read today until you update it with /watch price."
           % (ESC(added["name"]), ESC(_money(p)), NAMES[p["site"]]))
    if p["weight_assumed"]:
        msg += "\n⚖️ No weight on the page: /watch weight &lt;n&gt; &lt;kg&gt; once the seller answers."
    return msg + extra


def _short(s, n=60):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _money(p):
    sym = "$" if p.get("currency") == "USD" else "¥"
    return "%s%s" % (sym, ("%g" % p["price"]))


def _answer_question(cfg, root, chat_id, job_id, qi, oi):
    pend = search.read_json(root, "pending_%s.json" % job_id)
    if not pend or str(pend.get("chat_id")) != str(chat_id):
        return "That question has expired — send /china again."
    qs = pend["plan"]["questions"]
    if not (0 <= qi < len(qs)) or qi != len(pend["answers"]):
        return None                                   # an old tap on an answered question
    if oi >= 0:
        if oi >= len(qs[qi]["options"]):
            return "Unrecognised button."
        pend["answers"].append("%s %s" % (qs[qi]["q"].rstrip("?"), qs[qi]["options"][oi]))
    else:
        pend["answers"].append("")
    if oi >= 0 and qi + 1 < len(qs):
        search.write_json(root, "pending_%s.json" % job_id, pend)
        search.ask_question(telegram, cfg, root, pend, qi + 1)
        return None
    try:
        os.remove(os.path.join(search.data_dir(root), "pending_%s.json" % job_id))
    except OSError:
        pass
    plan = dict(pend["plan"], vague=False)
    return start_search(cfg, root, chat_id, pend["description"], pend.get("sites"), plan,
                        [a for a in pend["answers"] if a] or None)


def callback(cfg, root, data, chat_id):
    p = (data or "").split(":")
    if p == ["cn", "ask"]:
        telegram.send_html(cfg, PROMPT, silent=True, force_reply="e.g. GaN charger 65W EU plug",
                           chat_id=chat_id)
        return None
    if len(p) == 3 and p[1] in ("ph", "phx") and re.fullmatch(r"[0-9a-f]{8}", p[2]):
        return _photo_answer(cfg, root, chat_id, p[2], p[1] == "ph")
    if len(p) == 4 and p[1] == "only" and p[2] in NAMES:
        last = search.load_last(root, chat_id)
        if not last or last.get("job") != p[3]:
            return "That search is older than 24 h — send /china again."
        if last.get("kind") == "photo" and last.get("photo_of"):
            return _only_photo(cfg, root, chat_id, last, p[2])
        plan = {"query_cn": last["query_cn"], "vague": False, "questions": [],
                "category": last.get("category", "other")}
        return start_search(cfg, root, chat_id, last["description"], [p[2]], plan)
    if len(p) == 4 and p[1] in ("rev", "watch") and p[3].isdigit():
        if p[1] == "watch":
            return _watch(cfg, root, chat_id, p[2], int(p[3]))
        r, _ = search.find_result(root, chat_id, p[2], int(p[3]))
        if not r:
            return "That result is older than 24 h — send /china again."
        wait = _enqueue(cfg, root, chat_id, {"kind": "reviews", "for_job": p[2], "n": int(p[3])})
        return "⏳ Reading the reviews of %d. %s… (~2 min)%s" % (int(p[3]), ESC(_short(r["title_en"])), wait)
    if len(p) == 5 and p[1] == "q" and p[3].isdigit() and re.fullmatch(r"-?\d", p[4]):
        return _answer_question(cfg, root, chat_id, p[2], int(p[3]), int(p[4]))
    return "Unrecognised button."


# ------------------------------------------------------------------ photo search

def who(msg, root=None):
    """{"user_id", "role"} of the sender (household-ready, decision 089): the Telegram user id
    and the role from config_miniapp.json people (Users and roles replaces that source)."""
    uid = (msg.get("from") or {}).get("id")
    role = None
    try:
        import json

        from china import ROOT
        from miniapp import people
        with open(os.path.join(root or ROOT, "config_miniapp.json"), encoding="utf-8") as f:
            person = people.lookup(people.load(json.load(f)), uid)
        role = person.role if person else None
    except Exception:  # noqa: BLE001 — no people list = no role; the chat allow-list still applies
        role = None
    return {"user_id": uid, "role": role}


def photo(cfg, root, msg, chat_id):
    """A photo (or an image sent as a file) from an allowed chat. A /china caption starts the
    search; any other photo gets one button question, never a search on its own (decision 095:
    other features may use photos later — Health records reads them only inside /health)."""
    img = ph.pick(msg)
    if not img:
        return None
    if img["size"] > ph.MAX_BYTES:
        return "📷 That photo is larger than 10 MB — send it as a normal photo."
    person = who(msg, root)
    if person["role"] and person["role"] not in SEARCH_ROLES:
        return "🔒 China search is not available for your role."
    try:
        cmd = ph.caption_command(msg.get("caption"))
    except ValueError as e:
        return str(e)
    # crash safety; never shorter than an hour so a photo in a running job is not touched
    ph.sweep(root, max(search.load_cfg(root).get("photo_keep_minutes", 0), 60))
    if cmd is None:
        _prune_pending(root)
        pid = queue.new_id()
        search.write_json(root, f"pending_photo_{pid}.json", {
            "job": pid, "chat_id": str(chat_id), "file_id": img["file_id"], "ext": img["ext"],
            "note": (msg.get("caption") or "").strip()[:200], "saved": time.time(), **person})
        telegram.send_html(cfg, PHOTO_ASK, silent=True, chat_id=chat_id,
                           buttons=[[("🇨🇳 Search China", f"cn:ph:{pid}"), ("✖ No", f"cn:phx:{pid}")]])
        return None
    sites, note = cmd
    return start_photo(cfg, root, chat_id, {"file_id": img["file_id"], "ext": img["ext"],
                                            "note": note, **person}, sites)


def start_photo(cfg, root, chat_id, fields, sites=None, plan=None):
    sites = sites or ["pinduoduo", "taobao", "1688"]
    job = dict(fields, kind="photo", sites=sites)
    if plan:
        job["plan"] = plan
    wait = _enqueue(cfg, root, chat_id, job)
    link_only = search.load_cfg(root).get("taobao_mode", "link") == "link"
    mins = 1 + sum(0 if (s == "taobao" and link_only) else MINUTES[s] for s in sites)
    how = []
    if "1688" in sites:
        how.append("1688 by photo")
    if "pinduoduo" in sites:
        how.append("Pinduoduo by the words in it")
    if "taobao" in sites:
        how.append("a Taobao link")
    return f"⏳ Searching China by your photo — {', '.join(how)}… (~{mins} min; I'll post progress){wait}"


def _prune_pending(root, minutes=None):
    keep = minutes if minutes is not None else search.load_cfg(root).get("photo_ask_minutes", 60)
    d = search.data_dir(root)
    for name in os.listdir(d):
        if name.startswith("pending_photo_"):
            pend = search.read_json(root, name) or {}
            if time.time() - pend.get("saved", 0) > keep * 60:
                try:
                    os.remove(os.path.join(d, name))
                except OSError:
                    pass


def _photo_answer(cfg, root, chat_id, pid, yes):
    name = f"pending_photo_{pid}.json"
    pend = search.read_json(root, name)
    if not pend or str(pend.get("chat_id")) != str(chat_id):
        return "That photo question has expired — send the photo again." if yes else None
    try:
        os.remove(os.path.join(search.data_dir(root), name))
    except OSError:
        pass
    if not yes:
        return "OK — not searching."
    if time.time() - pend.get("saved", 0) > search.load_cfg(root).get("photo_ask_minutes", 60) * 60:
        return "That photo question has expired — send the photo again."
    fields = {k: pend.get(k) for k in ("file_id", "ext", "note", "user_id", "role")}
    return start_photo(cfg, root, chat_id, fields)


def _only_photo(cfg, root, chat_id, last, site):
    """🔁 Only <site> on a photo answer: by photo again while the photo is kept
    (photo_keep_minutes), else by the words read from it."""
    if ph.find(root, last["photo_of"]):
        return start_photo(cfg, root, chat_id, {"photo_of": last["photo_of"], "note": "",
                                                 "user_id": last.get("user_id"),
                                                 "role": last.get("role")}, [site], last.get("plan"))
    plan = {"query_cn": last["query_cn"], "vague": False, "questions": [],
            "category": last.get("category", "other")}
    words = ESC(last["query_cn"])
    return (f"<i>The photo is deleted after the search, so this one goes by its words "
            f"({words}).</i>\n") + start_search(
        cfg, root, chat_id, last["description"], [site], plan)


def route_reply(text, reply_to_text):
    """An answer to the China search prompt becomes /china <text>; a typed command is left."""
    if reply_to_text and reply_to_text.startswith(PROMPT) and text and not text.startswith("/"):
        return "/china " + text.strip()
    return text
