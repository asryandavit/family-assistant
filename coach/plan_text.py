"""Plan messages and Home sections from the parsed plan (decision 085).

Templates only -- every name, dose and time comes from plan/ through plan_view, the week
menu from coach/menu_gen (decision 107); no model call, no number computed here (the
weekly balance is counted in menu_gen). Layout follows docs/TELEGRAM_UX.md §2 via
lib.ui (header / fold / page). Links (the hard rule, §5c): a video URL only from
exercise-videos.md rows the video job verified, a recipe URL only from an allowlisted
`ref` in dishes.md, otherwise a search URL built in plan_view -- nothing else.
"""
import re
from datetime import timedelta

from coach import menu_gen as mg
from coach import plan_view as pv
from lib import ui
from lib.telegram import LIMIT, esc

SAFETY = ("Stop and seek medical care for chest pain, fainting, severe breathlessness, "
          "dark urine with muscle pain, yellowing of eyes or skin, or severe abdominal pain.")
FORBIDDEN = ("patient", "condition", "disease", "illness", "diagnosis", "treatment")
NAMES = {"davit": "Davit", "karine": "Karine"}
MEAL_LABELS = (("breakfast", "Breakfast"), ("lunch", "Lunch"), ("dinner", "Dinner"),
               ("prep", "Prep for tomorrow"))
MISSING = ("This week's menu couldn't be put together from the dish list. "
           "Davit has been told and will fix it.")
EVERY_DAY = ("Son: the same dishes — his portion taken out before salt, soft pieces, "
             "nuts only ground or finely chopped, full-fat dairy.",
             "Coffee ~08:00 and ~15:30, after food. Snack with coffee #2: fruit or matsun.",
             "Plate: ½ vegetables · ¼ protein · ¼ grains or legumes · a little lavash.")
RECIPE_NOTE = "Recipe links are for technique; dishes and portions stay ours."
WEEK_TITLE = "Next week's menu"


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


def _main_ids(plan, cell):
    """The dish ids of a cell that aren't sides (a side never gets a link or a mark)."""
    return [i for i in pv.ids_in(cell) if (plan["dishes"].get(i) or {}).get("slot") != "side"]


def _recipe(plan, cell):
    """One link per dish that has an allowlisted ref -- every option gets its own, so a
    cell never carries a link for one dish only while naming two."""
    refs = [(i, pv.recipe_ref(plan["dishes"].get(i))) for i in _main_ids(plan, cell)]
    refs = [(i, r) for i, r in refs if r]
    if len(refs) == 1:
        return ' · <a href="%s">recipe</a>' % esc(refs[0][1][0])
    return "".join(' · <a href="%s">%s</a>' % (esc(r[0]), esc(short(plan, i))) for i, r in refs)


def short(plan, dish_id):
    d = plan["dishes"].get(dish_id)
    return mg.short_name(d["name"]) if d else dish_id


def short_cell(plan, cell):
    """'`ln-x` · `sp-y` · boil 6 eggs' -> 'Mujaddara · Spas · boil 6 eggs' (escaped)."""
    return esc(pv.ID_RE.sub(lambda m: short(plan, m.group(1)), (cell or "").replace("**", "")))


def _notes(values):
    return [x for x in dict.fromkeys(v.strip() for v in values) if x and x not in ("—", "-")]


def meal_lines(plan, meals, refs=False, new=(), notes=False, tips_too=True):
    """Breakfast / Lunch / Dinner / Prep lines for one day; with notes, one 👶 line for
    the son and one 💡 line of tips from the day's dishes (dishes.md son / tip)."""
    out, son, tips = [], [], []
    for key, label in MEAL_LABELS:
        cell = (meals or {}).get(key, "").strip()
        if not cell or cell in ("—", "-"):
            continue
        mark = " ✨ <i>new</i>" if any(i in new for i in _main_ids(plan, cell)) else ""
        link = _recipe(plan, cell) if refs and key != "prep" else ""
        out.append("<b>%s</b> %s%s%s" % (label, _dish(plan, cell), mark, link))
        if key != "prep":
            for i in _main_ids(plan, cell):
                d = plan["dishes"].get(i) or {}
                son.append(d.get("son") or "")
                tips.append(d.get("tip") or "")
    if notes and _notes(son):
        out.append("👶 " + esc("; ".join(_notes(son))))
    if notes and tips_too and _notes(tips):
        out.append("💡 " + esc("; ".join(_notes(tips))))
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
    for son, tips in ((True, True), (True, False), (False, False)):
        text = _today(plan, day, chat_id, title, info, menu, son, tips)
        if len(text) <= LIMIT:
            break
    return text


def _today(plan, day, chat_id, title, info, menu, son, tips):
    def build(n_cues, full):
        body = []
        if menu.get("missing"):
            body.append(esc(MISSING))
        else:
            body += meal_lines(plan, info["meals"], new=menu.get("new") or (), notes=son,
                               tips_too=tips) or [
                "<i>No menu row for %s.</i>" % info["weekday"]]
            for _name, effort, text in info["batch"]:
                body.append("<b>Batch cooking</b> (%s) %s" % (esc(effort), short_cell(plan, text)))
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

def _range(monday):
    end = monday + timedelta(days=6)
    if monday.month == end.month:
        return "%d–%d %s" % (monday.day, end.day, end.strftime("%b"))
    return "%d %s – %d %s" % (monday.day, monday.strftime("%b"), end.day, end.strftime("%b"))


def _batch_day(monday, name):
    """'Sunday' batch = the Sunday before the week; 'Wednesday' = that week's Wednesday."""
    i = pv.DAYS.index(name[:3].title())
    return monday + timedelta(days=i - 7 if i == 6 else i)


# How much each day fold carries: (recipe links, 👶 son line, 💡 tips). The Rich Message
# always has all three; one plain HTML message takes the richest that fits (≤ LIMIT).
DETAIL = ((True, True, True), (True, True, False), (True, False, False), (False, False, False))


def week_model(plan, week, monday, today=None, detail=DETAIL[0]):
    """Everything a week message shows, built once for the HTML and the Rich layout:
    {sub, missing, menu, new, batch: [line], days: [(title, summary, lines)], balance}.
    No number is typed here -- the balance is counted by coach/menu_gen.balance()."""
    menu = pv.load_week(plan["root"], week, plan["dishes"])
    sub = "Week %d · %s" % (week, _range(monday))
    if menu.get("missing"):
        return {"sub": sub, "missing": True, "menu": menu}
    new = menu.get("new") or []
    batch = ["%s (%s): %s" % (ui.day_label(_dt(_batch_day(monday, n))), esc(e), short_cell(plan, t))
             for n, e, t in menu["batch"]]
    days = []
    for i, d in enumerate(pv.DAYS):
        date_ = monday + timedelta(days=i)
        meals = menu["days"].get(d) or {}
        refs, son, tips = detail
        lines = meal_lines(plan, meals, refs=refs, new=new, notes=son, tips_too=tips) or [
            "<i>No menu row.</i>"]
        mains = [short(plan, pv.ids_in(meals.get(k, ""))[0]) for k in ("lunch", "dinner")
                 if pv.ids_in(meals.get(k, ""))]
        title = "%s%s" % (ui.day_label(_dt(date_)), " · today" if today == date_ else "")
        days.append((title, " · ".join([title] + [esc(x) for x in dict.fromkeys(mains)]), lines))
    c = mg.balance(plan["dishes"], menu)
    bal = ("fish %d× · legumes %d× · chicken or turkey %d× · eggs %d× · red meat %d×"
           % (c["fish"], c["legume"], c["poultry"], c["egg"], c["red_meat"]))
    return {"sub": sub, "missing": False, "menu": menu, "batch": batch, "days": days,
            "new": ", ".join(esc(short(plan, i)) for i in new), "balance": bal}


def week_parts(plan, week, monday, today=None, detail=DETAIL[0]):
    """(subtitle, body, folded) for one plan week's menu: new dishes, batch cooking, one
    fold per day (title = the day and its lunch and dinner), an 'Every day' fold and the
    week's balance line."""
    m = week_model(plan, week, monday, today, detail)
    if m["missing"]:
        return m["sub"], [esc(MISSING)], ""
    body = []
    if m["new"]:
        body.append("✨ <b>New this week:</b> %s" % m["new"])
    if m["batch"]:
        body.append("<b>Batch cooking</b>")
        body += m["batch"]
    folds = [ui.fold(lines, summary) for _, summary, lines in m["days"]]
    folds.append(ui.fold([esc(x) for x in EVERY_DAY], "Every day"))
    folds.append("<i>This week: %s</i>" % m["balance"])
    return m["sub"], body, "\n".join(folds)


def _week_and_monday(plan, day):
    start = plan["start"]
    week = max(pv.week_of(day, start), 1)
    if start is not None and day < start:
        return 1, start
    return week, day - timedelta(days=day.weekday())


def meals_text(plan, day):
    week, monday = _week_and_monday(plan, day)

    def build(detail):
        sub, body, folded = week_parts(plan, week, monday, today=day, detail=detail)
        return ui.page(ui.header("\U0001f37d", "Meals", None, sub), body, folded,
                       "<i>%s</i>" % RECIPE_NOTE if detail[0] else None)
    return _fit_detail(build)


def _fit_detail(build):
    """The richest DETAIL level that keeps one message (Meals is edited in place)."""
    for detail in DETAIL:
        text = build(detail)
        if len(text) <= LIMIT:
            return text
    return text


def _next_week(plan, day):
    monday = pv.next_monday(day)
    return max(pv.week_of(monday, plan["start"]), 1), monday


def week_text(plan, day):
    """Sunday 18:00, plain HTML: next week's menu -- also the Rich Message's fallback and
    the Mini App's week page. Buttons (week_buttons) replace the old 'Home → Shopping'
    footer line; no file path is ever shown."""
    week, monday = _next_week(plan, day)

    def build(detail):
        sub, body, folded = week_parts(plan, week, monday, detail=detail)
        return ui.page(ui.header("\U0001f37d", WEEK_TITLE, None, sub), body, folded,
                       "<i>%s</i>" % RECIPE_NOTE if detail[0] else None)
    return _fit_detail(build)


def week_buttons(app_url=None):
    """📱 Today and 🧺 Basket in the Mini App when it is set up on this machine, else the
    chat's own 🧺 button (cmd:basket prices the list at both shops)."""
    if app_url:
        return [[("\U0001f4f1 Today", {"web_app": app_url + "?screen=today"}),
                 ("\U0001f9fa Basket", {"web_app": app_url + "?screen=basket"})]]
    return [[("\U0001f9fa Price the list at both shops", "cmd:basket")]]


def _attr(s):
    return esc(s).replace('"', "&quot;")


def rich_button(label, data):
    """A <tg-button> (same form as china/report.py: web_app url=, callback data=)."""
    if isinstance(data, dict) and "web_app" in data:
        return '<tg-button type="web_app" url="%s">%s</tg-button>' % (_attr(data["web_app"]), esc(label))
    return '<tg-button type="callback_data" data="%s">%s</tg-button>' % (_attr(data), esc(label))


def week_rich(plan, day, app_url=None):
    """(rich_html, plain_html, buttons, menu) for the Sunday message: a Telegram Rich
    Message with one <details> per day (a newline is a space there, so <br>), and the
    plain HTML as its fallback (lib/telegram.send_rich)."""
    week, monday = _next_week(plan, day)
    m = week_model(plan, week, monday)
    plain = week_text(plan, day)
    btns = week_buttons(app_url)
    R = ["<p><b>\U0001f37d %s</b><br><i>%s</i></p>" % (esc(WEEK_TITLE), esc(m["sub"]))]
    if m["missing"]:
        R.append("<p>%s</p>" % esc(MISSING))
    else:
        if m["new"]:
            R.append("<p>✨ <b>New this week:</b> %s</p>" % m["new"])
        if m["batch"]:
            R.append("<p><b>Batch cooking</b><br>%s</p>" % "<br>".join(m["batch"]))
        for _, summary, lines in m["days"]:
            R.append("<details><summary>%s</summary><p>%s</p></details>" % (summary, "<br>".join(lines)))
        R.append("<details><summary>Every day</summary><p>%s</p></details>"
                 % "<br>".join(esc(x) for x in EVERY_DAY))
        R.append("<p><i>This week: %s</i></p>" % m["balance"])
        R.append("<p><i>%s</i></p>" % esc(RECIPE_NOTE))
    R.append("".join("<tg-button-row>%s</tg-button-row>" % "".join(rich_button(lbl, d) for lbl, d in row)
                     for row in btns))
    return "".join(R), plain, btns, m["menu"]


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
