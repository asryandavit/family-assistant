"""Read the family plan (plan/) by its stable ids -- decision 085.

Parsing and day/week arithmetic only; coach/plan_text.py lays it out. Nothing here
invents a dish, an exercise or a number: an unknown id comes back as the id, a missing
week file as an explicit fallback the message says out loud.

    plan/meals/week-NN.md           the week's menu (Breakfast / Lunch / Dinner / Prep)
    plan/meals/dishes.md            dish ids -> names, optional recipe `ref`
    plan/daily-rhythm.md            weekly training calendar + session times
    plan/family/<person>.md         the 12-week blocks (Strength A, Session 1, ...)
    plan/training/exercises.md      exercise ids -> name + "how" cues
    plan/training/exercise-videos.md  generated + verified by jobs/exercise_videos.py
    plan/habits.md                  habit nudges
    config_coach.json               plan_start_local: Monday of week 1
"""
import glob
import json
import os
import re
from datetime import date, timedelta
from urllib.parse import quote_plus, urlparse

from lib import exercise_videos as xv

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
PEOPLE = ("davit", "karine")
PLAN_WEEKS = 12
ID_RE = re.compile(r"`([a-z]{2}-[a-z0-9-]+)`")

# Free recipe sites a dish `ref` may point to (docs/TELEGRAM_UX.md §5c). A ref on any
# other host is ignored. Each link is opened and checked before it is added.
RECIPE_SITES = {
    "www.bbcgoodfood.com": "BBC Good Food",
    "www.armenianinstitute.org.uk": "Armenian Institute",
    "thearmeniankitchen.com": "The Armenian Kitchen",
}
YOUTUBE_SEARCH = "https://www.youtube.com/results?search_query="

FIRST_TIME = "watch the video before your first set; start with the lightest option."


# ------------------------------------------------------------------ files

def _read(root, *parts):
    try:
        with open(os.path.join(root, *parts), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_sep(cells):
    return all(set(c) <= set("-: ") for c in cells)


def _bold_label(line):
    m = re.fullmatch(r"\*\*([^*]+)\*\*", line.strip())
    return m.group(1).strip() if m else None


def tables(md):
    """[{heading, label, header, rows}] for every Markdown table. heading = the last
    #-heading above it; label = a bold-only line right above it ('**Strength A**')."""
    out, heading, label, cur = [], None, None, None
    for line in (md or "").splitlines():
        s = line.strip()
        if s.startswith("#"):
            heading, label, cur = s.lstrip("#").strip(), None, None
            continue
        if s.startswith("|"):
            cells = _cells(s)
            if cur is None:
                cur = {"heading": heading, "label": label,
                       "header": [c.lower() for c in cells], "rows": []}
                out.append(cur)
            elif not _is_sep(cells):
                cur["rows"].append(cells)
            continue
        cur = None
        if s:
            label = _bold_label(s)
    return out


def ids_in(text):
    return ID_RE.findall(text or "")


# ------------------------------------------------------------------ config + dates

def load_coach(root):
    try:
        with open(os.path.join(root, "config_coach.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def plan_start(root):
    """Monday of plan week 1 (config_coach.json plan_start_local), or None."""
    v = load_coach(root).get("plan_start_local")
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


def week_of(day, start):
    """Plan week for a local date: 1 on the start date's week, 0 before it."""
    if start is None or day < start:
        return 0
    return (day - start).days // 7 + 1


def weekday(day):
    return DAYS[day.weekday()]


# ------------------------------------------------------------------ dishes

def parse_dishes(md):
    """dishes.md -> {id: {id, name, ref}} across all its tables."""
    out = {}
    for t in tables(md):
        h = t["header"]
        if not h or h[0] != "id":
            continue
        name_col = next((i for i, c in enumerate(h) if c in ("dish", "what", "name")), 1)
        ref_col = h.index("ref") if "ref" in h else None
        for r in t["rows"]:
            ids = ids_in(r[0])
            if not ids:
                continue
            ref = r[ref_col].strip() if ref_col is not None and ref_col < len(r) else ""
            out[ids[0]] = {"id": ids[0], "name": r[name_col] if name_col < len(r) else ids[0],
                           "ref": ref or None}
    return out


def recipe_ref(dish):
    """(url, site name) when the dish has a ref on an allowlisted site, else None."""
    url = (dish or {}).get("ref")
    if not url:
        return None
    u = urlparse(url)
    if u.scheme != "https" or u.netloc not in RECIPE_SITES:
        return None
    return url, RECIPE_SITES[u.netloc]


# ------------------------------------------------------------------ week menu

MEALS = ("breakfast", "lunch", "dinner", "prep")


def week_numbers(root):
    out = []
    for p in glob.glob(os.path.join(root, "plan", "meals", "week-*.md")):
        m = re.fullmatch(r"week-(\d+)\.md", os.path.basename(p))
        if m:
            out.append(int(m.group(1)))
    return sorted(out)


def pick_week_file(root, week):
    """(number used, fell_back). Missing week-NN.md -> the latest week file."""
    nums = week_numbers(root)
    if not nums:
        return None, True
    want = max(week, 1)
    return (want, False) if want in nums else (nums[-1], True)


def parse_week(md):
    """week-NN.md -> {days: {Mon: {breakfast, lunch, dinner, prep}}, batch: [(day, effort, text)],
    notes: [text]}. Cells stay raw Markdown (ids in backticks); plan_text renders them."""
    days = {}
    for t in tables(md):
        h = t["header"]
        if not h or h[0] != "day":
            continue
        cols = {}
        for i, c in enumerate(h):
            for m in MEALS:
                if c.startswith(m):
                    cols[m] = i
        for r in t["rows"]:
            d = r[0].replace("*", "").strip()[:3].title()
            if d in DAYS:
                days[d] = {m: (r[i] if i < len(r) else "") for m, i in cols.items()}
    batch, notes = [], []
    section = None
    paras, cur = [], []
    for line in (md or "").splitlines():
        s = line.strip()
        if s.startswith("#"):
            if cur:
                paras.append((section, " ".join(cur)))
            section, cur = s.lstrip("#").strip().lower(), []
            continue
        if not s or s.startswith("|"):
            if cur:
                paras.append((section, " ".join(cur)))
            cur = []
            continue
        if s.startswith("**") and cur:
            paras.append((section, " ".join(cur)))
            cur = []
        cur.append(s)
    if cur:
        paras.append((section, " ".join(cur)))
    for sec, p in paras:
        m = re.match(r"\*\*(\w+) \(([^)]*)\):\*\*\s*(.*)", p)
        if sec == "batch sessions" and m:
            batch.append((m.group(1), m.group(2), m.group(3)))
        elif sec == "the week" and p.startswith("**"):
            notes.append(p)
    return {"days": days, "batch": batch, "notes": notes}


def load_week(root, week):
    """{number, fell_back, days, batch, notes} for a plan week, or None without any file."""
    num, fell_back = pick_week_file(root, week)
    if num is None:
        return None
    md = _read(root, "plan", "meals", "week-%02d.md" % num)
    if md is None:
        return None
    w = parse_week(md)
    w.update(number=num, fell_back=fell_back)
    return w


# ------------------------------------------------------------------ exercises + videos

def parse_exercises(md):
    """exercises.md -> {id: {id, name, how}}."""
    out = {}
    for t in tables(md):
        h = t["header"]
        if not h or h[0] != "id" or "name" not in h:
            continue
        how_col = next((i for i, c in enumerate(h) if c.startswith("how")), None)
        for r in t["rows"]:
            ids = ids_in(r[0])
            if ids:
                out[ids[0]] = {"id": ids[0], "name": r[h.index("name")],
                               "how": r[how_col] if how_col is not None and how_col < len(r) else ""}
    return out


def cues(how, n=3):
    """Up to n 'how' sentences, without the dose sentences ('8-12 reps.') -- the plan's
    own dose is shown next to the exercise -- and without contextless 'Same position.'"""
    out = []
    for s in re.split(r"(?<=[.!?])\s+", (how or "").strip()):
        s = s.strip()
        if not s or s[0].isdigit() or len(s.split()) < 3:
            continue
        out.append(s)
        if len(out) == n:
            break
    return out


def load_videos(root):
    """{id: {video_url, video_title, channel}} for rows the video job verified; {} when
    exercise-videos.md doesn't exist yet."""
    md = _read(root, "plan", "training", "exercise-videos.md")
    if not md:
        return {}
    return {k: v for k, v in xv.parse_generated(md).items()
            if v.get("video_url") and v.get("verified_at")
            and v["video_url"].startswith("https://www.youtube.com/watch?v=")}


def video_search_url(name):
    """Code-built search -- '<exercise name> form tutorial', the video job's own query."""
    return YOUTUBE_SEARCH + quote_plus(xv.search_query(name))


# ------------------------------------------------------------------ training

def parse_calendar(md):
    """daily-rhythm.md weekly calendar -> [{person, from, to, days: {Mon: cell}}]."""
    out = []
    for t in tables(md):
        h = t["header"]
        if len(h) < 8 or h[1] != "mon":
            continue
        for r in t["rows"]:
            m = re.match(r"\*\*(\w+)\*\*\s*wk\s*(\d+)\s*[–-]\s*(\d+)", r[0])
            if m:
                out.append({"person": m.group(1).lower(), "from": int(m.group(2)),
                            "to": int(m.group(3)),
                            "days": {d: r[i + 1] for i, d in enumerate(DAYS) if i + 1 < len(r)}})
    return out


def session_times(md):
    """{person: 'HH:MM'} from the weekday table row whose cell names the training session."""
    out = {}
    for t in tables(md):
        h = t["header"]
        if not h or h[0] != "time":
            continue
        for r in t["rows"]:
            for p in PEOPLE:
                if p in h and p not in out:
                    i = h.index(p)
                    if i < len(r) and "training session" in r[i].lower():
                        out[p] = r[0]
    return out


def _paragraphs(lines):
    out, cur = [], []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("|"):
            if cur:
                out.append(" ".join(cur))
            cur = []
        else:
            cur.append(s)
    if cur:
        out.append(" ".join(cur))
    return out


def parse_person(md):
    """<person>.md -> {blocks: [{from, to, title, intro, tables, paras}], every_session}.
    A block is a '### Weeks 1–4 · Foundations — ...' heading and what follows it; intro =
    the paragraphs before its first table or bold label."""
    lines = (md or "").splitlines()
    blocks, cur = [], None
    for line in lines:
        s = line.strip()
        if s.startswith("#"):
            m = re.match(r"###\s+Weeks?\s+(\d+)\s*[–-]\s*(\d+)\s*·\s*(.*)", s)
            cur = None
            if m:
                cur = {"from": int(m.group(1)), "to": int(m.group(2)),
                       "title": m.group(3).strip(), "md": []}
                blocks.append(cur)
        elif cur is not None:
            cur["md"].append(line)
    for b in blocks:
        head = []
        for line in b["md"]:
            if line.strip().startswith("|") or _bold_label(line):
                break
            head.append(line)
        b["intro"] = _paragraphs(head)
        b["paras"] = _paragraphs(b["md"])
        b["tables"] = tables("\n".join(b["md"]))
        del b["md"]
    every = next((p for p in _paragraphs(lines) if p.startswith("Every session:")), None)
    return {"blocks": blocks, "every_session": every}


def block_for(plan, week):
    w = min(max(week, 1), PLAN_WEEKS)
    for b in plan["blocks"]:
        if b["from"] <= w <= b["to"]:
            return b
    return None


def _first_sentence(text):
    m = re.search(r"\.(\s|$)", text)
    return text[:m.start() + 1] if m else text


def _find_in_block(b, name):
    """A session's content inside one block: a table labelled with its name, the single
    unlabelled table of a block named after it, or the sentence that introduces it."""
    low = name.lower()
    for t in b["tables"]:
        if t["label"] and t["label"].lower() == low:
            return {"kind": "table", "rows": t["rows"], "header": t["header"]}
    if low in b["title"].lower():
        unl = [t for t in b["tables"] if not t["label"]]
        if len(unl) == 1:
            return {"kind": "table", "rows": unl[0]["rows"], "header": unl[0]["header"]}
    for p in b["paras"]:
        plain = p.replace("**", "")
        m = re.search(r"\b%s\s*(\(|:)" % re.escape(low), plain.lower())
        if m:
            return {"kind": "text", "text": _first_sentence(plain[m.start():])}
    return None


def session_detail(plan, week, name):
    """{block, source, kind, rows|text} for a named session in that week; kind None when
    the plan doesn't describe it. Searches the week's block, then earlier blocks (a
    later block that says 'same shape' reuses the earlier exercises)."""
    b = block_for(plan, week)
    if b is None:
        return {"block": None, "source": None, "kind": None}
    for cand in [b] + sorted((x for x in plan["blocks"] if x["to"] < b["from"]),
                             key=lambda x: -x["from"]):
        found = _find_in_block(cand, name)
        if found:
            found.update(block=b, source=cand)
            return found
    return {"block": b, "source": None, "kind": None}


SESSION_WORDS = ("strength", "session", "foundations", "cardio")


def is_session(cell):
    return any(w in (cell or "").lower() for w in SESSION_WORDS)


def day_cell(calendar, person, week, day):
    """Calendar cell for person/week/day ('Strength A', 'walk', '—'), or None."""
    w = min(max(week, 1), PLAN_WEEKS)
    for row in calendar:
        if row["person"] == person and row["from"] <= w <= row["to"]:
            return row["days"].get(day)
    return None


def row_exercises(row):
    """A session-table row -> (ids, dose, raw id cell). ids[0] is the one to do now; a
    'a → b' cell names the next step."""
    cell = row[1] if len(row) > 1 else ""
    dose = row[2] if len(row) > 2 else ""
    return ids_in(cell), dose, cell


def session_ids(detail):
    """The exercises a session asks for (first id of each row; every id in a sentence)."""
    if detail.get("kind") == "table":
        return [ids[0] for ids, _, _ in map(row_exercises, detail["rows"]) if ids]
    if detail.get("kind") == "text":
        return ids_in(detail["text"])
    return []


def options(cell):
    """'Strength A / Cardio' -> ['Strength A', 'Cardio']."""
    return [o.strip() for o in (cell or "").split(" / ") if o.strip()]


def first_appearance(calendar, plan, person):
    """{exercise id: (week, day index)} -- the first day it is scheduled for that person
    in the 12-week plan. Deterministic, from the plan files only."""
    seen = {}
    for week in range(1, PLAN_WEEKS + 1):
        for di, d in enumerate(DAYS):
            cell = day_cell(calendar, person, week, d)
            if not is_session(cell):
                continue
            for opt in options(cell):
                for ex in session_ids(session_detail(plan, week, opt)):
                    seen.setdefault(ex, (week, di))
    return seen


# ------------------------------------------------------------------ habits

def habit_nudges(md):
    """Short nudges from habits.md: the 'after X, do Y' table and the 'make it easy' list."""
    out = []
    for t in tables(md):
        if t["header"][:1] == ["after…"]:
            out += ["After %s: %s." % (r[0][0].lower() + r[0][1:], r[1][0].lower() + r[1][1:])
                    for r in t["rows"] if len(r) > 1]
    section = None
    for line in (md or "").splitlines():
        s = line.strip()
        if s.startswith("## "):
            section = s.lower()
        elif section and "make it easy" in section and s.startswith("- "):
            out.append(s[2:].replace("**", ""))
    return out


def nudge_for(md, day):
    n = habit_nudges(md)
    return n[day.toordinal() % len(n)] if n else None


# ------------------------------------------------------------------ one day

def load_plan(root):
    """Everything the messages need, parsed once."""
    rhythm = _read(root, "plan", "daily-rhythm.md") or ""
    return {
        "root": root,
        "start": plan_start(root),
        "dishes": parse_dishes(_read(root, "plan", "meals", "dishes.md")),
        "exercises": parse_exercises(_read(root, "plan", "training", "exercises.md")),
        "videos": load_videos(root),
        "calendar": parse_calendar(rhythm),
        "times": session_times(rhythm),
        "people": {p: parse_person(_read(root, "plan", "family", "%s.md" % p)) for p in PEOPLE},
        "habits": _read(root, "plan", "habits.md") or "",
    }


def person_day(plan, person, week, day):
    """{cell, kind: session|walk|rest, options: [{name, detail}], first_today: {ids}}."""
    d = weekday(day)
    cell = day_cell(plan["calendar"], person, week, d)
    pp = plan["people"][person]
    if not cell or cell.strip() in ("—", "-", ""):
        return {"cell": cell, "kind": "rest", "options": [], "first_today": set()}
    if not is_session(cell):
        return {"cell": cell, "kind": "walk", "options": [], "first_today": set()}
    opts = [{"name": o, "detail": session_detail(pp, week, o)} for o in options(cell)]
    first = set()
    if 1 <= week <= PLAN_WEEKS:
        fa = first_appearance(plan["calendar"], pp, person)
        first = {ex for ex, at in fa.items() if at == (week, DAYS.index(d))}
    return {"cell": cell, "kind": "session", "options": opts, "first_today": first}


def today_info(plan, day):
    """The plan for one local date: week, menu row, both adults' training."""
    start = plan["start"]
    week = week_of(day, start)
    wk_for_files = max(week, 1)
    menu = load_week(plan["root"], wk_for_files)
    d = weekday(day)
    return {
        "day": day, "weekday": d, "week": week, "start": start,
        "before_start": start is not None and day < start,
        "past_plan": week > PLAN_WEEKS,
        "menu": menu,
        "meals": (menu or {}).get("days", {}).get(d),
        "batch": [b for b in (menu or {}).get("batch", []) if b[0][:3] == d],
        "people": {p: person_day(plan, p, wk_for_files, day) for p in PEOPLE},
        "nudge": nudge_for(plan["habits"], day),
    }


def next_monday(day):
    return day + timedelta(days=7 - day.weekday())
