"""Plan messages to both family chats (decision 085, docs/TELEGRAM_UX.md §5).

    python jobs/coach_brief.py --morning            07:30: today's meals, prep, both sessions
    python jobs/coach_brief.py --week               Sunday 18:00: next week's menu
    python jobs/coach_brief.py --morning --dry-run  print instead of sending
    python jobs/coach_brief.py --morning --date 2026-10-26 --dry-run   any day
    python jobs/coach_brief.py --week --owner-only --force   the owner's chat only (review)

Silent, to both chats. Everything comes from plan/ through coach/plan_text.py -- no model
call. The week menu goes as a Telegram Rich Message (one fold per day, 📱 Today / 🧺 Basket
buttons) with the plain HTML as fallback (decision 107); the morning plan via send_family().
A week the generator can't fill is said plainly in the message and the owner is told; so
are the generator's warnings (a rule broken by a hand-edited week, the new-dish queue
running out). A push outside its window (morning after 10:00,
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


def app_url():
    """The Mini App (machine.json miniapp_public_url) or None -- then the chat button."""
    try:
        from miniapp import public_url
        return public_url() or None
    except (ImportError, OSError, ValueError):
        return None


def build(kind, root, day):
    """(plain_html, rich_html or None, buttons, problems for the owner)."""
    plan = plan_view.load_plan(root)
    if kind == "morning":
        info = plan_view.today_info(plan, day)
        menu = info["menu"]
        problems = [menu["error"]] if menu.get("missing") else []
        return plan_text.morning_text(plan, day), None, None, problems
    rich, plain, btns, menu = plan_text.week_rich(plan, day, app_url())
    problems = [menu["error"]] if menu.get("missing") else list(menu.get("warnings") or [])
    return plain, rich, btns, problems


def chats(cfg, owner_only):
    allowed = telegram.allowed_chats(cfg)
    return allowed[:1] if owner_only else allowed


def _log(cfg, status, detail):
    try:
        sheets.log_run(cfg, JOB, status, detail)
    except Exception as e:
        print("  could not log run: %s" % e)


def run(cfg, kind, now=None, day=None, send=True, force=False, owner_only=False):
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
        text, rich, btns, problems = build(kind, root, day)
    except Exception as e:                     # no output beats a wrong plan
        telegram.notify(cfg, "⚠️ SYSTEM: %s plan not sent — %s" % (kind, str(e)[:200]))
        _log(cfg, "failed", "%s: %s" % (kind, str(e)[:120]))
        return "failed", None
    if not send:
        for p in problems:
            print("  ! " + p)
        return "dry-run", text
    if problems:                               # the family still gets the plain sentence
        telegram.notify(cfg, "⚠️ Menu (%s %s): %s" % (kind, day.isoformat(), "; ".join(problems)[:600]))
    if rich:
        for chat in chats(cfg, owner_only):
            telegram.send_rich(cfg, rich, text, silent=True, buttons=btns, chat_id=chat)
    elif owner_only:
        telegram.send_html(cfg, text, silent=True, chat_id=chats(cfg, True)[0])
    else:
        telegram.send_family(cfg, text, silent=True)
    _log(cfg, "ok", "%s %s%s" % (kind, day.isoformat(), " owner only" if owner_only else ""))
    return "sent", text


def main():
    ap = argparse.ArgumentParser(description="Send the plan to both family chats.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--morning", action="store_true", help="today's plan (07:30)")
    g.add_argument("--week", action="store_true", help="next week's menu (Sunday 18:00)")
    ap.add_argument("--dry-run", action="store_true", help="print, don't send")
    ap.add_argument("--date", help="Yerevan date YYYY-MM-DD instead of today")
    ap.add_argument("--force", action="store_true", help="send even outside the time window")
    ap.add_argument("--owner-only", action="store_true", help="send to the owner's chat only (review)")
    a = ap.parse_args()
    kind = "morning" if a.morning else "week"
    day = date.fromisoformat(a.date) if a.date else None
    status, text = run(config.load(), kind, day=day, send=not a.dry_run, force=a.force,
                       owner_only=a.owner_only)
    if text and a.dry_run:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    print("%s: %s (%d chars)" % (kind, status, len(text or "")))
    return 0 if status in ("sent", "dry-run", "dropped") else 1


if __name__ == "__main__":
    sys.exit(main())
