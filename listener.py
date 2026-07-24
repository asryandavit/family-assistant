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

from lib import config, fmt, parse_cmd, sheets, tasks, telegram  # noqa: E402

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
}

CITY_RE = re.compile(r"^[A-Za-z][A-Za-z .\-]{1,28}$")


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
             % (telegram.esc(q["city"]), q["checkin"], q["checkout"], q["nights"],
                " \u00b7 " + telegram.esc(", ".join(flags)) if flags else ""))
    return args, label

HELP = ("\U0001f9ed <b>Commands</b>\n"
        "/scan \u2014 run the flight scan now\n"
        "/digest \u2014 scan + send the full digest\n"
        "/stays &lt;city&gt; &lt;dates&gt; [keywords] \u2014 search accommodation\n"
        "/auto \u2014 automation status, pause/enable\n"
        "/menu \u2014 buttons for everything\n"
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


class Runner:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.current = None
        self.started = None
        self.proc = None
        self.cancelled = False

    def launch(self, name, extra_args=None, ack=None):
        job = dict(JOBS[name])
        if extra_args:
            job["args"] = job["args"] + list(extra_args)
        if not self.lock.acquire(blocking=False):
            return (f"\u26a0\ufe0f <b>{self.current}</b> is already running "
                    f"(started {int(time.time() - self.started)}s ago). Queued nothing.")
        self.current, self.started = name, time.time()
        self.cancelled = False
        threading.Thread(target=self._run, args=(name, job), daemon=True).start()
        return (ack or job["ack"]) + "\n<i>/cancel to stop</i>"

    def _run(self, name, job):
        try:
            proc = subprocess.Popen([sys.executable, *job["args"]], cwd=ROOT,
                                    creationflags=CREATE_NO_WINDOW)
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
    cmds = [{"command": "scan", "description": "Run the flight scan now"},
            {"command": "digest", "description": "Scan + full digest"},
            {"command": "stays", "description": "Search stays: /stays LCA 04-11.11 sea"},
            {"command": "auto", "description": "Automation status and switches"},
            {"command": "menu", "description": "Buttons for everything"},
            {"command": "cancel", "description": "Stop the running job"},
            {"command": "status", "description": "Listener health"},
            {"command": "help", "description": "List commands"}]
    try:
        requests.post(f"https://api.telegram.org/bot{tok}/setMyCommands",
                      json={"commands": cmds}, timeout=15)
    except requests.RequestException:
        pass


def handle_text(cfg, runner, text):
    cmd = text.strip().split()[0].lower().lstrip("/").split("@")[0] if text.strip() else ""
    if cmd == "stays":
        args, msg = _safe_stays_args(cfg, text)
        if not args:
            return msg
        return runner.launch("stays", args, ack=msg)
    if cmd in JOBS:
        return runner.launch(cmd)
    if cmd == "cancel":
        return runner.cancel()
    if cmd == "menu":
        telegram.send_html(cfg, MENU_TEXT, buttons=menu_buttons())
        return None
    if cmd == "auto":
        rows = tasks.summary()
        telegram.send_html(cfg, fmt.auto_text(rows), buttons=fmt.auto_buttons(rows))
        return None
    if cmd == "status":
        return status(cfg, runner)
    if cmd in ("help", "start"):
        return HELP
    return None  # unknown text: stay silent


def _trip_lookup(cfg, trip_id):
    """Find a trip row by id in the Trips tab."""
    for r in reversed(sheets.read_all(cfg, "Trips")):
        if len(r) > 5 and r[1] == trip_id:
            return {"id": r[1], "kind": r[2], "route": r[3],
                    "out_date": r[4], "back_date": r[5]}
    return None


MENU_TEXT = ("\U0001f9ed <b>Menu</b>\n"
             "<i>Tap a button, or type a command directly.</i>\n\n"
             "Stays need a city and dates, so type those:\n"
             "<code>/stays LCA 04-11.11 sea center</code>")


def menu_buttons():
    return [
        [("\u2708\ufe0f Scan flights", "cmd:scan"),
         ("\U0001f4ca Digest", "cmd:digest")],
        [("\U0001f3a7 Status", "cmd:status"),
         ("\U0001f6d1 Cancel", "cmd:cancel")],
        [("\u2699\ufe0f Automation", "cmd:auto")],
    ]


def handle_callback(cfg, runner, data, chat_id=None, message_id=None):
    """Button taps.

        cmd:<action>      run a menu action
        st:TRIP:CITY      search stays for that trip, immediately

    Only ids and 3-letter codes travel in callback_data; the dates come from
    the Trips tab, never from the button.
    """
    parts = (data or "").split(":")

    if parts and parts[0] == "cmd" and len(parts) == 2:
        act = parts[1]
        if act == "cancel":
            return runner.cancel()
        if act == "status":
            return status(cfg, runner)
        if act == "auto":
            rows = tasks.summary()
            telegram.send_html(cfg, fmt.auto_text(rows), buttons=fmt.auto_buttons(rows))
            return None
        if act in JOBS:
            return runner.launch(act)
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
                note = runner.launch(job)
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
            telegram.send_html(cfg, text, buttons=fmt.auto_buttons(rows))
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
             % (city, trip["out_date"], trip["back_date"]))
    return runner.launch("stays", args, ack=label)


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
    allowed = str(os.environ.get(cfg["telegram"]["chat_id_env"]) or "")
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

    log(f"listener online (dropped backlog, offset={offset})")
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
                    if chat_id != allowed:
                        log("ignored callback from foreign chat %s" % chat_id)
                        continue
                    telegram.answer_callback(cfg, cb.get("id"))
                    log("callback: %s" % str(cb.get("data"))[:48])
                    cmsg = cb.get("message") or {}
                    reply = handle_callback(cfg, runner, cb.get("data"),
                                            chat_id, cmsg.get("message_id"))
                    if reply:
                        telegram.send_html(cfg, reply)
                    continue

                msg = u.get("message") or {}
                chat = str((msg.get("chat") or {}).get("id") or "")
                text = msg.get("text") or ""
                if not text:
                    continue
                if chat != allowed:
                    log(f"ignored message from foreign chat {chat}")
                    continue
                log(f"cmd: {text[:60]}")
                reply = handle_text(cfg, runner, text)
                if reply:
                    telegram.send_html(cfg, reply)

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
