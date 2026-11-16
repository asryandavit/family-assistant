"""Today and the menu pages for the Mini App (decision 108).

The chat's texts (coach/plan_text) must fit ONE Telegram message, so they drop recipe links, then
the son's and tip lines. The app has no such limit: these pages are built from the same public
pieces at the richest level (`week_parts` with DETAIL[0], `meal_lines(refs=True)`), so the dishes,
the generated week and every number come from the one source, coach/menu_gen via plan_view.
tests/test_miniapp_menus.py compares them with the chat's text so the two cannot drift apart.

    today_page(root, chat_id, day)   today's meals + batch session + training on top, this week's
                                     menu under it (today's day marked, folded), the safety fold last
    menu_page(root, which, day)      "meals" = this week, "week" = next week, one fold per day
"""
from datetime import datetime, timedelta

from coach import plan_text as pt
from coach import plan_view as pv
from lib import ui
from lib.telegram import esc
from miniapp import screens

TODAY_ABOVE = "today (meals above)"


def _dt(d):
    return datetime(d.year, d.month, d.day, tzinfo=ui.YEREVAN)


def _this_week(plan, day):
    start = plan["start"]
    if start is not None and day < start:
        return 1, start
    return max(pv.week_of(day, start), 1), day - timedelta(days=day.weekday())


def _next_week(plan, day):
    monday = pv.next_monday(day)
    return max(pv.week_of(monday, plan["start"]), 1), monday


def _week_line(info):
    if info["start"] is None:
        return "Plan start date not set (config_coach.json plan_start_local)"
    if info["before_start"]:
        return f"The plan starts {ui.day_label(_dt(info['start']))} · showing week 1"
    if info["past_plan"]:
        return f"Week {info['week']} · past the 12-week plan, repeating weeks 9–12"
    return f"Week {info['week']} of {pv.PLAN_WEEKS}"


def menu_page(root, which, day=None):
    """One week's menu at full detail as display blocks; None for an unknown `which`."""
    if which not in ("meals", "week"):
        return None
    plan = pv.load_plan(root)
    day = day or ui.now_local().date()
    if which == "meals":
        week, monday = _this_week(plan, day)
        title, today = "Meals", day
    else:
        week, monday = _next_week(plan, day)
        title, today = pt.WEEK_TITLE, None
    sub, body, folded = pt.week_parts(plan, week, monday, today=today, detail=pt.DETAIL[0])
    note = f"<i>{esc(pt.RECIPE_NOTE)}</i>"
    html = ui.page(ui.header("\U0001f37d", title, None, sub), body, folded, note)
    return screens.html_blocks(html)


def today_page(root, chat_id, day=None):
    plan = pv.load_plan(root)
    day = day or ui.now_local().date()
    info = pv.today_info(plan, day)
    menu = info["menu"]
    body = []
    if menu.get("missing"):
        body.append(esc(pt.MISSING))
    else:
        body += pt.meal_lines(plan, info["meals"], refs=True, new=menu.get("new") or (),
                              notes=True, tips_too=True) or [f"<i>No menu row for {info['weekday']}.</i>"]
        for _name, effort, text in info["batch"]:
            body.append(f"<b>Batch cooking</b> ({esc(effort)}) {pt.short_cell(plan, text)}")
    body.append("")
    for p in pv.PEOPLE:
        body.append(pt.session_summary(plan, p, info["people"][p]))
        body += pt.today_extras(plan, p, day, chat_id)
    if info["nudge"]:
        body += ["", f"<i>Habit: {esc(info['nudge'])}</i>"]

    # this week's menu under today. Today's day is marked but stays folded: its meals are
    # already on top, and opening it showed them twice (seen 2026-11-16). The app opens a
    # fold titled "· today" on its own, but not "· today (meals above)".
    week, monday = _this_week(plan, day)
    sub, wbody, wfolded = pt.week_parts(plan, week, monday, today=day, detail=pt.DETAIL[0])
    wfolded = wfolded.replace(" · today", " · " + TODAY_ABOVE, 1)
    body += ["", f"<b>\U0001f37d This week's menu</b> · <i>{esc(sub)}</i>"] + wbody

    training = [pt.session_fold(plan, p, info["people"][p], 3, True) for p in pv.PEOPLE]
    folded = "\n".join([wfolded] + [f for f in training if f] + [pt.safety_fold()])
    html = ui.page(ui.header("\U0001f4c5", "Today", ui.day_label(_dt(day)), _week_line(info)),
                   body, folded, f"<i>{esc(pt.RECIPE_NOTE)}</i>")
    return screens.html_blocks(html)
