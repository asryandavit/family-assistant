"""One Chrome job at a time (docs/briefs/CHINA_SEARCH.md §4.4).

Jobs are JSON files in .browser/china_data/queue/, named so they sort oldest first. One
worker process (jobs/china_search.py) drains the queue; a lock file with its pid makes it
the only one. A lock left by a dead process is cleared. Searches from both chats and the
login check share this queue, so they never overlap; a second request waits and is told its
place. Platform-neutral: psutil for "is this pid alive", no Windows-only calls here.
"""
import json
import os
import subprocess
import sys
import time
import uuid

from china import ROOT, data_dir

LOCK = "worker.lock"


def qdir(root=None):
    d = os.path.join(data_dir(root), "queue")
    os.makedirs(d, exist_ok=True)
    return d


def new_id():
    return uuid.uuid4().hex[:8]


def pending(root=None):
    d = qdir(root)
    return sorted(f for f in os.listdir(d) if f.endswith(".json"))


def enqueue(job, root=None):
    """Write a job; return its place among waiting jobs (1 = next)."""
    job = dict(job)
    job.setdefault("job", new_id())
    job.setdefault("queued_utc", time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()))
    name = "%d_%s.json" % (time.time_ns(), job["job"])
    tmp = os.path.join(qdir(root), name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False)
    os.replace(tmp, os.path.join(qdir(root), name))
    return pending(root).index(name) + 1


def _read(path):
    """JSON from a file, closed before returning (Windows cannot delete an open file)."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _drop(path):
    try:
        os.remove(path)
    except OSError:
        pass


def pop(root=None):
    """The oldest job (removed from the queue), or None."""
    for name in pending(root):
        path = os.path.join(qdir(root), name)
        try:
            job = _read(path)
        except (OSError, ValueError):
            _drop(path)                    # unreadable job: drop it, never loop on it
            continue
        _drop(path)
        return job
    return None


def remove_for_chat(chat_id, root=None):
    """/cancel: drop this chat's waiting jobs. Returns how many."""
    n = 0
    for name in pending(root):
        path = os.path.join(qdir(root), name)
        try:
            mine = str(_read(path).get("chat_id")) == str(chat_id)
        except (OSError, ValueError):
            continue
        if mine:
            _drop(path)
            n += 1
    return n


def _alive(pid):
    try:
        import psutil
        return psutil.pid_exists(int(pid))
    except Exception:
        return False


def lock_path(root=None):
    return os.path.join(data_dir(root), LOCK)


def running(root=None):
    """The worker's lock info {"pid", "since", "job"} if a live worker holds it, else None."""
    try:
        with open(lock_path(root), encoding="utf-8") as f:
            info = json.load(f)
    except (OSError, ValueError):
        return None
    return info if _alive(info.get("pid")) else None


def acquire(root=None):
    """Take the worker lock for this process; False if another live worker has it."""
    path = lock_path(root)
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if running(root):
                return False
            try:
                os.remove(path)             # stale lock from a dead worker
            except OSError:
                return False
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "since": time.time(), "job": None}, f)
        return True
    return False


def mark(job_id, root=None):
    """Record the job the worker is on (for the 'queued behind' message)."""
    try:
        with open(lock_path(root), encoding="utf-8") as f:
            info = json.load(f)
        info["job"] = job_id
        info["job_since"] = time.time()
        with open(lock_path(root), "w", encoding="utf-8") as f:
            json.dump(info, f)
    except (OSError, ValueError):
        pass


def release(root=None):
    try:
        mine = _read(lock_path(root)).get("pid") == os.getpid()
    except (OSError, ValueError):
        return
    if mine:
        _drop(lock_path(root))


def start_worker(root=None, popen=subprocess.Popen):
    """Start jobs/china_search.py unless a live worker is already draining the queue."""
    if running(root):
        return False
    popen([sys.executable, os.path.join(root or ROOT, "jobs", "china_search.py")],
          cwd=root or ROOT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True
