"""Telegram command listener for the Family Assistant.

Security model, in order:
  1. Only ALLOWED_CHAT (your chat id) is heard; everyone else gets silence.
  2. Commands map to a FIXED table of scripts -- user text is never passed to
     a shell (list-args subprocess only), so there is nothing to inject.
  3. One job at a time via a lock; extra requests get "already running".
  4. A localhost socket bind guarantees a single listener instance.
  5. The bot token lives only in the environment variable.

Footprint: long polling blocks server-side, so CPU is ~0 while idle and RSS
sits around 25-35 MB. Run it with pythonw.exe (no console window); it logs to
.browser/listener.log and a heartbeat row lands in Runs every 12 hours.
"""
import os
import re
import socket
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timezone

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from lib import config, flights, fmt, parse_cmd, places, sheets, tasks, telegram, ui  # noqa: E402

SINGLETON_PORT = 48291
POLL_TIMEOUT = 50
HEARTBEAT_SEC = 12 * 3600
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

# The ONLY things this listener can run. Commands never reach a shell.
JOBS = {
    "scan":   {"args": [os.path.join(ROOT, "jobs", "travel_scan.py")],
               "ack": "\u23f3 Running travel scan\u2026 (2\u20136 min)"},
    "digest": {"args": [os.path.join(ROOT, "jobs", "travel_scan.py"), "--digest"],
               "ack": "\u23f3 Building digest\u2026 (2\u20136 min)"},
    "stays":  {"args": [os.path.join(ROOT, "jobs", "stays_scan.py")],
               "ack": "\u23f3 Searching stays\u2026 (2\u20134 min)"},
    "flights": {"args": [os.path.join(ROOT, "jobs", "flights_search.py")],
                "ack": "\u23f3 Searching flights\u2026 (1\u20133 min)"},
    "price":  {"args": [os.path.join(ROOT, "jobs", "grocery_search.py"), "--send"],
               "ack": "\u23f3 Checking prices\u2026 (10\u201320 s)"},
    # Family content: the job sends its result to both chats itself (send_family),
    # so it is deliberately not in REPLY_JOBS; only the ack goes to the asker.
    "basket": {"args": [os.path.join(ROOT, "jobs", "grocery_basket.py"), "--send"],
               "ack": "\u23f3 Pricing this week's basket at both shops\u2026 (~2 min)\n"
                      "<i>The list goes to both of you and to the checklist.</i>"},
}

BASKET_KINDS = {"weekly": ("--weekly", "this week's basket"),
                "monthly": ("--monthly", "the monthly staples"),
                "all": ("--all", "the weekly and monthly lists")}

CITY_RE = re.compile(r"^[A-Za-z][A-Za-z .\-]{1,28}$")
PRICE_RE = re.compile(r"^[\w][\w\s%.,'\"&+\-]{1,39}$")
PRICE_SHOPS = {"parma": "parma", "yc": "yc", "yerevancity": "yc"}


def _safe_stays_args(cfg, text):
    """Validate a /stays request, then REBUILD the arguments from parsed values.

    Raw user text never reaches the subprocess: only a city matching CITY_RE,
    ISO dates produced by date.fromisoformat, and whitelisted keyword flags.
    """
    q = parse_cmd.parse(text, cfg)
    if "error" in q:
        return None, q["error"]
    if not CITY_RE.match(str(q["city"])):
        return None, "That city name looks odd \u2014 use a code like <code>LCA</code>."
    try:
        date.fromisoformat(q["checkin"]); date.fromisoformat(q["checkout"])
    except ValueError:
        return None, "Those dates didn't parse."
    allowed = set(parse_cmd.KEYWORDS.values())
    flags = [f for f in q["flags"] if f in allowed]

    args = [q["city"], "%s-%s" % (q["checkin"], q["checkout"])] + flags
    if q.get("budget"):
        args.append("budget%d" % int(q["budget"]))
    label = ("\u23f3 Searching stays in <b>%s</b>\n%s \u2192 %s \u00b7 %dn%s"
             % (telegram.esc(places.label(cfg, q["city"])), q["checkin"], q["checkout"], q["nights"],
                " \u00b7 " + telegram.esc(", ".join(flags)) if flags else ""))
    return args, label


def _safe_price_args(text):
    """Validate /price <product> [parma|yc] [match], then REBUILD the arguments.

    Only words matching PRICE_RE reach the subprocess, after a "--" so nothing
    the user types can be read as a command-line option.
    """
    words = text.strip().split()[1:]
    shop, sort = None, "cheap"
    while words and (words[-1].lower() in PRICE_SHOPS or words[-1].lower() == "match"):
        w = words.pop().lower()
        if w == "match":
            sort = "match"
        else:
            shop = PRICE_SHOPS[w]
    query = " ".join(words).strip().lstrip("-").strip()
    if not query:
        return None, ("Which product? For example:\n<code>/price lentils</code>\n"
                      "<code>/price olive oil parma</code>\n<code>/price chicken breast</code>")
    if not PRICE_RE.match(query):
        return None, "Keep it to a product name, up to 40 letters \u2014 e.g. <code>/price oats</code>."
    args = ["--sort", sort]
    if shop:
        args += ["--shop", shop]
    args += ["--"] + query.split()
    where = {"parma": "Parma", "yc": "Yerevan City"}.get(shop, "Parma + Yerevan City")
    return args, "\u23f3 Checking prices for <b>%s</b> at %s\u2026" % (telegram.esc(query), where)

def _safe_basket_args(text):
    """/basket [weekly|monthly|all] -> (args, ack) or (None, error). Only fixed
    flags reach the subprocess; any other word is refused."""
    words = [w.lower() for w in text.strip().split()[1:]]
    kind = words[0] if words else "weekly"
    if len(words) > 1 or kind not in BASKET_KINDS:
        return None, "Use <code>/basket</code>, <code>/basket monthly</code> or <code>/basket all</code>."
    flag, label = BASKET_KINDS[kind]
    return [flag], ("⏳ Pricing %s at both shops… (~%d min)\n"
                    "<i>The list goes to both of you and to the checklist.</i>"
                    % (label, 4 if kind == "all" else 2))


HELP = ("\U0001f9ed <b>Commands</b>\n"
        "<i>The \U0001f3e0 Home and \U0001f50d Price check keys below do most of this.</i>\n\n"
        "/scan \u2014 run the flight scan now\n"
        "/digest \u2014 scan + send the full digest\n"
        "/stays &lt;city&gt; &lt;dates&gt; [keywords] \u2014 search accommodation\n"
        "/flights &lt;city&gt; &lt;window&gt; [nights] \u2014 search flights\n"
        "/price &lt;product&gt; [parma|yc] \u2014 grocery prices + links\n"
        "/basket [monthly|all] \u2014 price the shopping list, fill the checklist\n"
        "/auto \u2014 automation status, pause/enable\n"
        "/menu \u2014 the Home screen\n"
        "/today \u2014 today's meals and both sessions\n"
        "/cancel \u2014 stop whatever is running\n"
        "/status \u2014 listener health + last runs\n"
        "/help \u2014 this message\n\n"
        "<b>Stays examples</b>\n"
        "<code>/stays LCA 04-11.11 sea center</code>\n"
        "<code>/stays BUD 24.01 apt budget90</code>\n"
        "<code>/stays NAP 01-08.12 quiet breakfast</code>\n"
        "<i>keywords: sea center quiet pool breakfast apt hotel strict budget&lt;N&gt;</i>")

START = time.time()
_log_f = None


def log(msg):
    global _log_f
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        if _log_f is None:
            os.makedirs(os.path.join(ROOT, ".browser"), exist_ok=True)
            _log_f = open(os.path.join(ROOT, ".browser", "listener.log"),
                          "a", encoding="utf-8")
        _log_f.write(line + "\n")
        _log_f.flush()
    except OSError:
        pass


# Jobs whose result answers the person who asked (decision 082). Travel scans and
# digests are the owner's alert stream and always go to the owner.
REPLY_JOBS = {"flights", "stays", "price"}


def job_env(name, chat_id, base=None):
    """Environment for a launched job: carries the asker's chat for REPLY_JOBS."""
    env = dict(os.environ if base is None else base)
    env.pop(telegram.REPLY_CHAT_ENV, None)
    if chat_id and name in REPLY_JOBS:
        env[telegram.REPLY_CHAT_ENV] = str(chat_id)
    return env


class Runner:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.current = None
        self.started = None
        self.proc = None
        self.cancelled = False

    def launch(self, name, extra_args=None, ack=None, chat_id=None):
        job = dict(JOBS[name])
        if extra_args:
            job["args"] = job["args"] + list(extra_args)
        if not self.lock.acquire(blocking=False):
            return (f"\u26a0\ufe0f <b>{self.current}</b> is already running "
                    f"(started {int(time.time() - self.started)}s ago). Queued nothing.")
        self.current, self.started = name, time.time()
        self.cancelled = False
        threading.Thread(target=self._run, args=(name, job, chat_id), daemon=True).start()
        telegram.chat_action(self.cfg, chat_id=chat_id)   # "typing…" while it works
        return (ack or job["ack"]) + "\n<i>/cancel to stop</i>"

    def _run(self, name, job, chat_id=None):
        try:
            proc = subprocess.Popen([sys.executable, *job["args"]], cwd=ROOT,
                                    creationflags=CREATE_NO_WINDOW,
                                    env=job_env(name, chat_id))
            self.proc = proc
            rc = proc.wait(timeout=1800)
            log(f"job {name} finished rc={rc}")
            if self.cancelled:
                pass  # deliberate stop: no error notification
            elif rc != 0:
                telegram.notify(self.cfg,
                                f"\u26a0\ufe0f SYSTEM: job '{name}' exited with code {rc}. "
                                f"Check .browser\\listener.log and the Runs tab.")
        except Exception as e:
            log(f"job {name} crashed: {e}")
            telegram.notify(self.cfg, f"\u26a0\ufe0f SYSTEM: job '{name}' crashed: {e}")
        finally:
            self.current = None
            self.proc = None
            self.lock.release()

    def cancel(self):
        """Stop the job this listener started AND any job started by Task
        Scheduler (the 08:00 run, or a Run now tap), plus their browsers.

        Task Scheduler launches a separate process the listener never sees, so
        tracking self.proc alone reports "nothing running" while Chromium is
        clearly open. Sweeping by repo path catches both.
        """
        self.cancelled = True
        killed_jobs, killed_browsers = 0, 0
        me = os.getpid()

        if self.proc:
            try:
                self.proc.kill()
                killed_jobs += 1
            except Exception:
                pass

        try:
            import psutil
        except ImportError:
            return "\u26a0\ufe0f psutil missing \u2014 run <code>pip install psutil</code>."

        # Normalize separators: command lines mix / and \\ and case, so compare
        # on a canonical form rather than raw os.path.join output.
        def canon(x):
            return x.replace("/", "\\").lower()

        jobs_dir = canon(ROOT) + "\\jobs\\"
        browser_dir = canon(ROOT) + "\\.browser"
        victims = []
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            if p.info["pid"] == me:
                continue
            try:
                cmd = canon(" ".join(p.info.get("cmdline") or []))
            except Exception:
                continue
            if not cmd:
                continue
            if jobs_dir in cmd:
                victims.append(("job", p))
            elif browser_dir in cmd:
                victims.append(("browser", p))

        for kind, p in victims:
            try:
                for child in p.children(recursive=True):
                    try:
                        child.kill()
                        killed_browsers += 1
                    except Exception:
                        pass
                p.kill()
                if kind == "job":
                    killed_jobs += 1
                else:
                    killed_browsers += 1
            except Exception:
                pass

        for key in ("travel", "training", "meals"):
            try:
                tasks.end(key)
            except Exception:
                pass

        self.current = None
        self.proc = None
        try:
            self.lock.release()
        except RuntimeError:
            pass

        if not killed_jobs and not killed_browsers:
            return "\u2705 Nothing is running."
        log("cancel: %d job(s), %d browser process(es)" % (killed_jobs, killed_browsers))
        bits = []
        if killed_jobs:
            bits.append("%d job%s" % (killed_jobs, "" if killed_jobs == 1 else "s"))
        if killed_browsers:
            bits.append("%d browser process%s"
                        % (killed_browsers, "" if killed_browsers == 1 else "es"))
        return "\U0001f6d1 Stopped %s." % " and ".join(bits)


def _uptime():
    s = int(time.time() - START)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, _ = divmod(s, 60)
    return (f"{d}d {h}h {m}m" if d else f"{h}h {m}m")


def _ram_mb():
    try:
        import psutil
        return f"{psutil.Process().memory_info().rss / 1048576:.0f} MB"
    except Exception:
        return "n/a (pip install psutil)"


def status(cfg, runner):
    busy = (f"running <b>{runner.current}</b> ({int(time.time() - runner.started)}s)"
            if runner.current else "idle")
    lines = [f"\U0001f3a7 <b>Listener</b> \u00b7 up {_uptime()} \u00b7 RAM {_ram_mb()}",
             f"State: {busy}", "", "<b>Last runs</b>"]
    try:
        rows = sheets.read_all(cfg, "Runs")[-5:]
        for r in rows:
            ts = (r[0] or "")[5:16].replace("T", " ")
            lines.append(f"\u2022 <code>{ts}</code> {telegram.esc(r[1])} "
                         f"\u2014 {telegram.esc(r[2])} {telegram.esc(r[3][:40] if len(r) > 3 else '')}")
    except Exception as e:
        lines.append(f"(Runs tab unreadable: {telegram.esc(str(e)[:80])})")
    return "\n".join(lines)


def set_menu(tok):
    cmds = [{"command": "menu", "description": "Home screen"},
            {"command": "today", "description": "Today's meals and training"},
            {"command": "price", "description": "Grocery prices: /price lentils"},
            {"command": "basket", "description": "Price the shopping list + checklist"},
            {"command": "flights", "description": "Search flights: /flights VCE 01-30.11 7"},
            {"command": "stays", "description": "Search stays: /stays LCA 04-11.11 sea"},
            {"command": "scan", "description": "Run the flight scan now"},
            {"command": "digest", "description": "Scan + full digest"},
            {"command": "status", "description": "Bot health"},
            {"command": "cancel", "description": "Stop the running job"},
            {"command": "help", "description": "All commands"}]
    api = f"https://api.telegram.org/bot{tok}"
    for method, payload in (("setMyCommands", {"commands": cmds}),
                            ("setMyDescription", {"description": BOT_DESCRIPTION}),
                            ("setMyShortDescription", {"short_description": BOT_SHORT_DESCRIPTION})):
        try:
            requests.post(f"{api}/{method}", json=payload, timeout=15)
        except requests.RequestException:
            pass


def handle_text(cfg, runner, text, chat_id=None):
    t = (text or "").strip()
    if t == ui.KEY_HOME:
        send_home(cfg, runner, chat_id)
        return None
    if t == ui.KEY_PRICE:
        send_price_prompt(cfg, chat_id)
        return None
    cmd = text.strip().split()[0].lower().lstrip("/").split("@")[0] if text.strip() else ""
    if cmd == "flights":
        q = flights.parse_command(text, cfg)
        if "error" in q:
            return q["error"]
        args = [q["dest"], "%s-%s" % (q["window_from"], q["window_to"])]
        n1, n2 = q["nights"]
        args.append("%d" % n1 if n1 == n2 else "%d-%d" % (n1, n2))
        if not q["include_openjaw"]:
            args.append("noopen")
        return runner.launch("flights", args, chat_id=chat_id,
                             ack="\u23f3 Searching flights to <b>%s</b>\n%s \u2192 %s"
                                 % (telegram.esc(places.label(cfg, str(q["dest"]))),
                                    q["window_from"], q["window_to"]))
    if cmd == "stays":
        args, msg = _safe_stays_args(cfg, text)
        if not args:
            return msg
        return runner.launch("stays", args, ack=msg, chat_id=chat_id)
    if cmd == "price":
        args, msg = _safe_price_args(text)
        if not args:
            return msg
        return runner.launch("price", args, ack=msg, chat_id=chat_id)
    if cmd == "basket":
        args, msg = _safe_basket_args(text)
        if not args:
            return msg
        return runner.launch("basket", args, ack=msg, chat_id=chat_id)
    if cmd in JOBS:
        return runner.launch(cmd, chat_id=chat_id)
    if cmd == "cancel":
        return runner.cancel()
    if cmd == "start":
        telegram.send_html(cfg, WELCOME, silent=True, reply_keyboard=ui.BOTTOM_KEYBOARD,
                           chat_id=chat_id)
        send_home(cfg, runner, chat_id)
        return None
    if cmd == "menu":
        send_home(cfg, runner, chat_id)
        return None
    if cmd == "today":
        text, btns = ui.section("today", ROOT, chat_id=chat_id)
        telegram.send_html(cfg, text, silent=True, buttons=btns, chat_id=chat_id)
        return None
    if cmd == "auto":
        rows = tasks.summary()
        telegram.send_html(cfg, fmt.auto_text(rows), buttons=fmt.auto_buttons(rows),
                           chat_id=chat_id)
        return None
    if cmd == "status":
        return status(cfg, runner)
    if cmd == "help":
        return HELP
    return None  # unknown text: stay silent


def _trip_lookup(cfg, trip_id):
    """Find a trip row by id in the Trips tab."""
    for r in reversed(sheets.read_all(cfg, "Trips")):
        if len(r) > 5 and r[1] == trip_id:
            return {"id": r[1], "kind": r[2], "route": r[3],
                    "out_date": r[4], "back_date": r[5]}
    return None


WELCOME = ("👋 <b>Family assistant</b>\n"
           "<i>Two keys below work any time: %s for everything, %s to compare grocery "
           "prices at Parma and Yerevan City.</i>" % (ui.KEY_HOME, ui.KEY_PRICE))

# Bot profile (docs/TELEGRAM_UX.md sections 6-7), applied at startup by set_menu().
BOT_DESCRIPTION = ("Family assistant for meals, training, shopping prices and travel deals. "
                   "Tap 🏠 Home to start, or 🔍 Price check to compare Parma "
                   "and Yerevan City.")
BOT_SHORT_DESCRIPTION = "Meals, training, grocery prices and travel deals for the family."


def _travel_next():
    """'19.10 08:00'-style next run of the flight scan, or None."""
    try:
        info = tasks.query("travel")
        if info.get("exists") and info.get("enabled"):
            return tasks._short_dt(info.get("next_run"))
    except Exception:
        pass
    return None


def send_home(cfg, runner, chat_id=None, message_id=None):
    """The Home message: edited in place when coming from a button, else sent."""
    text, buttons = ui.home(ROOT, running=runner.current, travel_next=_travel_next())
    if chat_id and message_id:
        telegram.edit_html(cfg, chat_id, message_id, text, buttons)
    else:
        telegram.send_html(cfg, text, silent=True, buttons=buttons, chat_id=chat_id)


def send_price_prompt(cfg, chat_id=None):
    telegram.send_html(cfg, ui.PRICE_PROMPT, silent=True, force_reply=ui.PRICE_PLACEHOLDER,
                       chat_id=chat_id)


def route_reply(text, reply_to_text):
    """An answer to the Price check prompt becomes a /price command; a slash
    command typed as a reply is left alone."""
    t = (text or "").strip()
    if reply_to_text and ui.PRICE_PROMPT_MARK in reply_to_text and t and not t.startswith("/"):
        return "/price " + t
    return text


def handle_callback(cfg, runner, data, chat_id=None, message_id=None):
    """Button taps.

        ui:<section>      Home navigation, edits the message in place
        cmd:<action>      run a menu action
        st:TRIP:CITY      search stays for that trip, immediately

    Only ids and 3-letter codes travel in callback_data; the dates come from
    the Trips tab, never from the button.
    """
    parts = (data or "").split(":")

    if parts and parts[0] == "ui" and len(parts) == 2:
        name = parts[1]
        if name == "home":
            send_home(cfg, runner, chat_id, message_id)
            return None
        if name == "price":
            send_price_prompt(cfg, chat_id)
            return None
        if name == "help":
            text, btns = HELP, [[ui.HOME_BACK]]
        else:
            sec = ui.section(name, ROOT, chat_id=chat_id)
            if not sec:
                return "Unrecognised button."
            text, btns = sec
        if chat_id and message_id:
            telegram.edit_html(cfg, chat_id, message_id, text, btns)
        else:
            telegram.send_html(cfg, text, silent=True, buttons=btns, chat_id=chat_id)
        return None

    if parts and parts[0] == "cmd" and len(parts) == 2:
        act = parts[1]
        if act == "cancel":
            return runner.cancel()
        if act == "status":
            return status(cfg, runner)
        if act == "auto":
            rows = tasks.summary()
            telegram.send_html(cfg, fmt.auto_text(rows), buttons=fmt.auto_buttons(rows),
                               chat_id=chat_id)
            return None
        if act in JOBS:
            return runner.launch(act, chat_id=chat_id)
        return "Unrecognised button."

    # sw:<task key>:<0 off | 1 on | r run now | v refresh>
    if parts and parts[0] == "sw" and len(parts) == 3:
        key, act = parts[1], parts[2]
        note = ""
        if act in ("0", "1") and key in tasks.TASKS:
            ok, note = tasks.set_enabled(key, act == "1")
            log("task %s -> %s (%s)" % (key, act, ok))
        elif act == "r" and key in tasks.TASKS:
            # Launch through the runner, not Task Scheduler: a task-scheduler
            # process is invisible here and could not be cancelled.
            job = {"travel": "scan", "training": "training", "meals": "meals"}.get(key)
            if job in JOBS:
                note = runner.launch(job, chat_id=chat_id)
            else:
                ok, note = tasks.run_now(key)
            log("run now: %s" % key)
        rows = tasks.summary()
        text = fmt.auto_text(rows)
        if note:
            text += "\n\n<i>%s</i>" % telegram.esc(note)
        if chat_id and message_id:
            telegram.edit_html(cfg, chat_id, message_id, text, fmt.auto_buttons(rows))
        else:
            telegram.send_html(cfg, text, buttons=fmt.auto_buttons(rows), chat_id=chat_id)
        return None

    if len(parts) != 3 or parts[0] != "st":
        return "Unrecognised button."
    _, trip_id, city = parts
    if not re.fullmatch(r"T[0-9A-F]{6}", trip_id) or not re.fullmatch(r"[A-Z]{3}", city):
        return "Unrecognised button."

    trip = _trip_lookup(cfg, trip_id)
    if not trip:
        return ("That trip is no longer in the sheet \u2014 try "
                "<code>/stays %s 04-11.11 sea</code>" % city)
    try:
        date.fromisoformat(trip["out_date"])
        date.fromisoformat(trip["back_date"])
    except ValueError:
        return "That trip has odd dates."

    args = [city, "%s-%s" % (trip["out_date"], trip["back_date"])]
    label = ("\u23f3 Searching stays in <b>%s</b>\n%s \u2192 %s"
             % (places.label(cfg, city), trip["out_date"], trip["back_date"]))
    return runner.launch("stays", args, ack=label, chat_id=chat_id)


def main():
    # single-instance guard: bind a localhost port for the process lifetime
    guard = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        guard.bind(("127.0.0.1", SINGLETON_PORT))
    except OSError:
        print("listener already running; exiting")
        return
    guard.listen(1)

    cfg = config.load()
    tok = os.environ.get(cfg["telegram"]["bot_token_env"])
    allowed = set(telegram.allowed_chats(cfg))
    if not tok or not allowed:
        log("FATAL: TELEGRAM env vars not set")
        return

    runner = Runner(cfg)
    api = f"https://api.telegram.org/bot{tok}"
    set_menu(tok)

    # drop any backlog accumulated while offline
    offset = 0
    try:
        r = requests.get(f"{api}/getUpdates", params={"timeout": 0}, timeout=15).json()
        upd = r.get("result", [])
        if upd:
            offset = upd[-1]["update_id"] + 1
    except requests.RequestException:
        pass

    log(f"listener online (dropped backlog, offset={offset}, chats={len(allowed)})")
    try:
        sheets.log_run(cfg, "listener", "online", f"pid {os.getpid()}")
    except Exception:
        pass
    telegram.send_html(cfg, "\U0001f3a7 <i>Listener online</i>", silent=True)

    last_hb = time.time()
    backoff = 5

    while True:
        try:
            r = requests.get(f"{api}/getUpdates",
                             params={"timeout": POLL_TIMEOUT, "offset": offset},
                             timeout=POLL_TIMEOUT + 15).json()
            backoff = 5
            for u in r.get("result", []):
                offset = u["update_id"] + 1

                cb = u.get("callback_query")
                if cb:
                    chat_id = str(((cb.get("message") or {}).get("chat") or {}).get("id") or "")
                    if chat_id not in allowed:
                        log("ignored callback from foreign chat %s" % chat_id)
                        continue
                    telegram.answer_callback(cfg, cb.get("id"))
                    log("callback: %s" % str(cb.get("data"))[:48])
                    cmsg = cb.get("message") or {}
                    reply = handle_callback(cfg, runner, cb.get("data"),
                                            chat_id, cmsg.get("message_id"))
                    if reply:
                        telegram.send_html(cfg, reply, silent=True, chat_id=chat_id)
                    continue

                msg = u.get("message") or {}
                chat = str((msg.get("chat") or {}).get("id") or "")
                text = msg.get("text") or ""
                if not text:
                    continue
                if chat not in allowed:
                    log(f"ignored message from foreign chat {chat}")
                    continue
                text = route_reply(text, (msg.get("reply_to_message") or {}).get("text"))
                log(f"cmd: {text[:60]}")
                reply = handle_text(cfg, runner, text, chat)
                if reply:
                    telegram.send_html(cfg, reply, silent=True, chat_id=chat)

            if time.time() - last_hb > HEARTBEAT_SEC:
                last_hb = time.time()
                try:
                    sheets.log_run(cfg, "listener", "heartbeat", f"up {_uptime()}")
                except Exception:
                    pass

        except KeyboardInterrupt:
            log("stopped by user")
            return
        except Exception as e:
            log(f"poll error: {str(e)[:120]}; retry in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    main()
