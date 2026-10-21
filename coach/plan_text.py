"""Plan messages and Home sections from the parsed plan (decision 085).

Templates only -- every name, dose and time comes from plan/ through plan_view; no
model call, no number computed here. Layout follows docs/TELEGRAM_UX.md §2 via
lib.ui (header / fold / page). Links (the hard rule, §5c): a video URL only from
exercise-videos.md rows the video job verified, a recipe URL only from an allowlisted
`ref` in dishes.md, otherwise a search URL built in plan_view -- nothing else.
"""
import re
from datetime import timedelta

from coach import plan_view as pv
from lib import ui
from lib.telegram import LIMIT, esc

SAFETY = ("Stop and seek medical care for chest pain, fainting, severe breathlessness, "
          "dark urine with muscle pain, yellowing of eyes or skin, or severe abdominal pain.")
FORBIDDEN = ("patient", "condition", "disease", "illness", "diagnosis", "treatment")
NAMES = {"davit": "Davit", "karine": "Karine"}
MEAL_LABELS = (("breakfast", "Breakfast"), ("lunch", "Lunch"), ("dinner", "Dinner"),
               ("prep", "Prep for tomorrow"))


def today_extras(plan, person, day, chat_id=None):
    """Hook for the health-records session (docs/briefs/HEALTH_RECORDS.md §6.2): extra
    lines for one person's Today section, on demand only -- e.g. the weekly muscle-symptom
    question when that person's approved brief flags it. Nothing here reads a brief yet."""
    return []


# ------------------------------------------------------------------ inline Markdown

def inline(text, lookup, what):
    """A plan cell -> HTML: `ids` become names, **bold** marks dropped, rest escaped.
    An id missing from the library stays visible with a note -- never a guess."""
    out, pos = [], 0
    text = (text or "").replace("**", "")
    for m in pv.ID_RE.finditer(text):
        out.append(esc(text[pos:m.start()]))
        item = lookup.get(m.group(1))
        out.append(esc(item["name"]) if item else
                   "<code>%s</code> <i>(not in the %s)</i>" % (esc(m.group(1)), what))
        pos = m.end()
    out.append(esc(text[pos:]))
    return "".join(out).strip()


def _dish(plan, cell):
    return inline(cell, plan["dishes"], "dish list")


def _ex(plan, text):
    return inline(text, plan["exercises"], "exercise library")


def _recipe(plan, cell):
    """At most one recipe reference per meal: the first dish in the cell with a ref."""
    for i in pv.ids_in(cell):
        ref = pv.recipe_ref(plan["dishes"].get(i))
        if ref:
            return ' · <a href="%s">recipe: %s</a>' % (esc(ref[0]), esc(ref[1]))
    return ""


def meal_lines(plan, meals, refs=False):
    out = []
    for key, label in MEAL_LABELS:
        cell = (meals or {}).get(key, "").strip()
        if not cell or cell in ("—", "-"):
            continue
        out.append("<b>%s</b> %s%s" % (label, _dish(plan, cell), _recipe(plan, cell) if refs else ""))
    return out


# ------------------------------------------------------------------ training

def _video(plan, ex_id, name):
    """(inline link, own line): a verified video gets its own line with title and channel;
    otherwise a short code-built search link sits on the exercise line."""
    v = plan["videos"].get(ex_id)
    if v:
        return "", '   Video: <a href="%s">%s</a> (%s)' % (
            esc(v["video_url"]), esc(v.get("video_title") or name), esc(v.get("channel") or "YouTube"))
    return ' · <a href="%s">video search</a>' % esc(pv.video_search_url(name)), None


def _exercise(plan, n, ids, dose, cell, first, n_cues):
    """One numbered exercise: names, dose, video, cues; '(new)' on its first day."""
    ex = plan["exercises"].get(ids[0]) if ids else None
    link, own = _video(plan, ex["id"], ex["name"]) if ex else ("", None)
    new = " <i>(new)</i>" if ex and ex["id"] in first else ""
    lines = ["%d. <b>%s</b>%s%s%s" % (n, _ex(plan, cell), (" · " + esc(dose)) if dose else "", link, new)]
    if ex:
        lines += ["   " + esc(c) for c in pv.cues(ex["how"], n_cues)]
    if own:
        lines.append(own)
    return lines


def _first_line(plan, d, first):
    """One line per session when any of its exercises is new today."""
    if any(i in first for i in pv.session_ids(d)):
        return "<i>(new) = first time: %s</i>" % esc(pv.FIRST_TIME)
    return None


def session_summary(plan, person, pd):
    who = "<b>%s</b>" % NAMES[person]
    if pd["kind"] == "rest":
        return "%s rest day · the daily walk and 5–10 min mobility" % who
    if pd["kind"] == "walk":
        return "%s no session today · %s" % (who, esc(pd["cell"]))
    t = plan["times"].get(person)
    parts = []
    for o in pd["options"]:
        n = len(pv.session_ids(o["detail"]))
        parts.append("%s%s" % (esc(o["name"]), " (%d exercises)" % n if o["detail"].get("kind") == "table" else ""))
    return "%s %s%s" % (who, (esc(t) + " · ") if t else "", " or ".join(parts))


def session_fold(plan, person, pd, n_cues=3, full=True):
    """Folded detail for one person's session ('' on walk / rest days). full=False
    leaves out the block's how-to paragraph and the warm-up line (they stay in Training)."""
    if pd["kind"] != "session":
        return ""
    lines = []
    every = plan["people"][person].get("every_session")
    for i, o in enumerate(pd["options"]):
        d = o["detail"]
        if i:
            lines.append("")
            lines.append("<i>or</i>")
        b, src = d.get("block"), d.get("source")
        if b:
            lines.append("<i>Weeks %d–%d · %s</i>" % (b["from"], b["to"], esc(b["title"])))
        if d.get("kind") == "table":
            if src is b and full:
                lines += [_ex(plan, p) for p in b["intro"]]
            elif src is not b and src:
                lines.append("<i>Exercises as in weeks %d–%d.</i>" % (src["from"], src["to"]))
            if every and full:
                lines.append(_ex(plan, every))
            lines.append(_first_line(plan, d, pd["first_today"]))
            for n, row in enumerate(d["rows"], 1):
                ids, dose, cell = pv.row_exercises(row)
                lines += _exercise(plan, n, ids, dose, cell, pd["first_today"], n_cues)
        elif d.get("kind") == "text":
            lines += [_ex(plan, d["text"]), _first_line(plan, d, pd["first_today"])]
            for n, ex_id in enumerate(pv.ids_in(d["text"]), 1):
                lines += _exercise(plan, n, [ex_id], "", "`%s`" % ex_id, pd["first_today"], n_cues)
        else:
            lines.append("<i>%s isn't described in the plan for this week.</i>" % esc(o["name"]))
    return ui.fold([ln for ln in lines if ln is not None], "%s · %s" % (NAMES[person], esc(pd["cell"])))


def safety_fold():
    return ui.fold([esc(SAFETY)], "Safety")


def _week_line(info):
    if info["start"] is None:
        return "Plan start date not set (config_coach.json plan_start_local)"
    if info["before_start"]:
        return "The plan starts %s · showing week 1" % ui.day_label(_dt(info["start"]))
    if info["past_plan"]:
        return "Week %d · past the 12-week plan, repeating weeks 9–12" % info["week"]
    return "Week %d of %d" % (info["week"], pv.PLAN_WEEKS)


def _dt(d):
    from datetime import datetime
    return datetime(d.year, d.month, d.day, tzinfo=ui.YEREVAN)


LEVELS = ((3, True), (2, True), (2, False), (1, False), (0, False))


def _fit(build, levels=LEVELS):
    """The richest (cues per exercise, full detail) that keeps one message. 2-3 cues is
    the aim; fewer only on the heaviest days (two sessions, every exercise new)."""
    for n, full in levels:
        text = build(n, full)
        if len(text) <= LIMIT:
            return text
    return text


# ------------------------------------------------------------------ Today + morning

def today_text(plan, day, chat_id=None, title="Today"):
    info = pv.today_info(plan, day)
    menu = info["menu"]

    def build(n_cues, full):
        body = []
        if menu is None:
            body.append("<i>No week menu file in plan/meals/.</i>")
        else:
            if menu["fell_back"]:
                body.append("<i>No menu for week %d yet — showing week %d's.</i>"
                            % (info["week"], menu["number"]))
            body += meal_lines(plan, info["meals"]) or ["<i>No menu row for %s.</i>" % info["weekday"]]
            for name, effort, text in info["batch"]:
                body.append("<b>Batch cooking</b> (%s) %s" % (esc(effort), _dish(plan, text)))
        body.append("")
        for p in pv.PEOPLE:
            body.append(session_summary(plan, p, info["people"][p]))
            body += today_extras(plan, p, day, chat_id)
        if info["nudge"]:
            body += ["", "<i>Habit: %s</i>" % esc(info["nudge"])]
        folds = [session_fold(plan, p, info["people"][p], n_cues, full) for p in pv.PEOPLE]
        folded = "\n".join([f for f in folds if f] + [safety_fold()])
        return ui.page(ui.header("\U0001f4c5", title, ui.day_label(_dt(day)), _week_line(info)),
                       body, folded)
    return _fit(build, LEVELS[1:])            # Today: compact first (20-second read)


def morning_text(plan, day):
    return today_text(plan, day, title="Good morning")


# ------------------------------------------------------------------ Meals + week plan

def week_parts(plan, week, monday, today=None):
    """(subtitle, body, folded) for one plan week's menu, one fold per day."""
    menu = pv.load_week(plan["root"], week)
    if menu is None:
        return "Week %d" % week, ["<i>No week menu file in plan/meals/.</i>"], ""
    body = []
    if menu["fell_back"]:
        body.append("<i>No menu for week %d yet (plan/meals/week-%02d.md) — showing week %d's.</i>"
                    % (week, week, menu["number"]))
    for name, effort, text in menu["batch"]:
        body.append("<b>Batch %s</b> (%s) %s" % (esc(name), esc(effort), _dish(plan, text)))
    folds = []
    for i, d in enumerate(pv.DAYS):
        date_ = monday + timedelta(days=i)
        lines = meal_lines(plan, menu["days"].get(d), refs=True) or ["<i>No menu row.</i>"]
        mark = " · today" if today == date_ else ""
        folds.append(ui.fold(lines, "%s%s" % (ui.day_label(_dt(date_)), mark)))
    notes = [_dish(plan, n) for n in menu["notes"]]
    if notes:
        folds.append(ui.fold(notes, "Notes"))
    end = monday + timedelta(days=6)
    sub = "Week %d · %d %s – %d %s" % (week, monday.day, monday.strftime("%b"), end.day, end.strftime("%b"))
    return sub, body, "\n".join(folds)


def _week_and_monday(plan, day):
    start = plan["start"]
    week = max(pv.week_of(day, start), 1)
    if start is not None and day < start:
        return 1, start
    return week, day - timedelta(days=day.weekday())


def meals_text(plan, day):
    week, monday = _week_and_monday(plan, day)
    sub, body, folded = week_parts(plan, week, monday, today=day)
    return ui.page(ui.header("\U0001f37d", "Meals", None, sub), body, folded,
                   "<i>Recipe links are for technique; dishes and portions stay ours.</i>")


def week_text(plan, day):
    """Sunday 18:00: next week's menu + where to price it."""
    monday = pv.next_monday(day)
    week = max(pv.week_of(monday, plan["start"]), 1)
    sub, body, folded = week_parts(plan, week, monday)
    return ui.page(ui.header("\U0001f37d", "Next week's menu", None, sub), body, folded,
                   "<i>To price it at both shops: \U0001f3e0 Home → \U0001f6d2 Shopping → "
                   "\U0001f9fa Basket.</i>")


# ------------------------------------------------------------------ Training

def training_text(plan, day):
    info = pv.today_info(plan, day)

    def build(n_cues, full):
        body = [session_summary(plan, p, info["people"][p]) for p in pv.PEOPLE]
        body.append("<i>Every day, both: 5–10 min mobility, a walk, wind-down breathing.</i>")
        folds = [session_fold(plan, p, info["people"][p], n_cues, full) for p in pv.PEOPLE]
        folded = "\n".join([f for f in folds if f] + [safety_fold()])
        return ui.page(ui.header("\U0001f3c3", "Training", ui.day_label(_dt(day)), _week_line(info)),
                       body, folded)
    return _fit(build)


# ------------------------------------------------------------------ checks used by tests

def urls(text):
    return re.findall(r'href="([^"]+)"', text or "")


def forbidden_words(text):
    plain = re.sub(r"<[^>]+>", " ", text or "").lower()
    return [w for w in FORBIDDEN if re.search(r"\b%ss?\b" % w, plain)]
