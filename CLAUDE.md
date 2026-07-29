# CLAUDE.md — working rules for this repository

This repo contains two subsystems that share one process boundary, one Telegram bot,
and one platform layer:

- `travel/` + `jobs/travel_*.py` — the existing, verified flight and accommodation monitor.
- `coach/` + `jobs/coach_*.py` — the family training and meal coach (under construction).

`docs/` is the source of truth for how this system works. Code comments are not.
If behaviour and docs disagree, the docs are wrong and must be fixed in the same commit.

---

## 1. The frozen platform rule

`lib/` and `listener.py` are shared by both subsystems. The travel monitor depends on
them at runtime: every job sends its own Telegram messages and writes its own Sheets
rows through `lib/`. A broken `lib/telegram.py` silently breaks travel alerts.

**Coach code may import from `lib/`. Coach code may not modify `lib/`.**

Any change to `lib/` or `listener.py`:

1. Is its own task and its own commit. Never bundled into a coach feature commit.
2. Is additive — existing call sites keep working with unchanged behaviour.
3. Runs the travel regression check before commit (see `docs/REGRESSION.md`).
4. Updates `docs/ARCHITECTURE.md` in the same commit.

Two `lib/` changes are already scheduled and must land in Phase 0, before any coach
logic depends on them:

- `lib/telegram.py` — optional per-message chat target, defaulting to the env chat id.
- `lib/sheets.py` — spreadsheet id carried in the replay queue, optional spreadsheet
  target on `append_rows`, coach entries in `HEADERS`.

Neither is optional and neither may be discovered mid-phase.

---

## 2. Numbers are code, words are AI

All arithmetic is deterministic Python, unit-tested. This is not a style preference —
this system computes calorie targets for a family.

- The model never calculates. It receives final numbers and phrases them.
- Every prompt that includes numbers instructs the model not to recalculate them.
- A model failure degrades to **no output**, never to a wrong number.
- Model output that fails validation is rejected and re-asked once, then falls back
  to a deterministic default. It is never partially accepted.

The model selects from allow-lists, never from memory:

- Exercises: the model returns `exercise_id` values chosen from a candidate list
  supplied in the prompt. An id outside that list is rejected. It never returns names.
- Foods: the model may only use items present in `food_db`. Missing items are added
  with sourced per-100g values first. Nutrition values are never invented.

---

## 3. Storage invariants

One connection helper. Every process uses it. No exceptions.

```
PRAGMA journal_mode = WAL          -- verified on this volume
PRAGMA busy_timeout = 5000         -- overshoots ~10%; budget 5.5s worst case
PRAGMA foreign_keys = ON           -- per connection; silently ignored inside a transaction
PRAGMA synchronous  = FULL         -- DO NOT CHANGE (see below)
```

- **`synchronous = FULL` is a do-not-change.** Lowering it to NORMAL is the standard
  WAL tuning advice and is wrong here: this system writes a handful of tiny rows a day,
  so there is no throughput to buy, and NORMAL can lose committed transactions on
  power loss.
- All coach tables are `STRICT`. STRICT is a backstop, not a validator — it accepts
  `'84.3'` into a REAL column and truncates `3.0` into an INTEGER column. Every value
  crossing into the database passes a typed parse function first (normalise decimal
  comma, strip units, range-check, reject with a human sentence).
- All writes use explicit `BEGIN IMMEDIATE`. Never deferred — two deferred transactions
  that both read then both try to write produce an immediate `SQLITE_BUSY` that
  `busy_timeout` cannot rescue.
- **No transaction is ever held across a `claude -p` call, a network call, or any
  subprocess.** Compute outside, validate outside, write inside. Writes are milliseconds.
- One connection per thread, created through the helper, never shared, never global,
  never `check_same_thread=False`. Use `with db.unit_of_work() as con:` — note that
  bare `with con:` is a transaction context manager, not a close, and does nothing
  under autocommit.
- `isolation_level=None` (autocommit) so Python's implicit transaction handling never
  fights the explicit one.
- Migrations: `PRAGMA user_version` plus numbered `migrations/00N_*.sql` applied in order.

---

## 4. Dates and times

The existing system stores UTC in the `Runs` tab, which made an 08:00 scan appear as
`04:04:59` and read as a job that never fired. That ambiguity is designed out here by
naming, not by convention:

- `*_local` — a local Asia/Yerevan date as TEXT `'YYYY-MM-DD'`. Used for day-keyed
  data: weights, meal days, workout days, freezer dates.
- `*_utc` — UTC ISO-8601 with offset. Used for event and audit timestamps.

Never `date.today()`. Always `today_local()`. Yerevan is UTC+4, so between midnight and
04:00 local the UTC date is still yesterday, and a retry that slips past midnight would
write to the wrong day.

---

## 5. Failure behaviour

- Fail loudly to the owner. Never silently to a log nobody reads.
- Queue to disk on a failed write rather than discarding collected data.
- Notify before persisting, so a storage outage cannot swallow a successful run.
- Every state is representable. "away", "ill", "paused", "inventory stale" are states,
  not failure streaks.
- Every ranking or decision carries a human-readable reason in the message that shows it.
- A job that did not run must be visible. The listener runs a staleness audit at startup
  (last snapshot, last restore drill, last travel scan, missed-run counts) and reports
  anything overdue — logon is the moment the owner is present to read it.

---

## 6. Portability

`coach.db` is the only irreplaceable artefact in this system. Every decision about it is
a portability decision.

- No absolute paths in code. Paths derive from `__file__` or from config.
- Machine-specific values (python executable, repo root, Drive folder) live only in
  `machine.json`, which is gitignored. `machine.example.json` is committed.
- Platform assumptions stay in `scheduler/` and `lib/tasks.py`. No `schtasks`, no
  Windows-only calls anywhere else. `jobs/` and `lib/` must run unchanged on
  Windows, macOS and Linux.
- Coach configuration lives in `config_coach.json`, not in `config.json`. The existing
  config is travel-shaped and already large.

---

## 7. Language

**English only.** Both users, every message, every seeded row. There is no RU content
to author, seed or test.

Messages still render through one template layer rather than hardcoded strings scattered
through handlers — that is clean code, not a dormant translation plan. Nothing bilingual
is authored.

---

## 8. Testing

- Fixtures are built from real captured data, never from assumption.
- Never write a parser against a guessed structure. Capture the actual payload to disk,
  inspect the real field names, then write the parser.
- `tests/test_db_contract.py` asserts the storage behaviour that was measured on this
  machine: STRICT rejection cases, WAL engagement, `busy_timeout` honoured under
  contention, and a foreign key violation actually raising.
- Every calculator has unit tests. Every validator has tests for the rejection path,
  not only the happy path.
- Show passing output before shipping.

---

## 9. Cadence

- One phase per session. A phase brief covers exactly one phase.
- One step at a time within a session. Wait for real console output before the next step.
- State the exact paths of every file created or changed.
- Give the exact commands to run the tests and the demo.
- No scope creep into the next phase. `travel/` is out of scope for every coach phase.

## 10. Definition of done, per phase

- `pytest` green, `ruff` clean.
- A short demo script runnable from Telegram on a phone.
- A numbered entry in `docs/DECISIONS.md`.
- Named documentation change: which file, what changed. A phase that alters behaviour
  and touches no doc is incomplete.
- Any `lib/` or `listener.py` change reflected in `docs/ARCHITECTURE.md` in the same commit.
