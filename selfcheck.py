"""Family-assistant repo self-check.

Run from the repo root:   python selfcheck.py

Verifies structure, imports, config keys, secrets, gitignore coverage, scheduled
tasks, environment variables and (optionally) Sheets connectivity. Prints a
verdict; never modifies anything. Secret VALUES are never printed.
"""
import importlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

OK, WARN, BAD = "  ok  ", " warn ", " FAIL "
issues, warnings = [], []


def line(status, text, detail=""):
    print("[%s] %-46s %s" % (status, text, detail))
    if status == BAD:
        issues.append(text)
    elif status == WARN:
        warnings.append(text)


def header(t):
    print("\n" + t)
    print("-" * 72)


# ----------------------------------------------------------------- structure
REQUIRED = {
    "": ["config.json", "areas.json", "requirements.txt", ".gitignore", "listener.py"],
    "lib": ["__init__.py", "config.py", "sheets.py", "telegram.py", "claude.py", "fx.py",
            "parse_wizz.py", "parse_stays.py", "parse_cmd.py", "movement.py", "trips.py",
            "score_stays.py", "fmt.py", "tasks.py", "stations.py"],
    "scrapers": ["__init__.py", "wizz_fare_finder.py", "stays.py"],
    "jobs": ["__init__.py", "travel_scan.py", "stays_scan.py"],
    "prompts": ["travel_analysis.md"],
}
OPTIONAL = {
    "": ["README.md", "stations.json", "ARCHITECTURE.md"],
    "jobs": ["training.py", "meals.py"],
    "prompts": ["training.md", "meals.md", "ondemand_deepdive.md"],
    "scheduler": ["register-listener.ps1", "register-tasks.ps1"],
}


def check_structure():
    header("STRUCTURE")
    for folder, files in REQUIRED.items():
        for f in files:
            p = os.path.join(ROOT, folder, f)
            rel = os.path.join(folder, f) if folder else f
            line(OK if os.path.exists(p) else BAD, rel,
                 "" if os.path.exists(p) else "MISSING (required)")
    for folder, files in OPTIONAL.items():
        for f in files:
            p = os.path.join(ROOT, folder, f)
            rel = os.path.join(folder, f) if folder else f
            if os.path.exists(p):
                line(OK, rel, "optional, present")
            else:
                line(WARN, rel, "optional, absent")


def check_duplicates():
    header("DUPLICATE / STALE FILES")
    # parse_stays.py legitimately exists in lib/ (imported) and may ALSO sit at the
    # root as the offline diagnostic runner. Two copies drift apart silently.
    root_copy = os.path.join(ROOT, "parse_stays.py")
    lib_copy = os.path.join(ROOT, "lib", "parse_stays.py")
    if os.path.exists(root_copy) and os.path.exists(lib_copy):
        same = (open(root_copy, encoding="utf-8", errors="ignore").read() ==
                open(lib_copy, encoding="utf-8", errors="ignore").read())
        line(WARN, "parse_stays.py in root AND lib",
             "identical" if same else "DIFFERENT - root copy is stale")
    else:
        line(OK, "no parse_stays duplication", "")

    diagnostics = [f for f in ("debug_wizz.py", "debug_stays.py", "debug_stays2.py",
                               "peek_stays.py", "extract_stays.py")
                   if os.path.exists(os.path.join(ROOT, f))]
    line(OK, "diagnostic tools kept at root", ", ".join(diagnostics) or "none")


# ------------------------------------------------------------------- imports
def check_imports():
    header("IMPORTS")
    mods = ["lib.config", "lib.sheets", "lib.telegram", "lib.claude", "lib.fx",
            "lib.parse_wizz", "lib.parse_stays", "lib.parse_cmd", "lib.movement",
            "lib.trips", "lib.score_stays", "lib.fmt", "lib.tasks", "lib.stations",
            "scrapers.wizz_fare_finder", "scrapers.stays"]
    for m in mods:
        try:
            importlib.import_module(m)
            line(OK, m, "")
        except Exception as e:
            line(BAD, m, "%s: %s" % (type(e).__name__, str(e)[:60]))

    # jobs are scripts; import them to prove their dependencies resolve
    for m in ("jobs.travel_scan", "jobs.stays_scan"):
        try:
            importlib.import_module(m)
            line(OK, m, "")
        except Exception as e:
            line(BAD, m, "%s: %s" % (type(e).__name__, str(e)[:60]))


# -------------------------------------------------------------------- config
CFG_KEYS = {
    "spreadsheet_id": str, "service_account_file": str, "claude_cmd": str,
    "telegram": dict, "wizz": dict, "watchlist": dict, "passengers": dict,
    "alerts": dict, "trips": dict, "stays": dict, "inbound": dict,
}
WIZZ_KEYS = ["base_url", "url_template", "fare_api_match", "origin_slug",
             "origin_code", "months_ahead", "duration", "profile_dir", "headless"]


def check_config():
    header("CONFIG")
    try:
        cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    except Exception as e:
        line(BAD, "config.json parses", str(e)[:60])
        return None

    for k, t in CFG_KEYS.items():
        if k not in cfg:
            line(BAD, "config.%s" % k, "MISSING")
        elif not isinstance(cfg[k], t):
            line(BAD, "config.%s" % k, "wrong type")
        else:
            line(OK, "config.%s" % k, "")

    w = cfg.get("wizz", {})
    for k in WIZZ_KEYS:
        line(OK if k in w else WARN, "config.wizz.%s" % k,
             "" if k in w else "absent")

    if w.get("fare_api_match") != "SmartSearchCheapFlightsV2":
        line(WARN, "wizz.fare_api_match", "expected SmartSearchCheapFlightsV2, got %r"
             % w.get("fare_api_match"))
    if w.get("headless") is True:
        line(WARN, "wizz.headless", "True - Wizz returned no fares to headless Chromium")
    if cfg.get("spreadsheet_id", "").startswith("PASTE"):
        line(BAD, "spreadsheet_id", "still the placeholder")
    if "price_threshold_eur" in cfg.get("watchlist", {}):
        line(WARN, "watchlist.price_threshold_eur", "stale key; prices are USD now")
    return cfg


# ------------------------------------------------------------------- secrets
def check_secrets(cfg):
    header("SECRETS AND ENVIRONMENT")
    sa = os.path.join(ROOT, (cfg or {}).get("service_account_file",
                                            "secrets/service_account.json"))
    if os.path.exists(sa):
        try:
            d = json.load(open(sa, encoding="utf-8"))
            has = all(k in d for k in ("client_email", "private_key", "project_id"))
            line(OK if has else BAD, "service account key",
                 "email %s" % d.get("client_email", "?") if has else "malformed")
        except Exception as e:
            line(BAD, "service account key", str(e)[:50])
    else:
        line(BAD, "service account key", "MISSING at %s" % sa)

    for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        v = os.environ.get(var)
        line(OK if v else BAD, "env %s" % var,
             "set (%d chars)" % len(v) if v else "NOT SET")

    if os.environ.get("ANTHROPIC_API_KEY"):
        line(WARN, "env ANTHROPIC_API_KEY",
             "SET - claude -p may bill the metered API instead of your plan")
    else:
        line(OK, "env ANTHROPIC_API_KEY", "unset (correct: uses the subscription)")


def check_gitignore():
    header("GITIGNORE COVERAGE")
    p = os.path.join(ROOT, ".gitignore")
    body = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    for pat in ("secrets/", ".browser/"):
        line(OK if pat in body else BAD, "gitignore covers %s" % pat,
             "" if pat in body else "NOT IGNORED - risk of committing secrets")

    rc, out, _ = run(["git", "ls-files", "secrets", ".browser"])
    if rc == 0:
        tracked = [x for x in out.splitlines() if x.strip()]
        line(BAD if tracked else OK, "nothing sensitive tracked by git",
             "TRACKED: %s" % ", ".join(tracked[:3]) if tracked else "clean")


# ---------------------------------------------------------------------- shell
def run(args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=30,
                           encoding="utf-8", errors="ignore", cwd=ROOT)
        return p.returncode, p.stdout or "", p.stderr or ""
    except Exception as e:
        return 1, "", str(e)


def check_tasks():
    header("SCHEDULED TASKS")
    if os.name != "nt":
        line(WARN, "task scheduler", "not Windows, skipped")
        return
    for name, required in (("FamilyAssistant-Travel", True),
                           ("FamilyAssistant-Listener", True),
                           ("FamilyAssistant-Training", False),
                           ("FamilyAssistant-Meals", False)):
        rc, out, _ = run(["schtasks", "/query", "/tn", name, "/fo", "LIST"])
        if rc == 0:
            status = ""
            for l in out.splitlines():
                if l.lower().startswith("status"):
                    status = l.split(":", 1)[1].strip()
            line(OK, name, status or "registered")
        else:
            line(BAD if required else WARN, name,
                 "not registered" + ("" if required else " (expected - not built yet)"))


def check_git():
    header("GIT")
    rc, out, _ = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    line(OK if rc == 0 else WARN, "git repo", out.strip() or "not a repo")
    rc, out, _ = run(["git", "status", "--porcelain"])
    if rc == 0:
        n = len([x for x in out.splitlines() if x.strip()])
        line(OK if n == 0 else WARN, "working tree",
             "clean" if n == 0 else "%d uncommitted change(s)" % n)
    rc, out, _ = run(["git", "remote", "-v"])
    line(OK if "origin" in out else WARN, "remote origin",
         out.splitlines()[0].split()[1] if "origin" in out else "none")


def check_sheets(cfg):
    header("GOOGLE SHEETS (network)")
    try:
        from lib import config as C, sheets as S
        c = C.load()
        tabs = ["Flights", "Trips", "Stays", "Runs"]
        for t in tabs:
            rows = S.read_all(c, t)
            line(OK, "tab %s" % t, "%d data row(s)" % len(rows))
        q = os.path.join(ROOT, ".browser", "pending_sheets.jsonl")
        if os.path.exists(q):
            n = sum(1 for _ in open(q, encoding="utf-8"))
            line(WARN, "replay queue", "%d queued write(s) awaiting retry" % n)
        else:
            line(OK, "replay queue", "empty")
    except Exception as e:
        line(WARN, "sheets reachable", "%s: %s" % (type(e).__name__, str(e)[:60]))


def main():
    print("=" * 72)
    print("FAMILY-ASSISTANT SELF-CHECK   %s" % ROOT)
    print("=" * 72)
    check_structure()
    check_duplicates()
    check_imports()
    cfg = check_config()
    check_secrets(cfg)
    check_gitignore()
    check_tasks()
    check_git()
    if "--no-net" not in sys.argv:
        check_sheets(cfg)

    header("VERDICT")
    if not issues and not warnings:
        print("  Everything checks out.")
    if issues:
        print("  %d PROBLEM(S) needing attention:" % len(issues))
        for i in issues:
            print("    - %s" % i)
    if warnings:
        print("  %d warning(s), review but probably fine:" % len(warnings))
        for w in warnings:
            print("    - %s" % w)
    print()


if __name__ == "__main__":
    main()
