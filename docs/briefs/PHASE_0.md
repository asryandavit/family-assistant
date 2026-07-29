# PHASE 0 BRIEF — scaffold and shared-platform changes

Self-contained brief for one Claude Code session. Read this fully before writing anything.

---

## Before you start

Read, in this order:

1. `CLAUDE.md` (repo root) — operating rules. The frozen `lib/` rule and the storage
   invariants are non-negotiable and are not repeated in full here.
2. `docs/COACH_SPEC.md` — the specification. §5 is the data model, §12 the schedule.
3. `docs/DECISIONS.md` — 70 numbered decisions. If you are about to propose an
   alternative to something in this brief, check here first; most have been argued.
4. `docs/COACH_CONTEXT.md` §7 — the list of reasonable-sounding suggestions that are
   already rejected here, with reasons.

---

## Scope

**In scope:** the foundation. Nothing in this phase sends a real coach message, computes
a real number, or stores a real measurement.

**Explicitly out of scope.** Do not start any of these, even if the structure seems to
invite it:

- Any calculator (BMR, TDEE, targets, trend, plateau) — Phase 1
- The interview engine or any onboarding flow — Phase 1
- Any training or meal logic, `exercises` seeding, `food_db` seeding — Phase 2 / 3a
- Any coach command beyond `/health`
- Anything inside `travel/`, `scrapers/`, `jobs/travel_scan.py`, `jobs/stays_scan.py`

**Cadence.** One step at a time. Each numbered step below is its own commit. After each
step, run its verification and report the actual console output before starting the next.
Do not batch steps. If a verification fails, stop and diagnose — do not proceed and fix
later.

**This brief may need two sessions.** The natural break is after Step 6. Steps 1–6 are
discovery, cleanup and the two shared-platform edits; Steps 7–9 are the listener and
docs. If context is running short at Step 6, stop there — it is a clean boundary with
everything committed and the travel path verified.

---

## Step 1 — Discovery: does `claude -p` work under an S4U scheduled task?

**Why this is first.** The Sunday 16:00 meal generation and the monthly review both run
as scheduled tasks and both call `claude -p`. Decision 042 registers all coach tasks with
`LogonType=S4U` so they run whether or not anyone is signed in. S4U runs as the user
*without* an interactive session, and whether the Claude Code CLI's stored credentials
resolve in that context is **unverified**. If the answer is no, those two tasks need a
different trigger strategy and this brief changes.

Do not assume. Measure.

**Create** `tmp/s4u_probe.py`:

- Writes a UTF-8 log line to `tmp/s4u_probe.log` recording the timestamp, `whoami`,
  whether an interactive session is present, and the value of `USERPROFILE`.
- Invokes `claude -p` as a subprocess exactly the way `lib/claude.py` does — prompt piped
  via STDIN, `--output-format json` — with a trivial prompt such as
  `Reply with the single word OK and nothing else.`
- Appends the return code, the first 500 characters of stdout, and the first 500
  characters of stderr to the same log.
- Never raises. Every failure path writes to the log.

**Then** register a throwaway task and run it. These commands are for Davit to paste —
report them to him, do not run them yourself:

```powershell
$py   = (Get-Command python).Source
$repo = "D:\Claude\family-assistant"

$action    = New-ScheduledTaskAction -Execute $py -Argument "$repo\tmp\s4u_probe.py" -WorkingDirectory $repo
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Limited
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName "ZZ-S4U-Probe" -Action $action -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName "ZZ-S4U-Probe"
Start-Sleep -Seconds 45
Get-Content "$repo\tmp\s4u_probe.log" -Encoding UTF8
Unregister-ScheduledTask -TaskName "ZZ-S4U-Probe" -Confirm:$false
```

**Gate.** Read the log.

- **`claude -p` returned valid JSON** → S4U is confirmed. Continue.
- **It failed** (auth error, empty output, non-zero return) → **stop this step and report
  the exact output.** Do not work around it, do not fall back to a logon trigger on your
  own initiative. This is an architecture decision and needs a DECISIONS entry.

**Also verify `pyzipper`** in the same step, since it is the other unmeasured dependency:
add `pyzipper` to `requirements.txt`, install it, and write `tmp/pyzipper_probe.py` that
creates an AES-256 encrypted zip from a small temp file, reads it back with the
passphrase, asserts the round-trip matches, and asserts that a wrong passphrase raises.
Print the result. Delete the artifacts.

**Commit:** `phase0: verify claude -p under S4U and pyzipper round-trip`
(commit the probes under `tmp/` — they document what was measured; `tmp/` is gitignored,
so move them to `tests/probes/` if you want them tracked. Prefer tracked.)

---

## Step 2 — Reconcile the stale skeleton

`selfcheck.py` currently reports four files as "optional, present" that predate this
architecture and conflict with it. Left in place, a future session will assume they are
the target of coach work.

**Delete:**

- `jobs/training.py`
- `jobs/meals.py`
- `prompts/training.md`
- `prompts/meals.md`

**Edit `selfcheck.py`:**

- Remove those four from the optional-files list.
- Remove the scheduled-task checks for `FamilyAssistant-Training` and
  `FamilyAssistant-Meals`.
- Change the `ARCHITECTURE.md` check from the repo root to `docs/ARCHITECTURE.md`
  (decision: docs live in `docs/`; the root check was the older convention).

**Edit `lib/sheets.py` HEADERS** — remove the unused placeholder `Training` and `Meals`
entries. Coach entries are added in Step 6, not now. This is a deletion only.

**Edit `machine.example.json`** — remove the `claude_cli` key. `config.claude_cmd`
already exists and is the single source for that value.

**Verification:**

```powershell
cd D:\Claude\family-assistant
python selfcheck.py
python jobs\travel_scan.py
```

`selfcheck.py` must show no new failures. `travel_scan.py` must complete and send its
normal Telegram message. Report both outputs.

**Commit:** `phase0: remove stale training/meals skeleton, align selfcheck`

---

## Step 3 — Coach package scaffold and configuration

**Create the directory structure.** Every package gets an `__init__.py`.

```
coach/__init__.py
coach/core/__init__.py
coach/core/db.py
coach/core/config.py
coach/core/timeutil.py
coach/core/parse.py
coach/training/__init__.py
coach/meals/__init__.py
coach/conversation/__init__.py
coach/conversation/router.py
migrations/001_initial.sql
tests/__init__.py
tests/test_db_contract.py
tests/test_parse.py
tests/test_timeutil.py
jobs/coach_health.py
config_coach.json
```

**`config_coach.json`** — coach configuration only. Do not add coach keys to
`config.json` (decision 004). Contents:

- `users`: a list of objects `{ tg_id, name, role, sheet_id, sheet_consent }`. Seed with
  two entries; leave `tg_id` values as `null` for Davit to fill in.
- `spreadsheet_id`: the coach Sheet id (leave `null`; Davit provides it in Step 9).
- `schedule`: the七 task definitions from `COACH_SPEC.md` §12 — name, time, script,
  catch-up flag, validity window.
- `quiet_hours`: `{ "start": "22:00", "end": "07:00" }`.
- `timezone`: `"Asia/Yerevan"`.
- `feature_flags`: `{ "training": false, "meals": false }` — both modules disabled at
  this stage, per the module-isolation rule.

**`coach/core/config.py`** — loads `config_coach.json` and `machine.json`, validates that
required keys exist, and raises a clear error naming the missing key. No absolute paths
in code; everything derives from `__file__` or from `machine.json` (decision 033).

**`coach/core/timeutil.py`** — `today_local()`, `now_utc_iso()`, and helpers to format and
parse the `date_local` / `ts_utc` conventions. **Never `date.today()` anywhere in the
codebase.** Tests must cover the boundary case: at 02:00 Yerevan the UTC date is the
previous day, and `today_local()` must return the Yerevan date.

**`coach/core/parse.py`** — parse-at-the-edge (decision 007). At minimum:
`parse_weight_kg(text)` and `parse_measurement_cm(text)`. Both must normalise a decimal
comma to a point, strip units (`kg`, `кг`, `cm`, `см`), range-check (weight 30–250,
waist 40–200), and return either a float or a structured rejection carrying a
human-readable English sentence. They must never raise on user input.

**`jobs/coach_health.py`** — a standalone job following the existing job pattern: open the
database, report schema version, row counts per table, config validity, and append a
job-level row to the `Runs` tab. Sends its own Telegram message and exits. This is the
one runnable coach job in Phase 0.

**Verification:** `python jobs\coach_health.py` runs and prints; `ruff check .` is clean.

**Commit:** `phase0: coach package scaffold, config, time and parse helpers`

---

## Step 4 — Schema and the storage layer

**`migrations/001_initial.sql`** — every table from `COACH_SPEC.md` §5, all `STRICT`.
Create them all now; later phases populate them rather than migrating.

Three tables have subtle constraints. Use exactly these:

```sql
CREATE TABLE users (
  id                   INTEGER PRIMARY KEY,
  tg_id                INTEGER NOT NULL UNIQUE,
  name                 TEXT    NOT NULL,
  role                 TEXT    NOT NULL CHECK (role IN ('owner','coach_user')),
  sex                  TEXT    CHECK (sex IN ('m','f')),
  dob_local            TEXT,
  height_cm            REAL,
  activity_mult        REAL,
  breastfeeding        INTEGER NOT NULL DEFAULT 0 CHECK (breastfeeding IN (0,1)),
  clearance_confirmed  INTEGER NOT NULL DEFAULT 0 CHECK (clearance_confirmed IN (0,1)),
  postpartum_status    TEXT,
  kcal_target          INTEGER,
  protein_g_target     INTEGER,
  protein_g_per_kg     REAL    NOT NULL DEFAULT 2.0,
  deficit_pct          INTEGER NOT NULL DEFAULT 15,
  kcal_floor           INTEGER NOT NULL,
  weekday_active_min   INTEGER,
  weekend_active_min   INTEGER,
  new_dish_rate        INTEGER NOT NULL DEFAULT 1,
  waist_tracking_enabled INTEGER NOT NULL DEFAULT 0 CHECK (waist_tracking_enabled IN (0,1)),
  sheet_id             TEXT,
  sheet_consent        INTEGER NOT NULL DEFAULT 0 CHECK (sheet_consent IN (0,1)),
  paused_until_local   TEXT,
  created_ts_utc       TEXT    NOT NULL
) STRICT;

CREATE TABLE weights (
  id         INTEGER PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id),
  date_local TEXT    NOT NULL,
  kg         REAL    NOT NULL,
  waist_cm   REAL,
  hips_cm    REAL,
  context    TEXT    NOT NULL DEFAULT 'normal' CHECK (context IN ('normal','travel','paused')),
  ts_utc     TEXT    NOT NULL,
  UNIQUE (user_id, date_local)
) STRICT;

CREATE TABLE conversations (
  user_id              INTEGER PRIMARY KEY REFERENCES users(id),
  kind                 TEXT NOT NULL,
  state_json           TEXT NOT NULL,
  last_activity_ts_utc TEXT NOT NULL
) STRICT;
```

The `exercises` DDL is given in full in `COACH_SPEC.md` §5 — use it verbatim, including
every `CHECK` constraint. The `equipment` constraint is the structural enforcement of the
mat-only rule (decision 054) and must not be relaxed.

**`coach/core/db.py`** — the single connection helper every process uses. Requirements
are in `CLAUDE.md` §3 and are not negotiable. Specifically:

- One `connect()` that opens with `isolation_level=None` and sets, on the raw connection
  before any transaction: `journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON`,
  `synchronous=FULL`. `foreign_keys` is silently ignored inside a transaction, so the
  pragma block and the transaction helper must be separate functions.
- `unit_of_work()` as a context manager: opens a connection, issues `BEGIN IMMEDIATE`,
  yields, commits or rolls back, closes. One connection per thread; never shared, never
  module-level, never `check_same_thread=False`, never `threading.local()`.
- Migration runner: reads `PRAGMA user_version`, applies numbered files from
  `migrations/` in order, sets the new version. Idempotent.

**`tests/test_db_contract.py`** — assert the behaviour that was measured on this machine
(recorded in `docs/COACH_CONTEXT.md` §4), so it stays measured:

- `journal_mode` returns `wal`
- `busy_timeout` returns 5000
- `foreign_keys` returns 1, **and** inserting a `weights` row with a non-existent
  `user_id` raises
- STRICT: `REAL ← 'eighty-four'` raises; `REAL ← '84.3'` is accepted and stored as real;
  `INTEGER ← 3.7` raises; `INTEGER ← 3.0` is accepted and stored as `3`
- Lock contention: a second connection issuing `BEGIN IMMEDIATE` while the first holds a
  write transaction waits and then raises, and the elapsed time is at least the configured
  timeout
- A reader can read committed rows while a writer holds an open transaction
- Inserting a row into `exercises` with `equipment = 'dumbbell'` raises

**Verification:** `pytest -v` green; run it twice to prove the migration is idempotent.

**Commit:** `phase0: schema, storage layer, db contract tests`

---

## Step 5 — `lib/telegram.py`: per-message chat target

**This is a frozen-platform edit.** Own commit, additive only, travel regression before
committing (`CLAUDE.md` §1).

**The problem:** `_creds()` reads a single `TELEGRAM_CHAT_ID` from the environment and
every send goes there. The coach has two recipients.

**The change:** add an optional `chat_id` parameter to the public send functions. When
omitted, behaviour is byte-for-byte identical to today — the env chat id. Do not change
any existing call site. Do not change the signature order. Do not make it required.

Useful property to preserve deliberately: travel alerts pass no `chat_id`, so they
continue to reach only Davit's chat even on a shared bot (decision 041).

**Verification, all four:**

1. `python jobs\travel_scan.py` — completes, message arrives as normal
2. `python jobs\stays_scan.py` — completes, message arrives as normal
3. A one-off script sending to an explicit `chat_id` — arrives
4. `pytest -v` — green

**Update `docs/ARCHITECTURE.md`** in this same commit (`CLAUDE.md` §1). If the file does
not exist yet, create it with the generated/hand-written split described in
`docs/COACH_CONTEXT.md`; the generated section comes from `selfcheck.py` in Step 9.

**Commit:** `lib: optional per-message chat target in telegram send (additive)`

---

## Step 6 — `lib/sheets.py`: spreadsheet id in the replay queue

**Frozen-platform edit.** Own commit, additive, travel regression before committing.

**The problem (decision 040):** queue entries are `{"tab": ..., "rows": ...}` with no
spreadsheet id, and `flush_pending()` replays them against whatever config the flushing
process loaded. With two spreadsheets, a queued coach weight row replays into the *travel*
spreadsheet, silently, into a tab whose name happens to match. Both jobs call
`flush_pending()` at startup, so whichever runs first wins.

**Three changes:**

1. Queue entries carry `spreadsheet_id`. `flush_pending()` targets it.
2. **Legacy branch:** an entry with no `spreadsheet_id` key is treated as the *travel*
   spreadsheet — the only one that existed when such entries could have been written.
   Do not raise, do not default to coach.
3. `append_rows` takes an explicit optional `spreadsheet_id` parameter, defaulting to the
   configured travel spreadsheet. Callers must not mutate a copy of config to redirect
   writes.
4. Add coach entries to `HEADERS` for the tabs coach will use.

A replay targeting an unreachable spreadsheet **re-queues rather than dropping**.

The replay queue was verified empty on 2026-07-29, so this cutover is clean today —
but the legacy branch is still required and still tested.

**Verification:**

1. `pytest -v` — including a new test that writes a legacy-shaped entry (no
   `spreadsheet_id`) to a temp queue file and asserts it resolves to the travel
   spreadsheet
2. A new test asserting an unreachable target re-queues rather than dropping
3. `python jobs\travel_scan.py` — completes, row appears in the `Flights` tab
4. `python selfcheck.py` — replay queue still reports empty

**Update `docs/ARCHITECTURE.md`** in the same commit.

**Commit:** `lib: carry spreadsheet id through the sheets replay queue`

> **Natural session break.** Everything above is committed and the travel path is verified.
> If context is short, stop here and report status.

---

## Step 7 — Listener changes

**Frozen-platform edit**, and the highest-risk step in this phase. The listener is the
single process whose failure removes all interactivity. Four changes, all additive, and
the listener keeps its current shape: receive, authorise, route, launch, cancel
(decision 031).

**7.1 — Per-update exception isolation.** Today one bad update aborts the rest of the
batch and backs off. Wrap each update individually. One malformed coach message must not
stall travel commands.

**7.2 — Offset persistence, in a JSON file, not SQLite** (decision 024). Store
`last_update_id` in `.browser/listener_offset.json`. Write temp + `os.replace` (atomic on
NTFS). On read, treat missing *or* unparseable as "no offset". **Advance the offset
before processing an update, not after** — with `RestartCount 999`, an update that crashes
the process would otherwise be redelivered forever, producing an invisible crash loop
where interactivity is dead but travel alerts keep arriving on schedule.

**The startup drain splits by update type** (decision 027):

- **Messages** whose Telegram timestamp is older than 10 minutes → discard, log the count.
- **Callback queries in the startup backlog** → discard **wholesale, regardless of age**.
  A callback query has no timestamp of its own; `callback_query.message.date` is when the
  *bot* sent the message the button sits on, so ageing by it would discard a live tap on
  an old message. A pre-crash tap should be re-tapped, since "confirm rebalance" is not
  idempotent.
- `answerCallbackQuery` on a pre-crash query id fails on Telegram's side — that call must
  tolerate its own failure rather than raise.

**The 10-minute staleness check also applies at processing time**, not only at startup
(decision 028): the machine sleeps without restarting the listener, so commands typed
during a sleep arrive on wake and would otherwise fire hours late. Normal latency is
under a second, so this never fires in ordinary operation.

**7.3 — Roles.** Replace the single-chat allowlist with a `chat_id → role` map loaded
from `config_coach.json`, **default deny**. Both users are `owner` (decision 051), but the
role machinery is built now because the code must not assume one role. Travel commands
and `/cancel` check `role == 'owner'`. A denied command replies "That's owner-only" and
points at `/stop` — never silence, because silence from a visible menu item reads as a
broken bot.

**7.4 — Delegation.** The listener calls into `coach/conversation/router.py` for anything
coach-shaped. The router implements the six-step precedence from `COACH_SPEC.md` §11.

In Phase 0 the router handles exactly two things: `/health` and the fallback hint. No
conversations exist yet. **But it must already catch every database error, report it to
the user as a sentence, and never let it escape into the poll loop** (decision 025).

**Verification — all of these, and report each result:**

1. Every travel command still works: `/scan`, `/stays`, `/auto`, `/cancel`, `/menu`,
   `/status`
2. **Tap a 🏨 button on an OLD message from before this change** — unprefixed legacy
   `callback_data` must still route correctly
3. `/health` responds
4. Send a photo or a voice note — a hint comes back, not silence
5. Send an edited message — acknowledged once, not silently ignored
6. **The missing-database test:** rename `data/coach.db`, restart the listener, confirm
   `/scan`, `/stays`, `/auto`, `/cancel` and `/status` all still work while `/health`
   fails politely with a sentence. Rename it back.
7. Kill the listener process mid-poll and confirm it restarts and resumes without
   replaying a backlog

**Update `docs/ARCHITECTURE.md`** in the same commit.

**Commit:** `listener: per-update isolation, offset file, roles, coach router delegation`

---

## Step 8 — Per-role command menus and the scheduled test job

**Command menus** — `setMyCommands` with scope (decision 030). Both users currently get
the same full menu, but the scope machinery is built now. Register the coach commands
plus the existing travel commands.

**One scheduled test job.** Register `FamilyAssistant-Coach-Health` to run
`jobs/coach_health.py` daily at a time Davit picks, with the settings from
`COACH_SPEC.md` §12: `LogonType=S4U`, `AllowStartIfOnBatteries`,
`DontStopIfGoingOnBatteries`, `MultipleInstances=IgnoreNew`, `ExecutionTimeLimit=PT30M`.

Registration commands go to Davit to paste — do not run them yourself, and do not hand
him a `.ps1` file (execution policy blocks unsigned scripts).

Add task registration helpers to `scheduler/`, not to `jobs/` or `lib/` — platform
assumptions stay inside the scheduler boundary (decision 033).

**Verification:** the task appears in `Get-ScheduledTask -TaskName "FamilyAssistant-*"`,
runs on demand via `Start-ScheduledTask`, and a row appears in the `Runs` tab.

**Commit:** `phase0: per-role command scopes, coach health scheduled task`

---

## Step 9 — Documentation

**`docs/REGRESSION.md`** — the check that runs before every `lib/` or `listener.py`
commit. It must be repeatable by someone with no context in three months. Include, as an
explicit list with expected responses:

- Each travel command and what a correct response looks like
- `python jobs\travel_scan.py` and `python jobs\stays_scan.py` completing and messaging
- The missing-database test from Step 7
- **A 🏨 button tap on an old message**, to prove unprefixed legacy `callback_data` still
  routes
- `python selfcheck.py` clean, replay queue empty
- `pytest -v` green

**`docs/RUNBOOK.md`** — bring-up on a clean machine: clone, install requirements, restore
secrets, create `machine.json` from the example, restore the newest snapshot, apply
migrations, register scheduled tasks, verify. **Walk through it once and correct what is
wrong** — an untested runbook is the same hypothesis as an untested backup.

**`docs/SECRETS.md`** — inventory only, never values. Each secret: name, where it lives,
what it is for, how to re-issue it. Current inventory: `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`, the service-account JSON under `secrets/`, the coach spreadsheet id,
and the backup passphrase (env var **and** password manager, decision 016).

**Extend `selfcheck.py`** (decision 070) — coach module imports, `config_coach.json` keys,
`coach.db` presence and schema version, coach scheduled tasks, and generation of the
`docs/ARCHITECTURE.md` **generated section** (file inventory, config keys, Sheet tabs,
scheduled tasks, module list). Never hand-edit that section.

**`machine.json`** — Davit creates it from `machine.example.json`. Confirm it is
gitignored.

**Commit:** `phase0: regression, runbook and secrets docs; selfcheck covers coach`

---

## Definition of done

- [ ] `pytest -v` green, `ruff check .` clean
- [ ] `python selfcheck.py` — no new failures, coach sections present
- [ ] `python jobs\travel_scan.py` and `python jobs\stays_scan.py` both complete and message
- [ ] Every item in `docs/REGRESSION.md` passes, including the legacy-button tap and the
      missing-database test
- [ ] `/health` works from a phone; a photo gets a hint
- [ ] `FamilyAssistant-Coach-Health` registered and runs
- [ ] `docs/ARCHITECTURE.md` reflects every `lib/` and `listener.py` change
- [ ] `docs/REGRESSION.md`, `docs/RUNBOOK.md`, `docs/SECRETS.md` written; the runbook
      actually walked through
- [ ] A numbered entry appended to `docs/DECISIONS.md` recording the S4U result and
      anything discovered during the build
- [ ] Zero scope creep — no calculator, no interview, no training, no meals

## Demo script for Davit's phone

1. `/health` → schema version, row counts, config OK
2. `/scan` → travel scan starts as normal
3. `/cancel` → sweeps it
4. Send a photo → a hint comes back
5. Tap a 🏨 button on an old message → still routes
6. Tap any coach menu button → responds

## Report back

For each step: the exact console output, the files created or changed with full paths,
and the commit hash. If anything in this brief turns out to be wrong — a rule that does
not fit the code as it actually exists, an instruction that contradicts `CLAUDE.md` — say
so plainly rather than working around it.
