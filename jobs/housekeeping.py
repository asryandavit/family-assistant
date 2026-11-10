"""Nightly housekeeping (decision 103): nothing the bot writes grows without limit, and the
owner hears before a disk fills.

    python jobs/housekeeping.py              clean, print and log the one-line report
    python jobs/housekeeping.py --send       ...and message the owner if a disk is low or the job fails
    python jobs/housekeeping.py --dry-run    measure only: what would be freed, nothing deleted

What it does, each run (config_housekeeping.json):
1. In each bot browser profile under .browser/ it deletes only Chrome's cache folders
   (`cache_dirs`). Logins live in Cookies, Login Data, Local Storage, IndexedDB, Network and
   Preferences, which are never deleted: a cache path naming one of them is refused.
   A profile is cleaned only when nothing uses it: the market profile through the same
   cross-process lock the nightly scan and /amazon take (scrapers/browser_lock, no wait);
   every profile through a live check (a process started with --user-data-dir=<profile>, or
   Chrome's own `lockfile` / `SingletonLock` held). In use -> skipped and said in the report.
   Only folders under .browser/ can be named, so the owner's real Chrome is out of reach.
2. Rotates our append-only logs over `log_max_bytes`, keeping `log_keep` old copies
   (lib/logfile; the listener's open log is copied and truncated).
3. Removes leftover .tmp files in .browser/miniapp_inbox older than `inbox_tmp_max_age_h`.
4. Checks free space on the repo's disk, the home disk and the temp disk; below
   `min_free_gb` the owner gets one plain message (--send).
5. Writes one line to .browser/housekeeping.log and its state to .browser/housekeeping.json
   (read by selfcheck.py).
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from datetime import UTC, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib import logfile

JOB = "housekeeping"
GB = 1024 ** 3
MB = 1024 ** 2
# Folder/file names that hold a profile's sign-ins and settings. A configured cache path that
# contains any of these (any part, any case) is refused, so a config typo cannot log the bot out.
PROTECTED = {"cookies", "cookies-journal", "login data", "login data-journal",
             "login data for account", "local storage", "indexeddb", "network", "preferences",
             "secure preferences", "session storage", "sessions", "web data", "local state",
             "history", "extension state", "sync data"}
# Profiles that have a cross-process owner lock (scrapers/browser_lock): cleaned only while
# housekeeping holds it, so the nightly scan or /amazon cannot open the profile mid-clean.
LOCKED_PROFILES = {"market"}
DEFAULTS = {"profiles": [], "cache_dirs": [], "logs": [], "log_max_bytes": 2_000_000,
            "log_keep": 3, "inbox_tmp_max_age_h": 24, "min_free_gb": 5}


def load_cfg(root=ROOT):
    cfg = dict(DEFAULTS)
    try:
        with open(os.path.join(root, "config_housekeeping.json"), encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items() if not k.startswith("_")})
    except (OSError, ValueError):
        pass
    return cfg


def browser_dir(root=ROOT):
    return os.path.join(root, ".browser")


def _canon(p):
    return os.path.normcase(os.path.realpath(os.path.abspath(p)))


def _inside(child, parent):
    c, p = _canon(child), _canon(parent)
    return c != p and c.startswith(p.rstrip("\\/") + os.sep)


# ---------------------------------------------------------------- path guards
def profile_path(root, name):
    """The profile folder for a configured name, or ValueError. Only a plain folder name
    directly under .browser/ is accepted; nothing outside .browser/ can be reached."""
    if not isinstance(name, str) or not name or name in (".", "..") \
            or any(s in name for s in ("/", "\\", ":")):
        raise ValueError(f"profile {name!r} is not a plain folder name under .browser/")
    p = os.path.join(browser_dir(root), name)
    if os.path.islink(p) or not _inside(p, browser_dir(root)):
        raise ValueError(f"profile {name!r} resolves outside .browser/")
    return p


def cache_path(profile, rel):
    """The cache folder inside a profile, or ValueError for anything that could hold logins."""
    if not isinstance(rel, str) or not rel or os.path.isabs(rel) or ":" in rel \
            or rel.startswith(("/", "\\")):
        raise ValueError(f"cache dir {rel!r} must be a relative path")
    parts = [x for x in rel.replace("\\", "/").split("/") if x]
    if not parts or any(x in (".", "..") for x in parts):
        raise ValueError(f"cache dir {rel!r} must not use . or ..")
    bad = [x for x in parts if x.lower() in PROTECTED]
    if bad:
        raise ValueError(f"cache dir {rel!r} names {bad[0]!r}, which holds sign-ins or settings")
    p = os.path.join(profile, *parts)
    if not _inside(p, profile):
        raise ValueError(f"cache dir {rel!r} resolves outside the profile")
    return p


# ---------------------------------------------------------------- in-use checks
def _processes():
    """[(pid, [cmdline...])] of running processes, or None when psutil is missing."""
    try:
        import psutil
    except ImportError:
        return None
    out = []
    for p in psutil.process_iter(["pid", "cmdline"]):
        info = getattr(p, "info", None) or {}
        out.append((info.get("pid"), info.get("cmdline") or []))
    return out


def chrome_holders(profile, procs):
    """Pids of processes started with --user-data-dir=<this profile>."""
    want = _canon(profile)
    pids = []
    for pid, cmd in procs:
        for a in cmd:
            if isinstance(a, str) and a.startswith("--user-data-dir=")                     and _canon(a.split("=", 1)[1].strip('"')) == want:
                pids.append(pid)
                break
    return pids


def _pid_alive(pid):
    try:
        import psutil
        return psutil.pid_exists(int(pid))
    except Exception:  # noqa: BLE001 - unknown = alive; a wrong clean is worse than a skip
        return True


def lock_held(profile):
    """Chrome's own profile lock. Windows: `lockfile` exists while Chrome runs and cannot be
    opened (measured 2026-11-10: PermissionError; removed on a clean close, a crash leaves an
    openable one). macOS/Linux: `SingletonLock` is a symlink to '<host>-<pid>'."""
    lf = os.path.join(profile, "lockfile")
    if os.path.exists(lf):
        try:
            fd = os.open(lf, os.O_RDONLY)
            os.close(fd)
        except PermissionError:
            return True
        except OSError:
            pass
    sl = os.path.join(profile, "SingletonLock")
    if os.path.islink(sl):
        try:
            pid = os.readlink(sl).rsplit("-", 1)[1]
            return _pid_alive(pid)
        except (OSError, IndexError):
            return True
    return False


def in_use(profile, procs):
    """A sentence saying why the profile is busy, or None when it is free."""
    if lock_held(profile):
        return "in use (Chrome's profile lock is held)"
    if procs is None:
        return "not checked (psutil missing), left alone"
    pids = chrome_holders(profile, procs)
    if pids:
        return "in use (browser pid {})".format(", ".join(str(p) for p in pids[:3]))
    return None


# ---------------------------------------------------------------- cleaning
def dir_size(path):
    total = 0
    for dp, dns, fns in os.walk(path, followlinks=False):
        for fn in fns:
            try:
                total += os.lstat(os.path.join(dp, fn)).st_size
            except OSError:
                pass
    return total


def _rmtree(path, errors):
    def onexc(func, p, exc):
        errors.append(f"{os.path.basename(p)}: {exc.__class__.__name__}")
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=onexc)
    else:  # pragma: no cover - older Python
        shutil.rmtree(path, onerror=lambda f, p, e: onexc(f, p, e[1]))


def clean_profile(root, name, cache_dirs, procs, dry_run=False, lock=None, log=print):
    """{"name", "status", "freed", "would_free", "errors"}; status is "cleaned", "missing",
    "refused: ..." or "in use ..."."""
    res = {"name": name, "status": "", "freed": 0, "would_free": 0, "errors": []}
    try:
        prof = profile_path(root, name)
        targets = [cache_path(prof, rel) for rel in cache_dirs]
    except ValueError as e:
        res["status"] = f"refused: {e}"
        return res
    if not os.path.isdir(prof):
        res["status"] = "missing"
        return res
    if lock is None and name in LOCKED_PROFILES:
        from scrapers import browser_lock as lock
    held = False
    try:
        if name in LOCKED_PROFILES:
            try:
                lock.acquire(JOB, 0, root, log=log)
                held = True
            except lock.BrowserBusy as e:
                res["status"] = f"in use ({e})"
                return res
        why = in_use(prof, procs)
        if why:
            res["status"] = why
            return res
        for t in targets:
            if not os.path.isdir(t) or os.path.islink(t):
                continue
            size = dir_size(t)
            res["would_free"] += size
            if dry_run:
                continue
            if lock_held(prof):            # a browser started meanwhile: stop here
                res["status"] = "in use (a browser started during cleaning), stopped"
                return res
            _rmtree(t, res["errors"])
            res["freed"] += size - (dir_size(t) if os.path.exists(t) else 0)
        res["status"] = "measured" if dry_run else "cleaned"
        return res
    finally:
        if held:
            lock.release(root)


def rotate_logs(root, logs, max_bytes, keep, dry_run=False):
    """Relative names of the logs that were (or would be) rotated."""
    done = []
    for rel in logs:
        p = os.path.join(root, *rel.replace("\\", "/").split("/"))
        if not _inside(p, browser_dir(root)):
            continue                                   # only our own logs under .browser/
        try:
            big = os.path.getsize(p) > max_bytes
        except OSError:
            continue
        if big and (dry_run or logfile.rotate(p, max_bytes, keep)):
            done.append(rel)
    return done


def clean_inbox_tmp(root, max_age_h, now=None, dry_run=False):
    d = os.path.join(browser_dir(root), "miniapp_inbox")
    cutoff = (now or time.time()) - max_age_h * 3600
    n = 0
    try:
        names = os.listdir(d)
    except OSError:
        return 0
    for fn in names:
        p = os.path.join(d, fn)
        try:
            if fn.endswith(".tmp") and os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                if not dry_run:
                    os.remove(p)
                n += 1
        except OSError:
            pass
    return n


# ---------------------------------------------------------------- disks
def disks(root=ROOT, paths=None):
    """[{"label", "free", "total"}] for the disks holding the repo, the home folder and the
    temp folder (Chrome, Claude and Windows caches live on the home disk), one row per disk."""
    seen, out = set(), []
    for p in paths or (root, os.path.expanduser("~"), tempfile.gettempdir()):
        try:
            drive = os.path.splitdrive(os.path.abspath(p))[0].upper()
            key = drive or os.stat(p).st_dev
            if key in seen:
                continue
            u = shutil.disk_usage(p)
        except OSError:
            continue
        seen.add(key)
        out.append({"label": drive or p, "free": u.free, "total": u.total})
    return out


def low_disks(rows, min_free_gb):
    return [d for d in rows if d["free"] < min_free_gb * GB]


def disk_message(low, min_free_gb):
    parts = ", ".join("{} {:.1f} GB free".format(d["label"], d["free"] / GB) for d in low)
    return (f"⚠️ Disk space is low on the PC: {parts} (the warning starts below {min_free_gb:g} GB). "
            "Free some space on that disk before the bot's jobs and browsers start failing.")


# ---------------------------------------------------------------- report
def _mb(n):
    return "%.1f MB" % (n / MB)


def report_line(profiles, rotated, tmp_removed, disk_rows, dry_run=False):
    key = "would_free" if dry_run else "freed"
    total = sum(p[key] for p in profiles)
    done = ["{} {}".format(p["name"], _mb(p[key])) for p in profiles
            if p["status"] in ("cleaned", "measured") and p[key]]
    skipped = ["{} {}".format(p["name"], p["status"]) for p in profiles
               if p["status"] not in ("cleaned", "measured", "missing")]
    errs = sum(len(p["errors"]) for p in profiles)
    verb = "would free" if dry_run else "freed"
    bits = ["{} {} ({})".format(verb, _mb(total), ", ".join(done) or "nothing to clean")]
    if skipped:
        bits.append("skipped: " + "; ".join(skipped))
    if errs:
        bits.append(f"{errs} file(s) could not be deleted")
    bits.append("logs rotated: " + (", ".join(r.replace("\\", "/").split(".browser/", 1)[-1]
                                             for r in rotated) or "none"))
    bits.append(f"inbox .tmp removed: {tmp_removed}")
    bits.append("disks: " + (", ".join("{} {:.1f} GB free".format(d["label"], d["free"] / GB)
                                       for d in disk_rows) or "unknown"))
    return " · ".join(bits)


def log(msg, root=ROOT, cfg=None):
    cfg = cfg or DEFAULTS
    line = "{} {}".format(datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    logfile.append(os.path.join(browser_dir(root), "housekeeping.log"), line,
                   cfg.get("log_max_bytes", 2_000_000), cfg.get("log_keep", 3))


def save_state(root, state):
    p = os.path.join(browser_dir(root), "housekeeping.json")
    tmp = p + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=1)
        os.replace(tmp, p)
    except OSError:
        pass


def load_state(root=ROOT):
    try:
        with open(os.path.join(browser_dir(root), "housekeeping.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def run(root=ROOT, cfg=None, send=False, dry_run=False, procs="live", notify=None,
        disk_paths=None, lock=None):
    """One housekeeping pass. Returns the state dict that is also saved."""
    cfg = cfg or load_cfg(root)
    if procs == "live":
        procs = _processes()
    profiles = [clean_profile(root, n, cfg["cache_dirs"], procs, dry_run, lock=lock,
                              log=lambda m: None)
                for n in cfg["profiles"]]
    rotated = rotate_logs(root, cfg["logs"], cfg["log_max_bytes"], cfg["log_keep"], dry_run)
    tmp_removed = clean_inbox_tmp(root, cfg["inbox_tmp_max_age_h"], dry_run=dry_run)
    rows = disks(root, disk_paths)
    low = low_disks(rows, cfg["min_free_gb"])
    line = report_line(profiles, rotated, tmp_removed, rows, dry_run)
    if low and send and notify:
        notify(disk_message(low, cfg["min_free_gb"]))     # tell before writing state
    log(line + (" · LOW DISK warned" if low and send else
                " · LOW DISK" if low else ""), root, cfg)
    state = {"last_run_utc": datetime.now(UTC).isoformat(timespec="seconds"),
             "dry_run": dry_run, "line": line,
             "freed_bytes": sum(p["freed"] for p in profiles),
             "profiles": profiles, "rotated": rotated, "tmp_removed": tmp_removed,
             "disks": rows, "low": [d["label"] for d in low]}
    if not dry_run:
        save_state(root, state)
    return state


def main(argv=None):
    ap = argparse.ArgumentParser(description="Nightly housekeeping (decision 103).")
    ap.add_argument("--send", action="store_true",
                    help="message the owner when a disk is low or the job fails")
    ap.add_argument("--dry-run", action="store_true", help="measure only, delete nothing")
    a = ap.parse_args(argv)
    notify = None
    if a.send:
        from lib import config, telegram
        tcfg = config.load()
        notify = lambda text: telegram.notify(tcfg, text)
    try:
        run(send=a.send, dry_run=a.dry_run, notify=notify)
    except Exception as e:  # noqa: BLE001 - fail loudly to the owner
        log("CRASH {}".format(traceback.format_exc().replace("\n", " | ")))
        if notify:
            notify(f"⚠️ SYSTEM: housekeeping failed: {str(e)[:200]}. See .browser\\housekeeping.log.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
