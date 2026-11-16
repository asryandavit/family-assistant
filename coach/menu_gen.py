"""The week menu generator (decision 107): every plan week has a menu, never a fallback.

Deterministic and model-free (CLAUDE.md §2): the same dish library and the same earlier
weeks always give the same week. It only picks dish ids from plan/meals/dishes.md and
counts them; it never names a dish, an amount or a nutrition value of its own.

    week-NN.md exists          -> that file (hand-written or written by this module)
    weeks 2-4 without a file   -> week 1 (the manual trial ran four weeks)
    week >= 5 without a file   -> generated here, from the library and weeks 5..N-1

The layout of a week (principles.md "The weekly rules"):

    Mon  breakfast | main A (Sunday batch)      | soup (Sunday batch)
    Tue  breakfast | main A                     | soup                 prep: main B's soak
    Wed  breakfast | main B (Wednesday batch)   | fish 1
    Thu  breakfast | main B                     | egg dinner
    Fri  breakfast | fish 2                     | light dinner
    Sat  breakfast | weekend lunch 1            | Scoolinary project   prep: Sunday shop
    Sun  breakfast | weekend lunch 2            | weekend lunch 2 leftovers, small, + greens

Rules: main B is a legume; exactly one of main A and the soup is a legume, so legumes are
4 meals and never twice in a day; fish twice; a lunch or dinner dish never returns the
week after (at least 8 days apart); no two dishes of one group in a week; chicken or
turkey at least 2 meals (when main A is a legume, Sunday's lunch is poultry); 1-2 new
dishes a week, taken in library order (3 only when a slot has nothing else); oats at
least 3 breakfasts. Breaking a rule raises
GenerationError -- the caller says so plainly and tells the owner.

    python -m coach.menu_gen --write 5 8      write plan/meals/week-05.md .. week-08.md
    python -m coach.menu_gen --show 9         print week 9 as it would be written
"""
import argparse
import os
import sys
from datetime import date, timedelta

from coach import plan_view as pv

FIRST_GENERATED = 5          # weeks 1-4 were the manual trial (week-01.md, repeated)
NEW_PER_WEEK = 2             # the novelty target; at least 1 while the queue lasts
NEW_HARD_MAX = 3             # a slot with nothing else may pull one extra new dish
GRAINS = ("sd-buckwheat", "sd-bulgur", "sd-barley")
BREAKFAST_PATTERN = ("breakfast-oats", "breakfast-egg", "breakfast-other", "breakfast-oats",
                     "breakfast-egg", "breakfast-oats", "breakfast-other")
SIDE_FOR = {"salad": "sd-salad", "egg": "sd-egg", "matsun": "sd-matsun"}
POULTRY = ("chicken", "turkey")


class GenerationError(Exception):
    """A week the rules can't fill from the library -- shown plainly, owner alerted."""


# ------------------------------------------------------------------ library

def library(dishes):
    """The parsed dishes.md rows that carry a generator slot, in file order."""
    out = []
    for i, d in enumerate(dishes.values()):
        slot = (d.get("slot") or "").strip()
        if slot and slot not in ("—", "-"):
            out.append(dict(d, slot=slot, order=i,
                            protein=(d.get("protein") or "").strip(),
                            status=(d.get("status") or "staple").strip().lower(),
                            side=(d.get("side") or "").strip(),
                            group=(d.get("group") or "").strip()))
    return out


def protein(dishes, dish_id):
    return ((dishes.get(dish_id) or {}).get("protein") or "").strip()


# ------------------------------------------------------------------ history

class History:
    """Which week each dish was last used in, and which dishes the family has had."""

    def __init__(self):
        self.last_week = {}

    def add(self, week, ids):
        for i in ids:
            self.last_week[i] = week

    def seen(self, dish_id):
        return dish_id in self.last_week

    def rest_ok(self, dish_id, week, weeks=1):
        """Not used in the last `weeks` weeks (1: never the week after -- a hard rule;
        2: what the generator tries first, so a month doesn't alternate two menus)."""
        return self.last_week.get(dish_id, -99) < week - weeks

    def key(self, d):
        """Least recently used first, then library order."""
        return (self.last_week.get(d["id"], -99), d["order"])


def week_ids(week_md):
    """Every dish id in a parsed week's day table."""
    out = []
    for meals in week_md["days"].values():
        for cell in meals.values():
            out += pv.ids_in(cell)
    return out


# ------------------------------------------------------------------ one generated week

class Builder:
    def __init__(self, lib, dishes, week, hist):
        self.lib, self.dishes, self.week, self.hist = lib, dishes, week, hist
        self.used, self.groups, self.new = set(), set(), []
        self.queue = [d for d in lib if d["status"] == "new" and not hist.seen(d["id"])]
        self.warnings = []

    def rotation(self, slot):
        return [d for d in self.lib if d["slot"] == slot
                and (d["status"] != "new" or self.hist.seen(d["id"]))]

    def ok(self, d, need=None, group=True, rest=1):
        return (d["id"] not in self.used
                and (not rest or self.hist.rest_ok(d["id"], self.week, rest))
                and not (group and d["group"] and d["group"] in self.groups)
                and (need is None or need(d)))

    def take(self, d):
        self.used.add(d["id"])
        if d["group"]:
            self.groups.add(d["group"])
        if d["status"] == "new" and not self.hist.seen(d["id"]) and d["id"] not in self.new:
            self.new.append(d["id"])
        return d["id"]

    def planned_new(self):
        """Up to NEW_PER_WEEK queue dishes, in library order, one per slot -- lunch and
        dinner dishes first (they bring the variety); a new breakfast fills a spare place."""
        out, slots = [], set()
        meals_first = sorted(self.queue, key=lambda d: (d["slot"].startswith("breakfast"), d["order"]))
        for d in meals_first:
            if d["slot"] in slots or d["slot"] in ("side", "project"):
                continue
            out.append(d)
            slots.add(d["slot"])
            if len(out) == NEW_PER_WEEK:
                break
        return {d["slot"]: d for d in out}

    def pick(self, slot, need=None, planned=None):
        """One dish for a slot, trying in order: the planned new dish; the least recently
        used rotation dish not eaten in the last two weeks; the next new dish in the queue
        (up to NEW_HARD_MAX a week); a rotation dish not eaten last week; then softer -- a
        second dish of one group, then a dish from last week (never one already in this
        week). `need` (legume, poultry) is never relaxed."""
        if planned and planned.get(slot) and self.ok(planned[slot], need):
            return self.take(planned.pop(slot))
        rot = sorted(self.rotation(slot), key=self.hist.key)
        queue = [d for d in self.queue if d["slot"] == slot]
        room = len(self.new) + len(planned or {}) < NEW_HARD_MAX   # planned ones are coming
        steps = ((rot, {"rest": 2}), (queue if room else [], {}), (rot, {}),
                 (rot, {"group": False}), (rot, {"group": False, "rest": 0}),
                 (queue, {"group": False}))
        for cands, relax in steps:
            for d in cands:
                if self.ok(d, need, **relax):
                    return self.take(d)
        raise GenerationError("week %d: no %s dish left that fits the rules" % (self.week, slot))

    def side(self, dish_id, lunch_grains):
        kind = (self.dishes.get(dish_id) or {}).get("side", "").strip()
        if kind == "grain":
            options = [g for g in GRAINS if g not in lunch_grains] or list(GRAINS)
            g = min(options, key=lambda g: (self.hist.last_week.get(g, -99), GRAINS.index(g)))
            lunch_grains.append(g)
            self.hist.last_week[g] = self.week
            return [g]
        return [SIDE_FOR[kind]] if kind in SIDE_FOR else []


def _legume(d):
    return d["protein"] == "legume"


def generate(lib, dishes, week, hist):
    """{days: {Mon: {breakfast, lunch, dinner, prep}}, batch, new, warnings} -- cells in the
    week-file Markdown (ids in backticks), so a written file reads back identically."""
    b = Builder(lib, dishes, week, hist)
    planned = b.planned_new()

    main_b = b.pick("main", _legume, planned)
    soup = main_a = None
    planned_soup = planned.pop("soup", None)
    rot = sorted(b.rotation("soup"), key=hist.key)
    queued = [d for d in b.queue if d["slot"] == "soup" and d is not planned_soup]
    if "main" in planned:
        # a planned new main decides the legume side: prefer soups that leave room for it
        fits = lambda d: _legume(d) != _legume(planned["main"])  # noqa: E731
        rot = [d for d in rot if fits(d)] + [d for d in rot if not fits(d)]
        queued = [d for d in queued if fits(d)] + [d for d in queued if not fits(d)]
        if not any(fits(d) and b.ok(d) for d in rot) and len(b.new) + 2 <= NEW_HARD_MAX:
            rot = [d for d in queued if fits(d)][:1] + rot
    soups = ([planned_soup] if planned_soup else []) + rot + [d for d in queued if d not in rot]
    soups = [x for x in soups if b.ok(x, rest=2)] + [x for x in soups if not b.ok(x, rest=2)]
    for s in soups:
        unplanned_new = s is not planned_soup and s["status"] == "new" and not hist.seen(s["id"])
        if not b.ok(s) or (unplanned_new and len(b.new) + len(planned) >= NEW_HARD_MAX):
            continue
        want_legume = not _legume(s)
        try:
            b.used.add(s["id"])
            main_a = b.pick("main", lambda d, w=want_legume: _legume(d) == w, planned)
            b.used.discard(s["id"])
            soup = b.take(s)
            break
        except GenerationError:
            b.used.discard(s["id"])
    if soup is None:
        raise GenerationError("week %d: no soup and batch lunch pair fits the legume rule" % week)

    fish1 = b.pick("fish", None, planned)
    fish2 = b.pick("fish", None, planned)
    egg = b.pick("egg", None, planned)
    light = b.pick("light", None, planned)
    poultry_main = protein(dishes, main_a) in POULTRY     # Sunday first: it may be constrained
    wk2 = b.pick("weekend", None if poultry_main else (lambda d: d["protein"] in POULTRY), planned)
    wk1 = b.pick("weekend", None, planned)

    grains, sides = [], {}

    def cell(dish_id, extra=None):
        """`dish` + its side; the second day of a batch dish keeps the first day's side."""
        if dish_id not in sides:
            sides[dish_id] = b.side(dish_id, grains)
        text = " + ".join("`%s`" % i for i in [dish_id] + sides[dish_id])
        return text + (" " + extra if extra else "")

    def prep_of(dish_id):
        d = dishes.get(dish_id) or {}
        p = (d.get("prep") or "").strip()
        if not p or p in ("—", "-"):
            return ""
        return "%s: %s%s" % (short_name(d.get("name") or dish_id), p[0].lower(), p[1:])

    days = {
        "Mon": {"lunch": cell(main_a), "dinner": cell(soup)},
        "Tue": {"lunch": cell(main_a), "dinner": cell(soup)},
        "Wed": {"lunch": cell(main_b), "dinner": cell(fish1)},
        "Thu": {"lunch": cell(main_b),
                "dinner": cell(egg)},
        "Fri": {"lunch": cell(fish2), "dinner": cell(light)},
        "Sat": {"lunch": cell(wk1), "dinner": "`wk-scoolinary`"},
        # Sunday evening is the batch session: dinner is lunch's leftovers, with plain greens
        # (not sd-salad: its lavash doubled the lavash of dishes served with it, 2026-11-16)
        "Sun": {"lunch": cell(wk2), "dinner": "`%s` (leftovers, small portion) + `sd-greens`" % wk2},
    }
    # breakfasts: the fixed pattern, least recently used within each kind, never the
    # same breakfast two days running
    # (Monday's breakfast never needs an evening prep: Sunday evening is the batch session)
    prev = None
    for i, d in enumerate(pv.DAYS):
        kind = BREAKFAST_PATTERN[i]

        def fits(x, i=i, prev=prev):
            return x["id"] != prev and not (i == 0 and (x.get("prep") or "").strip() not in ("", "—", "-"))
        planned_bf = planned.get(kind)
        if planned_bf is not None and len(b.new) < NEW_PER_WEEK and fits(planned_bf):
            pick = planned.pop(kind)
        else:
            pool = [x for x in b.rotation(kind) if fits(x)]
            if not pool:
                raise GenerationError("week %d: no %s dish" % (week, kind))
            pick = min(pool, key=lambda x: (hist.last_week.get(x["id"], -99), x["order"]))
        b.take(pick)
        hist.last_week[pick["id"]] = week + i / 10.0      # LRU within the week
        days[d]["breakfast"] = "`%s`" % pick["id"]
        prev = pick["id"]
    for i, d in enumerate(pv.DAYS):
        nxt = days[pv.DAYS[(i + 1) % 7]]
        days[d]["prep"] = ""
        if i < 6:
            preps = [prep_of(x) for x in pv.ids_in(nxt["breakfast"] + nxt["lunch"] + nxt["dinner"])
                     if pv.ids_in(days[d]["lunch"] + days[d]["dinner"]).count(x) == 0]
            days[d]["prep"] = " · ".join(p for p in dict.fromkeys(preps) if p)
    days["Sat"]["prep"] = " · ".join(x for x in (days["Sat"]["prep"], "Shopping for the Sunday batch") if x)
    # Sunday has no "prep for tomorrow": next week's batch is cooked on Sunday itself and
    # shows as that day's "Batch cooking" line (plan_view._batch_today)
    eggs = any("bf-eggs-boiled" in days[d]["breakfast"] for d in pv.DAYS[:3])
    def ahead(dish_id):
        """A Sunday-batch dish's soak happens the evening before -- in last week's days."""
        p = ((dishes.get(dish_id) or {}).get("prep") or "").strip()
        if not p or p in ("—", "-"):
            return "`%s`" % dish_id
        return "`%s` (%s%s)" % (dish_id, p[0].lower(), p[1:].replace("tonight", "the evening before"))
    batch = [("Sunday", "≈ 90 min", "%s · %s%s" % (ahead(main_a), ahead(soup), " · boil 6 eggs" if eggs else "")),
             ("Wednesday", "≈ 45 min", "`%s`" % main_b)]
    if not b.new and b.queue:
        b.warnings.append("week %d has no new dish although the queue has %d" % (week, len(b.queue)))
    left = len(b.queue) - len(b.new)
    if left <= 4:
        b.warnings.append("only %d new dishes left in the dishes.md queue after week %d — add "
                          "sourced dishes (status new) to keep something new every week" % (left, week))
    return {"days": days, "batch": batch, "new": list(b.new), "warnings": b.warnings}


def short_name(name):
    """'Harissa — chicken and wheat porridge' -> 'Harissa'; 'Overnight oats soaked in
    matsun, with …' -> 'Overnight oats'; 'Oat porridge (hercules) cooked in water …' ->
    'Oat porridge (hercules)'. Words from the library only -- a name that shortens badly is
    renamed in dishes.md (the short name is the day's title in the menu)."""
    n = name.split(" — ")[0].split(", ")[0]
    for cut in (" with ", " in ", " from ", " cooked ", " soaked "):
        if cut in n[3:]:
            n = n[:n.index(cut, 3)]
    return n.strip()


# ------------------------------------------------------------------ any plan week

def _file_week(root, week):
    md = pv.read_week_file(root, week)
    return pv.parse_week(md) if md is not None else None


def week_menu(root, dishes, week, ignore_file=False):
    """{number, source: file|trial|generated, days, batch, notes, new, warnings} for any
    plan week >= 1, or raises GenerationError. `new` = dish ids the family has never had
    before this week (computed from the earlier weeks, also for file weeks)."""
    week = max(week, 1)
    lib = library(dishes)
    status = {d["id"]: d["status"] for d in lib}
    trial = _file_week(root, 1)
    hist = History()
    if trial is not None:
        # the trial menu counts as eaten two weeks before week 5: its dishes may return
        # in week 5, but least-recently-used puts every dish it didn't have first
        hist.add(FIRST_GENERATED - 2, week_ids(trial))
    if week < FIRST_GENERATED:
        own = _file_week(root, week)
        if own is not None:
            return dict(own, number=week, source="file", new=[], warnings=[])
        if trial is None:
            raise GenerationError("no week-01.md for the trial weeks")
        return dict(trial, number=1, source="trial", new=[], warnings=[])
    out = None
    for w in range(FIRST_GENERATED, week + 1):
        own = None if (ignore_file and w == week) else _file_week(root, w)
        if own is not None:
            ids = week_ids(own)
            new = [i for i in dict.fromkeys(ids) if status.get(i) == "new" and not hist.seen(i)]
            cur = dict(own, number=w, source="file", new=new, warnings=[])
            hist.add(w, ids)
        else:
            g = generate(lib, dishes, w, hist)
            cur = dict(g, number=w, source="generated", notes=[])
            hist.add(w, week_ids(cur))
        out = cur
    out["warnings"] = out.get("warnings", []) + check_rules(dishes, out)
    return out


# ------------------------------------------------------------------ balance + rules

MEAL_KEYS = ("lunch", "dinner")


def meal_proteins(dishes, cell):
    """The proteins one meal cell serves (main dish + sides), each counted once."""
    return {protein(dishes, i) for i in pv.ids_in(cell)} - {"", "—", "-"}


def balance(dishes, menu):
    """{fish, legume, poultry, egg, red_meat, oats}: how many meals of each this week."""
    counts = {"fish": 0, "legume": 0, "poultry": 0, "egg": 0, "red_meat": 0, "oats": 0}
    for d in pv.DAYS:
        meals = menu["days"].get(d) or {}
        for k in ("breakfast",) + MEAL_KEYS:
            ps = meal_proteins(dishes, meals.get(k, ""))
            counts["fish"] += "fish" in ps
            counts["legume"] += "legume" in ps
            counts["poultry"] += bool(ps & {"chicken", "turkey"})
            counts["egg"] += "egg" in ps
            counts["red_meat"] += bool(ps & {"beef", "lamb", "pork"})
        if any((dishes.get(i) or {}).get("slot") == "breakfast-oats"
               for i in pv.ids_in(meals.get("breakfast", ""))):
            counts["oats"] += 1
    return counts


def check_rules(dishes, menu):
    """Plain sentences for every weekly rule a menu breaks ([] = all kept)."""
    c = balance(dishes, menu)
    out = []
    if c["fish"] < 2:
        out.append("fish %d× (rule: at least 2)" % c["fish"])
    if not 3 <= c["legume"] <= 4:
        out.append("legumes %d× (rule: 3–4)" % c["legume"])
    if c["poultry"] < 2:
        out.append("chicken or turkey %d× (rule: at least 2)" % c["poultry"])
    if c["oats"] < 3:
        out.append("oat breakfasts %d× (rule: at least 3)" % c["oats"])
    if c["red_meat"] > 1:
        out.append("red meat %d× (rule: at most 1)" % c["red_meat"])
    for d in pv.DAYS:
        meals = menu["days"].get(d) or {}
        if sum("legume" in meal_proteins(dishes, meals.get(k, "")) for k in MEAL_KEYS) > 1:
            out.append("%s has two legume meals" % d)
    return ["week %d: %s" % (menu.get("number", 0), x) for x in out]


def week_ingredients(root, week):
    """The shopping words for a week's dishes (dishes.md `buy`), sorted, no amounts --
    for the groceries side (lib/basket.py) to map onto basket.md rows."""
    dishes = pv.parse_dishes(pv.read_dishes(root))
    menu = week_menu(root, dishes, week)
    out = set()
    for i in week_ids(menu):
        for w in ((dishes.get(i) or {}).get("buy") or "").split(";"):
            if w.strip():
                out.add(w.strip())
    return sorted(out)


def week_shopping(root, week):
    """[(word, [short dish name, ...])] for a week's menu, in first-use order (Monday first):
    each dishes.md `buy` word with the dishes that need it -- what the tick list adds for the
    menu (shopping/checklist.py). A side's words name the dish it is served with. Raises
    GenerationError like week_menu."""
    dishes = pv.parse_dishes(pv.read_dishes(root))
    menu = week_menu(root, dishes, week)
    out = {}
    for d in pv.DAYS:
        meals = menu["days"].get(d) or {}
        for k in ("breakfast", "lunch", "dinner"):
            ids = pv.ids_in(meals.get(k, ""))
            mains = [i for i in ids if (dishes.get(i) or {}).get("slot") != "side"]
            for i in ids:
                dish = dishes.get(i) or {}
                # a side is named by the dish it comes with ("for Sheet-pan salmon")
                owner = dishes.get(mains[0]) if mains and dish.get("slot") == "side" else dish
                n = short_name((owner or {}).get("name") or i)
                for w in (dish.get("buy") or "").split(";"):
                    w = w.strip()
                    if w:
                        names = out.setdefault(w, [])
                        if n not in names:
                            names.append(n)
    return list(out.items())


# ------------------------------------------------------------------ writing week files

def render_md(week, monday, menu):
    end = monday + timedelta(days=6)
    lines = [
        "# Week %d · %d %s – %d %s %d" % (week, monday.day, monday.strftime("%b"), end.day,
                                          end.strftime("%b"), end.year),
        "",
        "Written by `python -m coach.menu_gen --write %d %d` from [dishes.md](dishes.md) with the" % (week, week),
        "rules in [principles.md](principles.md). Edit any cell by hand — this file then wins",
        "over the generator, and later weeks are built around what it says.",
        "",
    ]
    if menu["new"]:
        lines += ["New this week: " + " · ".join("`%s`" % i for i in menu["new"]), ""]
    lines += ["## Batch sessions", ""]
    for name, effort, text in menu["batch"]:
        lines.append("**%s (%s):** %s" % (name, effort, text))
    lines += ["", "## The week", "",
              "| Day | Breakfast | Lunch | Dinner (≤ 19:00) | Prep for tomorrow |",
              "|---|---|---|---|---|"]
    for d in pv.DAYS:
        m = menu["days"][d]
        lines.append("| **%s** | %s | %s | %s | %s |" % (d, m["breakfast"], m["lunch"], m["dinner"],
                                                       m.get("prep") or "—"))
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate plan week menus.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", nargs=2, type=int, metavar=("FROM", "TO"))
    g.add_argument("--show", type=int, metavar="WEEK")
    ap.add_argument("--force", action="store_true", help="overwrite an existing week file")
    a = ap.parse_args(argv)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dishes = pv.parse_dishes(pv.read_dishes(root))
    start = pv.plan_start(root) or date(2026, 10, 19)
    sys.stdout.reconfigure(encoding="utf-8")
    weeks = [a.show] if a.show else list(range(a.write[0], a.write[1] + 1))
    for w in weeks:
        menu = week_menu(root, dishes, w, ignore_file=a.force)
        md = render_md(w, start + timedelta(weeks=w - 1), menu)
        if a.show:
            print(md)
        else:
            path = os.path.join(root, "plan", "meals", "week-%02d.md" % w)
            if os.path.exists(path) and not a.force:
                print("kept %s (exists; --force to overwrite)" % path)
                continue
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(md)
            print("wrote %s" % path)
        for x in menu["warnings"]:
            print("  ! " + x)
    return 0


if __name__ == "__main__":
    sys.exit(main())
