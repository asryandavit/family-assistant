"""Keep the China worker alive and its failures visible (decision 104, CLAUDE.md §5).

On 2026-11-10 a search queued at 00:45 waited ~22 h: the worker started for it died on import,
its output went nowhere, and nothing ever started a worker again.

    ensure_worker()  jobs waiting and no live worker -> start one and watch it. Called on every
                     enqueue (china/bot.py) and when the listener starts. First reports a job a
                     dead worker left unfinished.
    watch_proc()     waits for the worker (a daemon thread in the listener) -> check_exit()
    check_exit()     the worker exited: a job left marked as in progress, or a crash before it
                     took any job, is told in one plain line to the person who asked and to the
                     owner (one message when they are the same). A job that crashed the worker
                     before it started is dropped so it cannot crash it again and again.
    drop_if_stale()  the worker drops a job stranded in the queue (queue.is_stale) with
                     "Your China search for … didn't start — please send it again."
"""
import re
import subprocess
import threading

from china import queue
from lib import telegram

_lock = threading.Lock()
_unreported = set()          # workers started here whose exit has not been checked yet
TOKEN_RE = re.compile(r"bot\d+:[\w-]+")


def label(job):
    """What the person asked for, in their words (for the one-line messages)."""
    kind = job.get("kind") or "search"
    if kind == "reviews":
        return "reviews"
    if kind == "photo":
        return "your photo" + (f" ({job['note']})" if job.get("note") else "")
    return f"“{(job.get('description') or 'your item')[:80]}”"


def err_tail(root=None, n=200):
    """The last non-empty line of worker.err, bot token removed."""
    try:
        with open(queue.err_path(root), encoding="utf-8", errors="replace") as f:
            lines = [ln.strip() for ln in f.read()[-8000:].splitlines() if ln.strip()]
    except OSError:
        return ""
    return TOKEN_RE.sub("bot<token>", lines[-1])[:n] if lines else ""


def _tell(cfg, tg, chat_id, line, owner_line):
    """One plain line to the asker; the owner gets the technical line too (once if same)."""
    owner = (tg.allowed_chats(cfg) or [None])[0]
    if chat_id and str(chat_id) != str(owner):
        tg.send_html(cfg, tg.esc(line), silent=False, chat_id=chat_id)
        tg.notify(cfg, "⚠️ SYSTEM: " + owner_line)
    else:
        tg.notify(cfg, line + "\n⚠️ SYSTEM: " + owner_line)


def check_exit(cfg, root, returncode, tg=telegram):
    """Called when no worker is alive any more (it exited, or was found dead at startup)."""
    why = err_tail(root) or f"exit code {returncode}"
    cur = queue.read_current(root)
    if cur:
        queue.clear_current(root)
        _tell(cfg, tg, cur.get("chat_id"),
              f"⚠️ Your China search for {label(cur)} stopped before it finished — please send it again.",
              f"China worker died during job {cur.get('job')}: {why}")
        return "interrupted"
    if returncode:
        job = queue.pop(root)                      # the job it was started for: never loop on it
        if job:
            _tell(cfg, tg, job.get("chat_id"),
                  f"⚠️ Your China search for {label(job)} didn't start — please send it again.",
                  f"China worker crashed before job {job.get('job')}: {why}")
        else:
            tg.notify(cfg, f"⚠️ SYSTEM: China worker crashed: {why}")
        return "crashed"
    return None


def watch_proc(proc, cfg, root, tg=telegram):
    """Wait for the worker; report how it ended; start a new one if jobs are still waiting."""
    rc = proc.wait()
    with _lock:
        if not queue.running(root):
            check_exit(cfg, root, rc, tg)
        _unreported.discard(proc)
    if queue.pending(root):
        ensure_worker(cfg, root, tg=tg)


def ensure_worker(cfg, root, popen=subprocess.Popen, tg=telegram, thread=True):
    """Start the worker when jobs wait and none is alive; return the process or None."""
    with _lock:
        if queue.running(root) or _unreported:    # alive, or its exit is being checked now
            return None
        if queue.read_current(root):               # a worker died mid-job while nobody watched
            check_exit(cfg, root, None, tg)
        if not queue.pending(root):
            return None
        proc = queue.start_worker(root, popen=popen)
        if proc and thread:
            _unreported.add(proc)
    if proc and thread:
        threading.Thread(target=watch_proc, args=(proc, cfg, root, tg), daemon=True,
                         name="china-worker-watch").start()
    return proc or None


def drop_if_stale(cfg, root, job, worker_started, tg=telegram, minutes=None, now=None):
    """In the worker, before running a job: a stranded job is dropped and its chat told."""
    if minutes is None:
        from china import search
        minutes = search.load_cfg(root).get("stale_job_minutes", 30)
    if not queue.is_stale(job, worker_started, minutes, now):
        return False
    _tell(cfg, tg, job.get("chat_id"),
          f"Your China search for {label(job)} didn't start — please send it again.",
          f"/china job {job.get('job')} queued {job.get('queued_utc')} was never started "
          "(no worker was running); dropped.")
    return True
