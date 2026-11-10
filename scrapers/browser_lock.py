"""One owner of the bot's browser profile (.browser/market) at a time.

A Chromium profile can be opened by one process only. The nightly market scan
(jobs/market_watch.py) and the /amazon worker (jobs/amazon_search.py) both open it through
scrapers/market.Session, which takes this lock first and waits for it up to `wait_s`. A lock
left by a dead process is cleared. Platform-neutral (O_EXCL file + psutil), CLAUDE.md §6.
"""
import json
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class BrowserBusy(RuntimeError):
    """The browser stayed taken for the whole wait."""


def path(root=None):
    d = os.path.join(root or ROOT, ".browser", "market_data")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "browser.lock")


def _alive(pid):
    try:
        import psutil
        return psutil.pid_exists(int(pid))
    except Exception:  # noqa: BLE001 - unknown = treat as alive; a wrong clear would be worse
        return True


def holder(root=None):
    """{"pid", "since", "who"} of a live holder, or None."""
    try:
        with open(path(root), encoding="utf-8") as f:
            info = json.load(f)
    except (OSError, ValueError):
        return None
    return info if _alive(info.get("pid")) else None


def acquire(who, wait_s=0.0, root=None, poll_s=2.0, log=print):
    """Take the lock for this process or raise BrowserBusy after wait_s. Re-entrant for the
    same pid is not supported: one Session per process."""
    deadline = time.time() + wait_s
    told = False
    while True:
        try:
            fd = os.open(path(root), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            h = holder(root)
            if not h:
                try:
                    os.remove(path(root))          # left by a dead process
                except OSError:
                    pass
                continue
            if time.time() >= deadline:
                raise BrowserBusy("the bot's browser is in use by %s" % (h.get("who") or "another job"))
            if not told:
                log("  waiting for the browser (in use by %s)" % (h.get("who") or "another job"))
                told = True
            time.sleep(poll_s)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "since": time.time(), "who": who}, f)
        return


def release(root=None):
    """Remove the lock if this process holds it."""
    try:
        with open(path(root), encoding="utf-8") as f:
            mine = json.load(f).get("pid") == os.getpid()
    except (OSError, ValueError):
        return
    if mine:
        try:
            os.remove(path(root))
        except OSError:
            pass
