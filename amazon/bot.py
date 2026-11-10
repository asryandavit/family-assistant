"""/amazon in Telegram (docs/briefs/AMAZON_SEARCH.md §1). Called by listener.py; never blocks:
every model or browser step runs in the worker (jobs/amazon_search.py) through the queue.

    /amazon <description>              search Amazon UK, DE, IT
    /amazon only uk|de|it <desc>       one store
    /amazon last                       the last answer (24 h)
    /amazon cancel                     drop your waiting searches
Buttons (am:):  am:ask  am:q:<job>:<question>:<option|-1>  am:watch:<job>:<n>
Davit and Karine share one browser, one queue and the same features; the answer goes to
whoever asked. Structure and wording follow china/bot.py (# same as china/bot.py where copied).
"""
import os
import re

from amazon import parse, queue, search
from lib import telegram

ESC = telegram.esc
STORES = {"uk": "uk", "de": "de", "it": "it", "germany": "de", "italy": "it"}
PROMPT = "🛒 Amazon search · what are you looking for?"
USAGE = ("🛒 <b>Amazon search</b> - Amazon UK, DE and IT, priced to Yerevan.\n"
         "<code>/amazon usb c charger 65w</code>\n"
         "<code>/amazon baby romper 6-12 months</code>\n"
         "<code>/amazon only de lego technic 42115</code>\n"
         "<code>/amazon last</code> · <code>/amazon cancel</code>")
DESC_RE = re.compile(r"^.{3,200}$", re.S)
MINUTES = 5


def _nth(n):                                                   # same as china/bot.py
    return "%d%s" % (n, {1: "st", 2: "nd", 3: "rd"}.get(n if n < 20 else n % 10, "th"))


def _enqueue(cfg, root, chat_id, job):                         # same as china/bot.py
    job.setdefault("job", queue.new_id())
    job.update(chat_id=str(chat_id), kind=job.get("kind", "search"))
    busy = queue.running(root)
    place = queue.enqueue(job, root)
    queue.start_worker(root)
    if busy or place > 1:
        return "\n<i>Another Amazon search is running - you are %s in line.</i>" % _nth(place)
    return ""


def start_search(cfg, root, chat_id, description, stores=None, answers=None, no_questions=False):
    stores = stores or list(search.load_cfg(root)["stores"])
    job = {"description": description, "stores": stores}
    if answers:
        job["answers"] = answers
    if no_questions:
        job["no_questions"] = True
    wait = _enqueue(cfg, root, chat_id, job)
    return ("⏳ Searching %s for <b>%s</b>… (~%d min; I'll post progress)%s"
            % (", ".join(parse.NAME[s] for s in stores), ESC(description), MINUTES, wait))


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
        return ("🗑 Removed %d waiting Amazon search%s." % (n, "" if n == 1 else "es")) if n \
            else "Nothing of yours is waiting. (A search already running finishes on its own.)"
    stores = None
    m = re.match(r"only\s+(\S+)\s*(.*)$", rest, re.I | re.S)
    if m:
        site = STORES.get(m.group(1).lower())
        if not site:
            return "Which store? <code>/amazon only uk|de|it &lt;description&gt;</code>"
        stores, rest = [site], m.group(2).strip()
    if not DESC_RE.match(rest):
        return "Describe the item in 3–200 characters, e.g. <code>/amazon usb c charger 65w</code>"
    return start_search(cfg, root, chat_id, rest, stores)


def send_last(cfg, root, chat_id):
    acfg = search.load_cfg(root)
    last = search.load_last(root, chat_id, acfg.get("keep_last_hours", 24))
    if not last:
        return "No Amazon search in the last %d h." % acfg.get("keep_last_hours", 24)
    telegram.send_rich(cfg, last["rich"], last["plain"], buttons=last.get("buttons"), chat_id=chat_id)
    return None


def _short(s, n=60):                                           # same as china/bot.py
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _watch(cfg, root, chat_id, job_id, n):
    """👁 Watch: the exact /dp/ link through the Market watch add path; a link already on the
    list is not added again (decision 099)."""
    from market import bot as mbot
    from market import state
    p, _ = search.find_result(root, chat_id, job_id, n)
    if not p or p.get("price") is None or not p.get("url"):
        return "That result is gone (older than 24 h) or has no price - run /amazon again."
    added = {}

    def fn(items):
        same = next((it for it in state.active(items) if p["url"] in (it.get("links") or [])), None)
        if same:
            raise ValueError(f"👁 Already on 🌍 Market watch: {same['name']} - nothing added.")
        it = state.new_item(items, _short(p.get("title")), [p["url"]], 1,
                            None if p["weight_assumed"] else p["kg"],
                            list(p["dims_cm"]) if p.get("dims_cm") else None, mbot.who(cfg, chat_id))
        items.append(it)
        added.update(it)
        return ""
    try:
        extra = mbot._mutate(cfg, root, fn)
    except ValueError as e:
        return ESC(str(e))
    msg = ("👁 Added to 🌍 Market watch: <b>%s</b> (%s, from /amazon). It is re-read every night "
           "and shows in the report." % (ESC(added["name"]), parse.NAME[p["site"]]))
    if p["weight_assumed"]:
        msg += "\n⚖️ No weight on the page: /watch weight &lt;n&gt; &lt;kg&gt; once you know it."
    return msg + extra


def _answer_question(cfg, root, chat_id, job_id, qi, oi):
    pend = search.read_json(root, "pending_%s.json" % job_id)
    if not pend or str(pend.get("chat_id")) != str(chat_id):
        return "That question has expired - send /amazon again."
    qs = pend["plan"]["questions"]
    if not (0 <= qi < len(qs)) or qi != len(pend["answers"]):
        return None                                   # an old tap on an answered question
    skipped = oi < 0
    if not skipped and oi >= len(qs[qi]["options"]):
        return "Unrecognised button."
    answer = "" if skipped else "%s %s" % (qs[qi]["q"].rstrip("?"), qs[qi]["options"][oi])
    try:
        os.remove(os.path.join(search.data_dir(root), "pending_%s.json" % job_id))
    except OSError:
        pass
    # the plan is made again with the answer in the words, so the German/Italian size words match
    return start_search(cfg, root, chat_id, pend["description"], pend.get("stores"),
                        [answer] if answer else None, no_questions=skipped)


def callback(cfg, root, data, chat_id):
    p = (data or "").split(":")
    if p == ["am", "ask"]:
        telegram.send_html(cfg, PROMPT, silent=True, force_reply="e.g. usb c charger 65w", chat_id=chat_id)
        return None
    if len(p) == 4 and p[1] == "watch" and p[3].isdigit():
        return _watch(cfg, root, chat_id, p[2], int(p[3]))
    if len(p) == 5 and p[1] == "q" and p[3].isdigit() and re.fullmatch(r"-?\d", p[4]):
        return _answer_question(cfg, root, chat_id, p[2], int(p[3]), int(p[4]))
    return "Unrecognised button."


def route_reply(text, reply_to_text):
    """An answer to the Amazon search prompt becomes /amazon <text>; a typed command is left."""
    if reply_to_text and reply_to_text.startswith(PROMPT) and text and not text.startswith("/"):
        return "/amazon " + text.strip()
    return text
