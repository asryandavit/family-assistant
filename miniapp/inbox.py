"""Command inbox: how the Mini App asks the listener to run a chat command (decision 098).

The Mini App server never starts jobs itself. It writes one small JSON file per request into
.browser/miniapp_inbox/; a thread in listener.py takes each file and feeds the text to the
same `handle_text` a typed message goes through. So every request gets the chat's own
validation (`_safe_stays_args`, `flights.parse_command`, …), the listener's one-job-at-a-time
runner and its "already running" answer, and the reply lands in the person's chat.

Both ends check the same allow-list of commands and the same size limits, and the listener
checks the chat id against the bot's allowed chats. At-most-once: a file is deleted before it is
run, so a crash can lose a request but never run it twice. Pure file I/O, no Telegram.
"""
import json
import os
import re
import time
import uuid

DIRNAME = "miniapp_inbox"
MAX_AGE_S = 120               # an older request is dropped: nobody is waiting for it any more
MAX_TEXT = 220                # "only pinduoduo " (15) + the chat's 200-character description fits
ALIVE = "alive"               # touched by the listener thread every pass (decision 102)
ALIVE_S = 15                  # a heartbeat older than this means the listener is not draining us
# Commands the app may send. /watch is only "check"; /china needs a description.
COMMANDS = ("basket", "scan", "digest", "flights", "stays", "price", "watch", "china")
TEXT_RE = re.compile(rf"^/(?P<cmd>[a-z]+)(?: (?P<rest>[^\x00-\x1f]{{1,{MAX_TEXT}}}))?$")


def inbox_dir(root):
    d = os.path.join(root, ".browser", DIRNAME)
    os.makedirs(d, exist_ok=True)
    return d


def heartbeat(root, now=None):
    """Called by the listener's inbox thread every pass: proof it is alive and draining."""
    d = inbox_dir(root)
    tmp = os.path.join(d, ALIVE + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(repr(now or time.time()))
    os.replace(tmp, os.path.join(d, ALIVE))


def listener_alive(root, now=None):
    """True if the listener's inbox thread ticked within ALIVE_S. A request queued while this
    is False would expire unseen, so the server refuses it instead."""
    try:
        with open(os.path.join(inbox_dir(root), ALIVE), encoding="utf-8") as f:
            ts = float(f.read())
    except (OSError, ValueError):
        return False
    return -5 < (now or time.time()) - ts < ALIVE_S


def check_text(text):
    """(command, rest) for an allowed command text, or None."""
    m = TEXT_RE.match(text or "")
    if not m or m["cmd"] not in COMMANDS:
        return None
    rest = (m["rest"] or "").strip()
    if m["cmd"] == "watch" and rest != "check":
        return None
    if m["cmd"] in ("scan", "digest") and rest:
        return None
    if m["cmd"] in ("china", "price", "flights", "stays", "basket") and not rest:
        return None
    return m["cmd"], rest


def put(root, chat_id, text, now=None):
    """Queue `text` (e.g. "/basket weekly") for the chat. True if queued."""
    if check_text(text) is None or not str(chat_id).lstrip("-").isdigit():
        return False
    name = f"{int((now or time.time()) * 1000):015d}-{uuid.uuid4().hex[:8]}.json"
    tmp = os.path.join(inbox_dir(root), name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"chat_id": str(chat_id), "text": text}, f)
    os.replace(tmp, os.path.join(inbox_dir(root), name))
    return True


def take(root, allowed_chats, now=None):
    """Oldest-first list of (chat_id, text) to run now. Every file seen is removed; stale,
    unreadable, foreign-chat or disallowed ones are dropped."""
    now = now or time.time()
    d = inbox_dir(root)
    out = []
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(d, name)
        try:
            with open(path, encoding="utf-8") as f:
                req = json.load(f)
        except (OSError, ValueError):
            req = None
        try:
            os.remove(path)
        except OSError:
            continue                      # someone else took it
        try:
            written = int(name.split("-")[0]) / 1000
        except ValueError:
            continue
        if (not isinstance(req, dict) or now - written > MAX_AGE_S
                or str(req.get("chat_id")) not in set(map(str, allowed_chats))
                or check_text(req.get("text")) is None):
            continue
        out.append((str(req["chat_id"]), req["text"]))
    return out
