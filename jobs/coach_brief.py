"""Plan messages to both family chats (decision 085, docs/TELEGRAM_UX.md §5).

    python jobs/coach_brief.py --morning            07:30: today's meals, prep, both sessions
    python jobs/coach_brief.py --week               Sunday 18:00: next week's menu
    python jobs/coach_brief.py --morning --dry-run  print instead of sending
    python jobs/coach_brief.py --morning --date 2026-10-26 --dry-run   any day

Silent, to both chats via telegram.send_family(). Everything comes from plan/ through
coach/plan_text.py -- no model call. A push outside its window (morning after 10:00,
week plan after 22:00: a late start or a catch-up) is dropped and logged, never sent
late (COACH_SPEC §12). A failure tells the owner and sends nothing to the family.
"""
import argparse
import os
import sys
from datetime import date, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from coach import plan_text, plan_view  # noqa: E402
from lib import config, sheets, telegram, ui  # noqa: E402

JOB = "coach_brief"
VALID_UNTIL = {"morning": time(10, 0), "week": time(22, 0)}


def build(kind, root, day):
    plan = plan_view.load_plan(root)
    return plan_text.morning_text(plan, day) if kind == "morning" else plan_text.week_text(plan, day)


def _log(cfg, status, detail):
    try:
        sheets.log_run(cfg, JOB, status, detail)
    except Exception as e:
        print("  could not log run: %s" % e)


def run(cfg, kind, now=None, day=None, send=True, force=False):
    """Returns (status, text). status: sent | dry-run | dropped | failed."""
    root = cfg.get("_root", ROOT)
    now = now or ui.now_local()
    day = day or now.date()
    if send and not force and now.time() >= VALID_UNTIL[kind]:
        detail = "%s dropped: %s is past %s" % (kind, now.strftime("%H:%M"),
                                               VALID_UNTIL[kind].strftime("%H:%M"))
        print(detail)
        _log(cfg, "dropped", detail)
        return "dropped", None
    try:
        text = build(kind, root, day)
    except Exception as e:                     # no output beats a wrong plan
        telegram.notify(cfg, "⚠️ SYSTEM: %s plan not sent — %s" % (kind, str(e)[:200]))
        _log(cfg, "failed", "%s: %s" % (kind, str(e)[:120]))
        return "failed", None
    if not send:
        return "dry-run", text
    telegram.send_family(cfg, text, silent=True)
    _log(cfg, "ok", "%s %s" % (kind, day.isoformat()))
    return "sent", text


def main():
    ap = argparse.ArgumentParser(description="Send the plan to both family chats.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--morning", action="store_true", help="today's plan (07:30)")
    g.add_argument("--week", action="store_true", help="next week's menu (Sunday 18:00)")
    ap.add_argument("--dry-run", action="store_true", help="print, don't send")
    ap.add_argument("--date", help="Yerevan date YYYY-MM-DD instead of today")
    ap.add_argument("--force", action="store_true", help="send even outside the time window")
    a = ap.parse_args()
    kind = "morning" if a.morning else "week"
    day = date.fromisoformat(a.date) if a.date else None
    status, text = run(config.load(), kind, day=day, send=not a.dry_run, force=a.force)
    if text and a.dry_run:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    print("%s: %s (%d chars)" % (kind, status, len(text or "")))
    return 0 if status in ("sent", "dry-run", "dropped") else 1


if __name__ == "__main__":
    sys.exit(main())
