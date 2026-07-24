"""Read and toggle our own Windows scheduled tasks.

Deliberately narrow: only the task names in TASKS can be touched, and the key
is looked up in that dict rather than interpolated, so no text from a message
ever reaches the command line.

Uses schtasks.exe rather than PowerShell to avoid execution-policy issues.
"""
import re
import subprocess

TASKS = {
    "travel":   {"task": "FamilyAssistant-Travel",   "label": "Flight scan",
                 "toggle": True},
    "listener": {"task": "FamilyAssistant-Listener", "label": "Telegram listener",
                 "toggle": False},   # switching this off would cut the branch we sit on
    "training": {"task": "FamilyAssistant-Training", "label": "Training plan",
                 "toggle": True},
    "meals":    {"task": "FamilyAssistant-Meals",    "label": "Meal plan",
                 "toggle": True},
}

FIELDS = {
    "status": ("status",),
    "next run time": ("next_run",),
    "last run time": ("last_run",),
    "last result": ("last_result",),
    "schedule type": ("schedule",),
    "start time": ("start_time",),
}


def _run(args, timeout=25):
    try:
        p = subprocess.run(["schtasks"] + args, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="ignore")
        return p.returncode, (p.stdout or ""), (p.stderr or "")
    except Exception as e:
        return 1, "", str(e)


def query(key):
    """Returns {'exists','status','next_run','last_run','last_result',...}."""
    meta = TASKS.get(key)
    if not meta:
        return {"exists": False}
    rc, out, _ = _run(["/query", "/tn", meta["task"], "/fo", "LIST", "/v"])
    if rc != 0 or not out.strip():
        return {"exists": False, "label": meta["label"], "toggle": meta["toggle"]}

    info = {"exists": True, "label": meta["label"], "toggle": meta["toggle"]}
    for line in out.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip().lower(), v.strip()
        for prefix, (field,) in FIELDS.items():
            if k.startswith(prefix) and field not in info:
                info[field] = v
    st = (info.get("status") or "").lower()
    info["enabled"] = "disabled" not in st
    info["running"] = "running" in st
    return info


def set_enabled(key, enabled):
    """Enable or disable one of our tasks. Returns (ok, message)."""
    meta = TASKS.get(key)
    if not meta:
        return False, "Unknown task."
    if not meta["toggle"]:
        return False, "%s can't be switched off from here." % meta["label"]
    flag = "/enable" if enabled else "/disable"
    rc, out, err = _run(["/change", "/tn", meta["task"], flag])
    if rc == 0:
        return True, "%s %s." % (meta["label"], "enabled" if enabled else "disabled")
    msg = (err or out).strip().splitlines()[-1] if (err or out).strip() else "failed"
    if "denied" in msg.lower():
        msg = "access denied \u2014 run the change on the PC as administrator"
    return False, "Could not change %s: %s" % (meta["label"], msg[:120])


def run_now(key):
    meta = TASKS.get(key)
    if not meta:
        return False, "Unknown task."
    rc, out, err = _run(["/run", "/tn", meta["task"]])
    return (rc == 0), ("Started %s." % meta["label"] if rc == 0
                       else "Could not start: %s" % ((err or out).strip()[:120]))


def end(key):
    """Tell Task Scheduler to stop a task it started."""
    meta = TASKS.get(key)
    if not meta:
        return False
    rc, _, _ = _run(["/end", "/tn", meta["task"]])
    return rc == 0


def _short_dt(s):
    """'24/07/2026 08:00:00' -> '24/07 08:00'"""
    if not s or s.upper().startswith("N/A"):
        return "\u2014"
    m = re.match(r"(\d{1,2}[/.-]\d{1,2})[/.-]\d{2,4}\s+(\d{1,2}:\d{2})", s)
    return "%s %s" % (m.group(1), m.group(2)) if m else s[:16]


def summary():
    """Ordered list of task info dicts for display."""
    out = []
    for key in ("travel", "listener", "training", "meals"):
        info = query(key)
        info["key"] = key
        info["next_short"] = _short_dt(info.get("next_run"))
        info["last_short"] = _short_dt(info.get("last_run"))
        out.append(info)
    return out
