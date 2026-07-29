# DECISIONS.md

Numbered, dated, with the reason. Append only. Never renumber.

Decisions 001–064 were taken across the architecture round of 26–29 July 2026 and logged
together at its close, so they carry the logging date rather than individual decision
dates. From 065 onward, each entry is dated when taken.

---

## Boundary and process

**001 — 2026-07-29 — One repo, one bot, coach as modules inside `family-assistant`.**
Not a separate repo. Jobs are self-contained scripts that send their own Telegram
messages and exit, so a coach bug that kills the listener costs interactivity, not deal
alerts. `lib/` is exactly the shared platform that a second repo would have forced us to
duplicate, and the `/menu` inline-keyboard pattern the coach needs already exists here.

**002 — 2026-07-29 — One Telegram bot token, one polling process.**
`getUpdates` supports exactly one consumer per token; two pollers produce
`409 Conflict` and non-deterministic update theft. Sending is not exclusive, but
receiving is, so one program owns the loop.

**003 — 2026-07-29 — `lib/` is frozen against coach edits.**
Coach code imports from `lib/` and never modifies it. Changes to `lib/` are their own
task, their own commit, additive, with a travel regression run before commit. The real
risk surface of merging is `lib/`, not the listener.

**004 — 2026-07-29 — Coach configuration lives in `config_coach.json`.**
`config.json` is travel-shaped and already large. Separate file, separate lifecycle.

## Storage

**005 — 2026-07-29 — Plain `sqlite3` + `schema.sql`. No SQLAlchemy, no Alembic.**
Auditability under Claude Code: 12 tables of explicit SQL can be reviewed in one sitting,
whereas ORM behaviour is emergent from session scope, identity map and flush timing —
bugs that do not look like bugs in review. Matches the repo's existing stdlib conviction.
Migrations are `PRAGMA user_version` plus numbered `.sql` files.

**006 — 2026-07-29 — `STRICT` on every coach table.**
SQLite's default type affinity would store `'eighty-four'` in a REAL weight column
silently. Verified on this machine (SQLite 3.50.4): STRICT rejects it.

**007 — 2026-07-29 — STRICT is a backstop, not a validator; parse-at-the-edge is mandatory.**
Measured on this machine: `'84.3'` is accepted into REAL (lossless conversion) and `3.0`
is silently truncated into INTEGER. A decimal comma (`"84,3"`) would reach the database
and die as an `IntegrityError` — loud, but in the wrong place, in front of a user who
typed a valid weight. Every value passes a typed parse function first.

**008 — 2026-07-29 — WAL + `busy_timeout=5000` + `BEGIN IMMEDIATE` for all writes.**
Verified: WAL engages on D: (fixed local disk), readers proceed during writes (0.027s),
and a second writer waits and then fails. Deferred `BEGIN` is forbidden — two deferred
transactions that both read then both try to write produce an immediate `SQLITE_BUSY`
that `busy_timeout` cannot rescue. Measured overshoot ~13% (3.40s against 3000ms), so
budget ~5.5s worst case.

**009 — 2026-07-29 — `synchronous = FULL` is a do-not-change.**
Standard WAL advice is NORMAL for throughput. There is no throughput to buy here — a few
tiny rows a day — and NORMAL can lose committed transactions on power loss. Honest note:
zero unexpected shutdowns in 14 days and the host is a laptop with a battery, so the
justification is "costs nothing" rather than "power cuts are frequent."

**010 — 2026-07-29 — No transaction is held across a `claude -p`, network or subprocess call.**
The Sunday job runs the model for 30–90s. A transaction opened before and committed after
would block every other writer for the whole duration. This single rule is what makes
WAL + `busy_timeout` sufficient.

**011 — 2026-07-29 — `PRAGMA foreign_keys = ON` per connection, in the one connect helper.**
SQLite defaults foreign keys OFF and it is per-connection, so a schema full of
`REFERENCES` would be silently unenforced. The pragma is ignored inside a transaction, so
it must be set on the raw connection before any `BEGIN` — the pragma block and the
transaction helper cannot be the same function.

**012 — 2026-07-29 — One connection per thread; no module-level connection; `unit_of_work()`.**
`listener.py` is threaded and sqlite3 connections are not thread-safe.
`check_same_thread=False` turns a loud error into silent corruption. Not
`threading.local()` either — thread-local connections leak when job threads die. Note
that bare `with con:` is a transaction context manager, not a close, and under autocommit
does effectively nothing.

**013 — 2026-07-29 — `date_local` versus `ts_utc` encoded in column names.**
The existing `Runs` tab stores UTC, so an 08:00 scan appears as `04:04:59` and reads as a
job that never fired. Day-keyed data stores local Asia/Yerevan `'YYYY-MM-DD'`; audit
timestamps store UTC with offset. A single `today_local()` helper, never `date.today()` —
between midnight and 04:00 local the UTC date is still yesterday.

**014 — 2026-07-29 — `VACUUM INTO` for backups, never a file copy.**
A copy of a live database with a hot WAL restores to a state that never existed.

**015 — 2026-07-29 — `pyzipper` (AES-256 ZIP), not 7-Zip.**
Reverses an earlier recommendation. 7-Zip is not installed on this machine (verified: not
in PATH, Program Files, Programs, or the WinGet shim directory), and a binary path in
`machine.json` would break the portability rule on a fresh machine. A pip dependency
travels with the repo, and AES-256 ZIP opens in 7-Zip, WinRAR, PeaZip, keka and p7zip.
Honest cost: ZIP does not encrypt filenames. Snapshot filenames carry no health data.

**016 — 2026-07-29 — Backup passphrase in a Windows env var AND in the password manager.**
Corrects an earlier statement that it should live only in the password manager — an
unattended nightly job cannot encrypt with a key that is not on the machine. The off-box
copy is what survives disk failure.

**017 — 2026-07-29 — Encrypted snapshots may enter the synced folder; the live database may not.**
`VACUUM INTO` output is static and sidecar-free, which makes it safe to sync. The live
`.db` with its `-wal` and `-shm` files is not — sync clients copy them independently and
corrupt WAL databases. Staging must be on the same volume as the destination so the final
step is an atomic rename, not a cross-volume copy a sync client can watch grow.

**018 — 2026-07-29 — Automatic nightly restore drill, not a monthly manual one.**
A drill that depends on remembering is worse than none, because it will be believed to
have happened. The nightly job decrypts the snapshot it just wrote, opens it, and queries
the `weights` table. Result goes into the nightly `Runs` row so a drill that *stops
running* is distinguishable from one that passes; the monthly review states the count.

**019 — 2026-07-29 — Retention: 7 daily + 4 weekly. Same-day re-run must not crash.**
`VACUUM INTO` fails if the target exists.

## Listener

**020 — 2026-07-29 — Keep the hand-rolled polling loop. Reject python-telegram-bot v21.**
The feature that would justify PTB is `ConversationHandler`, which holds state in memory
and would need a custom SQLite `BasePersistence` anyway — so we build the persistence
layer regardless. And PTB is asyncio, so adopting it means rewriting `/scan`, `/stays`,
`/auto`, `/menu` and `/cancel` as async handlers: rewriting the verified travel surface
to serve the coach, which is precisely what the merge must not do.

**021 — 2026-07-29 — Six-step update routing precedence.**
Allowlist → callback (answer first, then route by prefix) → command (pre-empts and
suspends a conversation) → active conversation → bare input as weight → hint. Never
silence.

**022 — 2026-07-29 — 30-minute conversation expiry, with a signpost rather than a fallthrough.**
Without expiry, a Saturday weigh-in reply would be swallowed by an onboarding question
abandoned on Tuesday. With a bare fallthrough, someone returning after 45 minutes to
finish a sentence gets told their answer is not a valid weight. The expired branch names
the truth: "Onboarding is paused at question 6. Send /onboarding to resume, or a number on
its own to log a weight."

**023 — 2026-07-29 — `/stop` added; `/cancel` keeps its exact meaning, owner-only.**
`/cancel` sweeps running jobs and is dangerous once coach jobs exist. Overloading it with
"leave this wizard" would make a kill ambiguous.

**024 — 2026-07-29 — `last_update_id` in a JSON file under `.browser\`, not in SQLite.**
Corrects an earlier proposal. Putting it in `coach.db` would mean the listener cannot poll
at all if the coach database is missing, locked or corrupt — a new single point of failure
introduced into the working path by a coach requirement. Written temp + `os.replace`
(atomic on NTFS); missing or unparseable is treated as "no offset" and falls back to
dropping the backlog, so the offset store can never stop the poll loop either.

**025 — 2026-07-29 — The listener must survive a broken `coach.db`, and it is tested.**
Rename `coach.db`, restart the listener, confirm `/scan`, `/stays`, `/auto`, `/cancel` and
`/status` all work while coach commands fail politely. Database errors in the conversation
path are caught, reported as a sentence, and never escape into the poll loop.

**026 — 2026-07-29 — Per-update exception isolation; offset advanced before processing.**
With `RestartCount 999`, an update that crashes the process is redelivered on restart and
crashes it again — an invisible crash loop where interactivity is dead but travel alerts
keep arriving on schedule, so nothing looks wrong. Confirming first costs one lost message
instead of the listener.

**027 — 2026-07-29 — Startup drain: messages older than 10 minutes discarded; callback
queries in the backlog discarded wholesale.**
Telegram queues for 24 hours; without a threshold, a crash during a Windows update replays
everything at once. Stale commands are worse than lost ones. Callback queries are aged
differently because they carry no timestamp of their own — `callback_query.message.date`
is when the *bot* sent the message, so ageing by it would discard a live tap on an old
message and fail the legacy-button regression test. `answerCallbackQuery` on a pre-crash
query id tolerates its own failure.

**028 — 2026-07-29 — The 10-minute staleness threshold applies at processing time, not only at startup.**
Sleep suspends the listener without restarting it — the `Runs` log shows `up 20h 58m`
spanning a sleep — so the startup drain never runs for commands typed during a sleep.
Normal latency is under a second, so this never fires in ordinary operation.

**029 — 2026-07-29 — Non-text updates get a hint; edited messages are acknowledged once.**
`if not text: continue` silently violates routing rule 6 for voice notes, photos,
stickers and forwards. Ignoring edits is a fine choice; ignoring them silently is not.

**030 — 2026-07-29 — Per-role `setMyCommands` scopes.**
Architecture retained even though both users are now owners (see 049): silence from a
visible menu item reads as a broken bot, and a denied command says "That's owner-only"
with a pointer to `/stop`.

**031 — 2026-07-29 — Conversation state lives in storage, never in listener memory;
conversation handling lives in its own module the listener delegates to.**
`RestartCount 999` guarantees a restart mid-onboarding eventually. The listener keeps its
shape: receive, authorise, route, launch, cancel.

## Sheets

**032 — 2026-07-29 — SQLite is the source of truth. No coach code path ever reads from a Sheet.**
The moment a number can come back from a spreadsheet, a hand-edit becomes an input and
"numbers are code" is dead. Recovery from the mirror is a deliberate manual act.

**033 — 2026-07-29 — A new coach Sheet, separate from the travel Sheet.**
Drive sharing is per-file. The travel Sheet holds flight monitoring and the ops log;
sharing one Sheet would share all of it.

**034 — 2026-07-29 — Coach ops rows go to the existing `Runs` tab, job-level only.**
One place to answer "did everything fire last night?", and `lib/sheets.py` is unchanged
for that path. `coach_meals | ok | week 31 generated`, never
`coach_weight | ok | wife 68.4`. No names, no numbers about people.

**035 — 2026-07-29 — Per-user target Sheet id in config from day one; consent is a
revocable state, not a moment.**
Defaults both users to the same file. If one declines, her mirror points at a file she
owns and the change is a config value rather than a refactor. Per-user tabs make
revocation atomic: stop future writes, delete that tab, log it.

**036 — 2026-07-29 — The sensitive tier is never mirrored.**
Postpartum symptoms, pain flags, breastfeeding status, medical clearance. A `/pain` entry
reporting leakage must not appear in a spreadsheet, and it has no recovery value that
justifies the exposure.

**037 — 2026-07-29 — Weights and waist mirror on every successful write; the user is
confirmed from the SQLite write.**
A year of measurements cannot be recovered from anything else. Notify before persisting
so a Sheets outage cannot swallow a successful log.

**038 — 2026-07-29 — Recovery precedence: encrypted snapshot primary, Sheet mirror insurance.**
Stated explicitly, or someone builds a Sheets import believing it is the main path and
decision 032 quietly dies.

**039 — 2026-07-29 — Backups reach the owner's Drive, and this is disclosed rather than denied.**
The mirror rule protects against a spreadsheet; it does not protect against the backup.
Encryption plus disclosure at onboarding, because local-only backups reintroduce the
disk-failure risk to the one irreplaceable dataset.

**040 — 2026-07-29 — `lib/sheets.py` changes, scheduled for Phase 0.**
The replay queue stores `{"tab", "rows"}` with no spreadsheet id, so with two spreadsheets
a queued coach weight would replay into the travel spreadsheet, silently, into a
name-matched tab. Three additive changes: spreadsheet id in the queue entry (missing key
treated as the travel spreadsheet, since that is the only one that existed when such
entries were written), an explicit optional spreadsheet target on `append_rows` rather
than callers mutating a copy of cfg, and coach entries in `HEADERS` — reconciling the
unused placeholder `Training` and `Meals` entries rather than leaving two meanings for one
name. A replay targeting an unreachable spreadsheet re-queues instead of dropping.

**041 — 2026-07-29 — `lib/telegram.py` multi-chat targeting, scheduled for Phase 0.**
`_creds()` reads a single `TELEGRAM_CHAT_ID` and every send goes there. Additive: an
optional per-message target defaulting to the env chat. Useful side effect: travel alerts
read the env chat id directly, so travel privacy holds by default rather than by rule.

## Schedule and ops

**042 — 2026-07-29 — All coach tasks `LogonType=S4U`, battery-safe, `IgnoreNew`.**
Diagnosed live: `FamilyAssistant-Travel` missed its 08:00 run on 26 July with
`NumberOfMissedRuns=1` while the machine had been continuously up for 18h — both existing
tasks are `Interactive` and nobody was signed in until 11:16 after an overnight update
reboot. A competing explanation exists (`DisallowStartIfOnBatteries=True` on that task),
and the evidence cannot separate them — but S4U plus battery-safe closes both paths
without needing to know which one opened.

**043 — 2026-07-29 — `WakeToRun` is not relied on.**
`RTCWAKE` is `0x2`, "important wake timers only", and Task Scheduler wake requests are not
classified as important. Setting it would have looked like protection and done nothing.
The guarantee is `StartWhenAvailable` catch-up plus the missing-`Runs`-row alert.

**044 — 2026-07-29 — Nightly at 03:15 with an at-boot trigger and catch-up; a skip guard
makes both triggers idempotent.**
Idle sleep is off on AC (`STANDBYIDLE=0`) and both recorded sleep events resolved within
7 seconds, so this machine effectively does not sleep. The hour was never the problem;
the logon type was.

**045 — 2026-07-29 — Evening check at 21:00, not the specced 20:30.**
20:30 is a 19-month-old's bedtime. An unanswered check-in is recorded as a bad day, and
adherence feeds a plateau rule that requires ≥80%. Bedtime chaos would read as poor
discipline in data that drives calorie decisions.

**046 — 2026-07-29 — Sunday split: 16:00 generate and validate, 18:00 send.**
Generation is the only fragile weekly step. Combined, a model failure or a >5% macro
mismatch is discovered at delivery and the fallback silently serves last week's plan.
Split, it surfaces to the owner with two hours of slack; if unresolved, last week's plan
is sent **labelled as last week's**.

**047 — 2026-07-29 — Quiet hours 22:00–07:00 enforced in code via per-push validity windows.**
The risk is the retry, not the trigger time: a failed 20:30 job retrying at 23:40 is a
push into quiet hours, and one slipping past midnight writes to the wrong `date_local`.
Outside its window a push is dropped, logged, and surfaced in the next brief.

**048 — 2026-07-29 — Listener startup staleness audit.**
Last snapshot, last restore drill, last travel scan, per-task missed-run counts. A missing
`Runs` row is only useful if something reads it, and logon is the moment the owner is
present. Had this existed, 26 July's missed scan would have been reported at 11:16 instead
of found in a diagnostic on Sunday afternoon.

**049 — 2026-07-29 — A cross-process lock file wraps every `claude -p` invocation.**
Both subsystems now draw on one Max subscription from processes that do not share the
listener's in-memory lock. A throttle would surface as a JSON parse failure and be
misdiagnosed as a prompt bug.

**050 — 2026-07-29 — `/cancel` safety is both transactional writes and named-job scoping.**
Corrects a proposal to pick one. They solve different problems: transactions protect the
database (and cover power cuts), scoping protects the outcome. A cleanly-rolled-back
Sunday generation still leaves no plan for the week, silently — so the 07:30 brief fails
loudly when no plan exists.

## Users and privacy

**051 — 2026-07-29 — Both adults hold the `owner` role.**
Consciously reverses the travel-privacy default from 034/041. Scheduled travel digests
still go only to the env chat id — holding the role means she can run `/scan` herself, not
that she is subscribed to the digest. Known limitation, accepted: travel command responses
are English-only strings inside frozen code.

**052 — 2026-07-29 — Own-data-only visibility inside the bot.**
Role governs the machine, not each other's bodies. Each adult sees their own measurements,
logs and interview answers; joint household objects (meal plan, shopping list, freezer,
schedule) are visible to both. Honest answers are the fuel for this system, and "how is
your sleep, honestly" gets answered differently when the answer is one command away from
anyone else.

**053 — 2026-07-29 — English only. RU removed from the design.**
No `lang` logic, no `*_ru` columns, no bilingual seeding or testing. The message template
layer is retained as clean code, not as a dormant translation plan.

## Training and meals

**054 — 2026-07-29 — Equipment is enforced structurally: an `exercises` table with a
CHECK-constrained `equipment` column.**
An LLM asked for a home workout drifts to dumbbells and bands because its training data is
full of them — the same failure mode as inventing nutrition values, so the same fix. No
purchase suggestions ever, not even framed as optional.

**055 — 2026-07-29 — The generator selects `exercise_id` values from a supplied candidate
list, never names.**
Names invite fuzzy matching and fuzzy matching invites the drift being guarded against. An
id outside the list is rejected and re-asked once, then a deterministic session is served.
If a session cannot be built from the table, that is a table problem for the owner to fix.

**056 — 2026-07-29 — Yoga, mobility, breathwork and wind-down are first-class session
types with their own progression.**
Not rest-day filler. With a toddler in the house the stress and sleep side matters as much
as the training side, and they are mat-only by nature.

**057 — 2026-07-29 — Recomposition: 15% deficit, 2.0 g/kg protein.**
Conservative end of the band because aggressive deficits cost lean mass. Consequence
recorded explicitly in the spec: this system will rarely cut calories, and training
progression and adherence become the primary levers.

**058 — 2026-07-29 — Plateau v2 replaces the v1 rule.**
28-day window (weekly weigh-ins make 21 days three readings), ≥4 readings spanning ≥21
days, waist suppressor at −1.0 cm, progression suppressor, mandatory
`RecompositionProgress` message, and a `HardPlateau` override at 56 days. The waist
threshold survives ±1–2 cm measurement error because it is asymmetric — waist only ever
suppresses a cut, never triggers one. The 56-day override exists because progression
climbs on motor learning for months early on, and would otherwise suppress a genuine stall
indefinitely.

**059 — 2026-07-29 — `RecompositionProgress` sends an explicit message rather than staying silent.**
The absence of a plateau alarm communicates nothing. Only a positive statement counters
what a flat scale appears to say, and a flat scale misread as failure is the stated reason
this project would be abandoned.

**060 — 2026-07-29 — Waist tracking is opt-in per user, with a fixed measurement protocol.**
Body-measurement tracking is not neutral for everyone, and 19 months postpartum is not a
neutral moment. Declining falls back to weight-only — degraded, not broken. Protocol is
navel level (not "narrowest point", which requires a judgement call that moves between
sessions), Saturday morning, before eating, end of a normal exhale, tape snug.

**061 — 2026-07-29 — The full interview is collected upfront in Phase 1.**
Reverses a recommendation to tier it by module. It matches the "trainer's first
consultation" framing — a real trainer does one comprehensive intake, not three partial
ones. Mitigations: the catalogue is authored and reviewed on paper before Phase 1 builds
it, so consuming data shapes are designed at the same time; the interview is sectioned,
resumable, and states plainly that meals arrive in a few weeks. Recipe capture stays in
Phase 3a — the interview collects dish names only, or week one balloons into 15 guided
recipe conversations.

**062 — 2026-07-29 — Freezer portions are deducted by default via the evening check;
inventory goes stale after 3 weeks.**
Freezing happens at a moment of high engagement (Sunday, one button); eating happens on a
Tuesday with a toddler. Tying deduction to a tap that already exists makes the common path
free. Trust decay means a drifted inventory degrades to a slightly worse plan rather than
to a missing dinner, and staleness becomes a representable state.

**063 — 2026-07-29 — Fixed constraint relaxation order; hard constraints never bend.**
Corrects an earlier proposal that had effort ceilings bendable and one-family-meal below
them — both contradicted the stated requirements. Never relaxed: floors, one family meal,
effort ceilings. Relaxed in order: novelty → variety → freezer targets → portion rounding
±5%. Every relaxation is named in the plan message. Still unsolvable means a loud failure
to the owner with resolution buttons.

**064 — 2026-07-29 — Effort ceilings are validated against the day's cook; `/swap` flips it.**
The wife is the default cook; Davit's days are the exception. A single household ceiling
would apply the lower limit every day and throw away real available cooking time, making
relaxations fire far more often than necessary.

**065 — 2026-07-29 — `/cooking` handles cooking practice as a planned positive deviation.**
Davit holds a Scoolinary membership and will cook course dishes on notice. Same shape as
`/event`: displaced meal handled explicitly, calorie ballpark buttons, `rebalance()`
absorbs it. Logged as cooking practice, **not** as a deviation — practising cooking is
pro-plan behaviour and must never count against adherence. Successful dishes get a one-tap
offer into the rotation.

**066 — 2026-07-29 — Not breastfeeding; the gate is dormant but retained in code.**
The son eats solids. Her floor is 1,300 kcal and the clearance gate never fires. The
`breastfeeding` and `clearance_confirmed` columns and the calculator branch remain — one
boolean and one `if`, already tested — because dead code in a safety path is cheaper than
absent code under time pressure. Her answer comes from her own private onboarding, not
pre-set from the other account.

**067 — 2026-07-29 — The postpartum training gate remains fully in force.**
Postpartum is not the same as breastfeeding. At 19 months, pelvic-floor and abdominal-wall
considerations do not expire. The gate is owned by Training and is unaffected by the
calorie decisions above.

## Rollout

**068 — 2026-07-29 — Go live after Phase 2; meals is built on a running system.**
The project's own build-order rule at project scale. Two weeks of real use answers what
design cannot: whether 21:00 is right, whether the brief is short enough to read, whether
the evening buttons get tapped, and — most importantly for Phase 3b — whether freezer
deduction can be trusted. Accepted cost, following from 061: the wife answers meal
questions in week one and sees nothing come of them for several weeks; the interview says
so plainly at that section break.

**069 — 2026-07-29 — Phases renumbered: 0, 1, 2, 3a, 3b, 4, 5.**
Phase 3 splits because capturing the existing rotation is roughly 15 guided conversations
with ingredients, quantities and code-computed macros — not a side effect of the meal
interview, and enough on its own to run a phase three sessions long.

**070 — 2026-07-29 — `selfcheck.py` is extended to cover coach modules, config keys and
scheduled tasks.**
Otherwise the green check stops meaning what it means today.
