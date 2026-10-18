# Family plan — food, movement, daily rhythm

A living, editable plan for Davit, Karine and their son. Plain Markdown files in Git:
change any file and the plan changes; Git keeps every previous version, so nothing is
ever lost and every edit is visible. No app, no database (decision 072).

**Not medical care.** Davit's cholesterol and gastritis and Karine's postpartum recovery
are for their doctors and physio; this plan is everyday food and movement around that.

## Start here

| If you want… | Open |
|---|---|
| **What do I do today?** | [daily-rhythm.md](daily-rhythm.md) + this week's menu [meals/week-01.md](meals/week-01.md) |
| Davit's full plan | [family/davit.md](family/davit.md) |
| Karine's full plan | [family/karine.md](family/karine.md) |
| The son's plan | [family/son.md](family/son.md) |
| How an exercise is done | [training/exercises.md](training/exercises.md) |
| When to make exercises harder / easier, safety | [training/progression.md](training/progression.md) |
| Food rules | [meals/principles.md](meals/principles.md) |
| Dish list | [meals/dishes.md](meals/dishes.md) |
| What to buy | [meals/shopping.md](meals/shopping.md) |
| How to keep it going | [habits.md](habits.md) |
| Weekly log | [tracking.md](tracking.md) |
| Why these numbers | [sources.md](sources.md) |

## The idea in one paragraph

Breakfast stays what you already love (eggs, hercules, katnashor). Lunch and dinner come
from a small rotation of Mediterranean-leaning Armenian dishes, batch-cooked twice a week
so Karine gets her time back. Davit breaks up sitting every 30 minutes and trains 3× a
week at 18:15; Karine trains 3× a week during the son's nap, starting from postpartum-safe
foundations; the son plays 3 hours a day and joins the family movement time. Portions,
not calories. Everyone starts easy and levels up by how their body handles it. Saturday
weigh-in, Sunday 10-minute review, Saturday Scoolinary project as the planned treat.

## How to change things

- **Small edits:** open the file on GitHub (phone or laptop) → pencil icon → edit → commit.
- **Or ask Claude:** "move training to mornings", "swap lobi for chickpeas", "Karine's
  self-check is clear, unlock level 2" — the files get updated and committed.
- **Rules that keep it flexible:** exercises live only in `training/exercises.md` and
  dishes only in `meals/dishes.md`, referenced by id everywhere else. Add a new one there
  first, then use it. Times live only in `daily-rhythm.md`.
- **Each new week:** copy `meals/week-01.md` to `week-02.md` and adjust.

## Roadmap

| Stage | What | Status |
|---|---|---|
| **A — Manual** | These files; you follow them by hand for 2–4 weeks, log in `tracking.md` | **now** |
| **B — Reminders** | The Telegram bot reads these files: morning brief, desk-break nudges, Sunday plan + priced Parma list | after A proves the routine |
| **C — Full coach** | The `docs/COACH_SPEC.md` design (logging, progression engine, plateau rules), seeded from these libraries | later, if wanted |

The ids in the libraries are deliberately the same shape the bot will use, so stage B/C
reads these files instead of starting over.

## Still open (fill in when you can)

- Davit's real work hours and whether he works from home → adjust `daily-rhythm.md`.
- The son's real nap and bedtime → adjust `daily-rhythm.md`.
- Karine: health notes, injuries, likes/dislikes → `family/karine.md`.
- First Scoolinary project (pizza?) → `meals/week-01.md` Saturday.
- Baseline numbers (week 0) → `tracking.md`.
