# COACH_CONTEXT.md — start here

**Purpose:** make a new chat session productive in one read. Attach or paste this file at
the start of a session about the Family Coach Bot. It carries what the other docs do not:
measured facts about this specific machine, the working method, current build state, and
the list of reasonable-sounding suggestions that are already rejected here and why.

Last updated: 2026-07-29, at the close of the architecture round.

---

## 1. Read order

1. **This file** — context, method, current state.
2. `CLAUDE.md` (repo root) — operating rules. The frozen `lib/` rule and storage
   invariants are non-negotiable.
3. `docs/COACH_SPEC.md` — the full v2 specification.
4. `docs/DECISIONS.md` — 70 numbered decisions with reasons. Check here before proposing
   anything; most alternatives have already been argued.

`docs/` in Git is the source of truth. The Google Doc "Family Assistant — Current
Architecture (shared context)" is a synced copy for chat sessions, and covers the
**travel** system. Until the nightly docs-mirror job exists (Phase 0), keeping the Doc
current is manual.

---

## 2. The system in one paragraph

An always-on Windows 11 laptop runs two subsystems out of one private repo
(`D:\Claude\family-assistant`, GitHub `asryandavit/family-assistant`, branch `main`),
behind one Telegram bot: a **travel monitor** (Wizz Air fares, Booking.com and Airbnb
stays, Google Sheets storage) that is complete and verified, and a **family coach bot**
(training + meals for two adults and a toddler, SQLite storage) that is fully designed
and not yet built. Jobs are self-contained scripts that gather data, write storage, send
their own Telegram message and exit. A long-running listener owns the Telegram polling
loop and launches whitelisted jobs as child processes. All model calls go through
`claude -p` (Claude Code CLI) as a subprocess on a Max subscription — never the Anthropic
API.

**Family:** Davit (senior full-stack dev, 14 yrs, React/NestJS, heavy Claude Code user),
wife, son born 29 Dec 2024. Home airport EVN, timezone Asia/Yerevan (UTC+4). Both adults
are Telegram `owner` role. English only.

---

## 3. Working method — non-negotiable

**One step at a time.** Give one thing to do, then wait for pasted console output. Never
stack three steps and hope. Read the pasted output carefully — real bugs have been caught
in output that looked fine.

**Never guess at external data.** When data comes from a website, an API, a file format
or a library's actual behaviour: run a discovery script, capture the real payload or
behaviour, inspect it, *then* write code against real structure. Every time this was
skipped in the sibling project, a bug shipped.

**Test before shipping.** Fixtures from real captured data, assertions, run them, show
passing output. Bugs this caught previously: a weekly total read as a nightly rate (7x
error), currencies summed across HUF/USD/EUR, a dedup key collapsing every inbound flight
into one.

**Numbers are code, words are AI.** All arithmetic in deterministic, unit-tested Python.
The model judges and phrases, receives final numbers, and is instructed never to
recalculate them. A model failure degrades to no output, never to a wrong number.

**When something breaks:** diagnose the actual cause before proposing a fix. If your own
code was wrong, say so directly. If the premise is wrong, say so. Honest pushback over
agreement.

**Design defaults:** fail loudly to the owner, never silently to a log nobody reads ·
queue to disk on a failed write rather than discarding data · notify before persisting ·
every state must be representable ("away", "ill", "paused", "inventory stale" are states,
not failure streaks) · every ranking or decision carries a human-readable reason.

### Delivery format

- Complete files, never fragments to splice together. State the exact destination path.
- **Every message that emits files ends with one paste-ready PowerShell block** that
  moves them all from `C:\Users\davoa\Downloads` to their destinations, creates any
  missing folders with `New-Item -ItemType Directory -Force`, uses `-Force` on
  `Move-Item` so re-running is safe, restarts the listener if a loaded file changed, and
  finishes with a verification command.
- Listener restart is stop / sleep 3 / start — there is no `Restart-ScheduledTask`, and
  the singleton port needs a moment to release.
- **PowerShell traps, all hit for real:** inline `python -c` with f-strings or braces gets
  mangled by quoting — write a temp `.py` with `Set-Content -Encoding UTF8` instead.
  Never use `>` to write a Python file: it produces UTF-16 with a BOM and Python rejects
  it. Unsigned `.ps1` files are blocked by execution policy — paste commands directly, or
  use `powershell -ExecutionPolicy Bypass -File`.
- Claude Code writes to disk directly and needs no move block, but must still report the
  exact paths it created or changed and give the commands to run its tests and demo.

### Question format

One topic per message. Recommendation first, with a short reason and a concrete example,
then **one clearly-marked question with example answers**. Do not stack a diagnostic, two
corrections and three questions into one message — that has failed here before.

---

## 4. Verified environment facts

Measured on this machine, not assumed. Dates are when measured.

**Runtime (2026-07-29)**
- Python 3.14.6, SQLite engine 3.50.4, `sqlite3.threadsafety = 3`.
- `sqlite3.version` was **removed** in Python 3.14 — use `sqlite3.sqlite_version` only.

**SQLite behaviour (2026-07-29, measured via `tmp\sqlite_probe.py`)**
- `D:` is a fixed local disk (drive type 3). WAL engages: `journal_mode` returns `wal`,
  and `-wal` / `-shm` sidecars are created.
- `STRICT` tables supported. Measured acceptance and rejection:
  - `REAL ← 84.3` accepted · `REAL ← '84.3'` **accepted**, stored as real (lossless
    conversion) · `REAL ← 'eighty-four'` rejected (`IntegrityError`)
  - `INTEGER ← 3.7` rejected · `INTEGER ← 3.0` **accepted**, silently truncated to `3`
  - → STRICT is a backstop, not a validator. Parse-at-the-edge is mandatory.
- Read during an uncommitted write: OK in 0.027s, sees only committed rows.
- Second writer with `busy_timeout=3000`: waited **3.40s** then `database is locked`.
  ~13% overshoot; budget ~5.5s at the configured 5000ms.
- `synchronous` defaults to `2` (FULL). Keep it.

**Host (2026-07-29)**
- **Dell Inspiron 5577 laptop** (`PCSystemType 2`), battery present, on AC. Not a desktop —
  the "always-on PC" in the original spec is a laptop that is usually on.
- Idle sleep, hybrid sleep and hibernate are all `0` on AC. Two sleep events in 14 days,
  both resolved within 7 seconds (aborted attempts). This machine effectively does not
  sleep.
- `RTCWAKE = 0x2` ("important wake timers only") — Task Scheduler wake requests do not
  qualify, so `WakeToRun` would be a no-op. Do not rely on it.
- Zero unexpected shutdowns (event 41) in 14 days. Note a laptop battery masks mains cuts.
- **7-Zip is not installed** — absent from PATH, Program Files, Program Files (x86),
  LOCALAPPDATA\Programs and the WinGet shim directory. Use `pyzipper`.

**Scheduled tasks (2026-07-29)**

| | Listener | Travel |
|---|---|---|
| Trigger | at logon | daily 08:00 |
| LogonType | Interactive | Interactive |
| StartWhenAvailable | False | True |
| MultipleInstances | IgnoreNew | IgnoreNew |
| ExecutionTimeLimit | P3650D | PT30M |
| RestartCount / Interval | 999 / PT1M | 0 |
| DisallowStartIfOnBatteries | False | **True** |
| RunLevel | Limited | Limited |

- `LastTaskResult 267009` on the listener is `0x41301`, `SCHED_S_TASK_RUNNING` — benign.
- **Diagnosed 2026-07-26:** the travel scan did not run that day. `NumberOfMissedRuns=1`,
  machine continuously up since 19:04 the previous evening, listener `LastRun 11:16` (a
  logon trigger firing) — i.e. an overnight Windows Update reboot left the box at the
  login screen with no interactive session. A competing explanation exists
  (`DisallowStartIfOnBatteries=True`) and the evidence cannot separate them. Coach tasks
  use `S4U` + battery-safe, which closes both paths. **Nothing alerted anyone.**

**Google Sheets (2026-07-29, travel spreadsheet)**
- Tabs and row counts: `Flights` 287 · `Trips` 84 · `Stays` 43 · `Runs` 41.
- Replay queue **empty** — the `lib/sheets.py` spreadsheet-id cutover is clean if done now.
- Service account: `sheets-writer@family-assistant-503305.iam.gserviceaccount.com`.
- Env: `TELEGRAM_BOT_TOKEN` set (46 chars), `TELEGRAM_CHAT_ID` set (9 chars — a single
  chat id, which is why `lib/telegram.py` needs the multi-chat change),
  `ANTHROPIC_API_KEY` correctly unset.

**Unverified — do not assume**
- Whether `claude -p` works under an `S4U` scheduled task. S4U runs as the user without
  an interactive session; whether the CLI's stored credentials resolve there is unknown.
  Sunday 16:00 generation and the monthly review depend on it; the nightly job does not.
  **First Phase 0 discovery item**, tested with a throwaway task.
- `pyzipper` round-trip on this machine.
- Whether a two-*process* (rather than two-connection) SQLite lock behaves as measured.
  Same file-level locking, so expected — but untested.

---

## 5. Repo inventory (2026-07-29)

```
config.json  areas.json  stations.json  requirements.txt  .gitignore  README.md
CLAUDE.md  machine.example.json  listener.py  selfcheck.py
lib\        config sheets telegram claude fx parse_wizz parse_stays parse_cmd
            movement trips score_stays fmt tasks stations
scrapers\   wizz_fare_finder stays
jobs\       travel_scan stays_scan  + training.py meals.py  (STALE SKELETON)
prompts\    travel_analysis.md  + training.md meals.md  (STALE SKELETON)
scheduler\  register-listener.ps1  register-tasks.ps1
docs\       COACH_SPEC.md  DECISIONS.md  COACH_CONTEXT.md
root debug  debug_wizz.py debug_stays.py debug_stays2.py peek_stays.py extract_stays.py
```

**Three reconciliations required in Phase 0**, all found by `selfcheck.py`:

1. `jobs\training.py`, `jobs\meals.py`, `prompts\training.md`, `prompts\meals.md` are
   stale skeleton files, and `selfcheck.py` also checks for scheduled tasks named
   `FamilyAssistant-Training` / `FamilyAssistant-Meals`. The architecture uses
   `jobs/coach_*.py` and `FamilyAssistant-Coach-*`. Same "two meanings for one name"
   problem as the placeholder `HEADERS` entries in `lib/sheets.py`. Delete or repurpose
   before Claude Code assumes they are the target.
2. `selfcheck.py` expects `ARCHITECTURE.md` at the repo root; the documentation
   requirement puts it in `docs/`. Pick one and update `selfcheck.py`.
3. `config.claude_cmd` already exists, so `claude_cli` in `machine.example.json` is a
   duplicate — drop it and use the existing config key.

`selfcheck.py` currently covers the travel system only. Extending it to coach modules,
config keys and scheduled tasks is decision 070.

---

## 6. Current state and what happens next

**Built:** travel monitor, complete and verified end to end.
**Designed, not built:** the entire coach bot. Zero coach code exists.

Phase order: **0** scaffold → **1** core + full interview → **2** training →
**GO LIVE, two weeks of real use** → **3a** recipe capture → **3b** meal generation →
**4** interconnection → **5** polish.

Immediate next steps, in order:

1. Review the ~50-question interview catalogue on paper (decision 061 requires this
   before Phase 1 builds it; not needed for Phase 0).
2. Write the Phase 0 brief.
3. Phase 0 opens with the `claude -p` under S4U test, because two scheduled jobs depend
   on an answer nobody has.

Phase 0 also produces `docs/REGRESSION.md`, `docs/RUNBOOK.md` and `docs/SECRETS.md`, and
Phase 1 produces `docs/RECOVERY.md`. These are deliberately unwritten until the phase
that makes them true — an untested runbook is the same hypothesis as an untested backup.

---

## 7. Already rejected — do not re-propose without new information

Each of these is a reasonable default that is wrong *here*, for a recorded reason.

| Suggestion | Why it is rejected | Decision |
|---|---|---|
| A separate `family-coach` repo | Jobs already isolate failure; `lib/` would have to be duplicated | 001 |
| A second Telegram bot token | Only *receiving* is exclusive; one poller is enough | 002 |
| SQLAlchemy / Alembic | Auditability under Claude Code; ORM bugs do not look like bugs in review | 005 |
| `synchronous = NORMAL` for WAL throughput | No throughput to buy; can lose committed transactions | 009 |
| Deferred `BEGIN` (Python's default) | Upgrade deadlock produces `SQLITE_BUSY` that `busy_timeout` cannot rescue | 008 |
| `check_same_thread=False` | Turns a loud error into silent corruption | 012 |
| `threading.local()` connections | Leak when job threads die | 012 |
| A file copy for backups | A live database with a hot WAL restores to a state that never existed | 014 |
| 7-Zip for encryption | Not installed; a binary path breaks the portability rule | 015 |
| python-telegram-bot v21 | `ConversationHandler` needs custom persistence anyway, and asyncio would force rewriting the verified travel handlers | 020 |
| `last_update_id` in SQLite | Makes travel commands depend on the coach database | 024 |
| Ageing callback queries by `message.date` | That is when the *bot* sent the message; would fail the legacy-button test | 027 |
| Overloading `/cancel` to exit a wizard | `/cancel` kills jobs; ambiguity is dangerous | 023 |
| Reading numbers back from Google Sheets | A hand-edit would become an input | 032 |
| One shared coach Sheet with interleaved rows | Drive sharing is per-file; revocation must be atomic | 033, 035 |
| `WakeToRun` on a scheduled task | `RTCWAKE=0x2`; Task Scheduler wakes do not qualify | 043 |
| Letting the model name exercises or foods | Drifts to dumbbells and invented nutrition values | 054, 055 |
| A 21-day plateau window | Weekly weigh-ins make that three readings | 058 |
| Cutting calories on a flat scale | That is what successful recomposition looks like | 058, 059 |
| Any RU / bilingual content | English only | 053 |

---

## 8. Session-opening checklist

Before proposing anything technical:

- [ ] Read `CLAUDE.md`, `docs/COACH_SPEC.md`, and the relevant part of `docs/DECISIONS.md`.
- [ ] Check §7 above — has this already been argued?
- [ ] If the proposal touches `lib/` or `listener.py`, it is its own task with a travel
      regression run, not part of a coach commit.
- [ ] If it depends on external behaviour, write a discovery script first.
- [ ] One topic, one recommendation, one question, with an example.
