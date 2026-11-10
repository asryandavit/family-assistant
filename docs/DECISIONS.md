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

## Manual family plan

**071 — 2026-10-18 — A manual-first family plan runs now, ahead of the coach build.**
Meals and training are pulled forward as hand-followed Markdown in `plan/`, without
waiting for Phases 0–2. Owner's choice: value now, and two to four weeks of real use
answer what design cannot (same reasoning as 068, applied earlier). The coach phases in
`COACH_SPEC.md` §15 are not cancelled; they become stages B and C in `plan/README.md`.

**072 — 2026-10-18 — Plan content lives in Markdown in Git, not a database, for now.**
Owner wants it flexible and editable. Git keeps every hand-edit as a reviewable diff, which
answers the concern behind 032 (a silent hand-edit becoming an input) better than an
editable Sheet would. SQLite (005) remains the design for *measurements* once the bot
logs them; plan content may stay in Markdown even then.

**073 — 2026-10-18 — Portions, not calorie numbers, in the manual stage.**
Plate rule for adults, ad-libitum for the son. The calculators in §6 stay the design for
the automated stage if numbers are ever wanted. Owner's choice.

**074 — 2026-10-18 — Grocery integration promoted from backlog into scope.**
Parma (English UI, per-kg prices) primary, Yerevan City (lactose-free collection)
secondary. Lists and fresh prices are prepared; ordering and checkout stay manual — no
credentials, no automated cart.

**075 — 2026-10-18 — Exercise and dish libraries carry stable ids from day one.**
`plan/training/exercises.md` and `plan/meals/dishes.md` are the only places an exercise or
dish may be defined; every plan references ids. Same allow-list principle as 054/055, so
the manual libraries become the seed of the `exercises` and recipe tables later.

**076 — 2026-10-18 — New owner health data shapes meals and training timing.**
Davit: mild gastritis, high LDL, lactose from fresh milk only, citrus limited. Hence: no
intermittent fasting, light dinner by 19:00, hard sessions 2–3 h after main meals, olive
oil/fibre/fish emphasis, lactose-free milk with fermented dairy kept. Karine's postpartum
gate (067) carries into the manual plan as a symptom self-check. The son gets a WHO-based
play plan and remains untracked (§1). Evidence summary in `plan/sources.md`.

## Grocery prices

**077 — 2026-10-18 — Grocery price lookup over plain HTTP; each shop independent.**
Discovery (fixtures in `tests/fixtures/grocery/`): Parma renders search results
server-side (`/en/product/search?text=…&page=N`, 60 per page); Yerevan City has a public
JSON search API (`apishopv2…/api/Product/Search`) that answers without the browser's
anonymous token, with English names. So no Playwright: faster and far less fragile than
the travel scrapers. Parsing is stdlib regex like `parse_stays` — no BeautifulSoup
dependency. Every item is normalised to one shape with a **unit price per kg/l**, because
Parma shows weight items at the price of the *minimum* amount (0.5 kg) and comparing
that against a 1 kg pack would be off by 2×. Both shops rank loosely ("milk" returns
face wash), so results are filtered locally: whole-word, plural-tolerant matching, with
names that lead with the product type ranked first. Prices are always looked up fresh,
never stored as truth. A shop failure is reported in the message, never hidden.

**078 — 2026-10-18 — Armenian queries via an editable word list; strict cross-shop comparison.**
Both shops' search engines already understand Armenian script and transliteration
(tested: ոսպ, մածուն, կաթնաշոռ, matsun, katnashor, tvorog, lavash, hercules), but the
local match filter only read English, so it discarded e.g. Parma's "Matzoon" for
"matsun". `plan/meals/grocery-words.md` (Markdown, editable — decision 072) maps what the
family types to the search term and the product-name words each shop uses; Yerevan City's
Armenian product names are matched directly; for an Armenian word not in the list,
Parma's English results are left to the shop's own search. Comparison is two-part and
deterministic: cheapest per kg/l at each shop among the best matches (same unit only),
and "same product at both shops", paired only when brand, package size, fat % and the
remaining descriptive words all agree — strict on purpose, because a false pairing
("Curd Marianna Bifido" vs "Curd Marianna") would make the comparison misleading.

## Progress records

**079 — 2026-10-18 — Progress numbers live in a private Google Sheet per adult, not in Git.**
Weight, waist and blood-test results are health records; the repo holds the *plan*, not
the measurements. Each adult owns their own Sheet (Karine copies a blank template into
Karine's own Drive), which keeps the "own data, self only" rule of §2 and the per-file
sharing of 033/035 without any code. No postpartum symptom column, ever (036/067). When
the bot gains `/weight`-style logging, measurements move to local storage on the PC and
each Sheet's history is imported **once**, explicitly — a one-time migration, not the
ongoing read-back that 032 rejects. A baseline lipid panel before the plan starts is
recommended so the effect of the food changes can be measured.

## Telegram UX

**080 — 2026-10-18 — One home screen, a two-key bottom keyboard, folded messages; docs/TELEGRAM_UX.md.**
The bot grew one feature at a time (travel, /flights, /price; daily plan and basket
next), leaving a travel-only menu and a dozen commands to remember. Replaced by: a Home
message edited in place with six sections (Today · Meals · Training · Shopping · Travel ·
System), a persistent bottom keyboard with only Home and Price check, long content
folded into expandable blockquotes, one message template, and a sound policy (alerts and
failures notify; routine messages are silent). This supersedes the six-button layout in
COACH_SPEC §11 (Training · Meals · Weight · Baby · Status · Settings), which predates
travel, shopping and the plan — Weight and Baby will live inside sections when built.
Navigation uses a new `ui:` prefix; existing prefixes stay, so buttons in old messages
keep working. All features used are free Bot API features, verified on this bot first.

**081 — 2026-10-18 — No "primary" shop: both are compared, cheapest wins.**
Corrects the wording of 074, which called Parma primary on day one — a readability
choice (English site, per-kg prices) made before any prices were compared. The
comparison built in 078 showed Yerevan City cheaper on every identical product checked
(5–18%) and usually cheapest per kg. The code never had a preference (rank and compare
pick the cheapest); only the docs and plan wording change. Yerevan City is listed first as
the usual winner; the basket picks per item from both.

**082 — 2026-10-19 — Karine uses the bot: two allowed chats, replies to the asker.**
The Phase 0 change scheduled in CLAUDE.md §1, done now because Karine wanted access:
`lib/telegram.py` gained an optional per-message chat target (default unchanged),
`allowed_chats()` (owner + `TELEGRAM_CHAT_ID_2`) and `send_family()`. The listener answers
both chats; replies, Home navigation and the results of /price, /flights and /stays go to
the chat that asked (the job gets `TELEGRAM_REPLY_CHAT_ID`). Travel scans, digests and
deal alerts stay Davit's (COACH_SPEC §2; Davit confirmed), and system messages always go
to the owner. Family content (daily plan, week plan, shopping list) goes to both through
`send_family()`. Karine's chat id is a Windows user environment variable like the first —
never in Git. Rules: docs/TELEGRAM_UX.md §5a.

**083 — 2026-10-19 — Yerevan City products get an extra "📱 app" link for iPhone.**
Both adults use iPhones. Yerevan City's apple-app-site-association lets the iPhone app
open only `/shop/home` and `/shop/product-detail/*` (singular), while the website's real
product pages are `/shop/product-details/*` (plural; the singular path redirects to the
shop home on the web — verified). So each Yerevan City product keeps its normal web link
and gains a small "📱 app" link with the singular path; tapped on an iPhone with the app
installed (and Telegram set to open links in Safari) it opens the app. Parma publishes no
app association, so no app link. /price now shrinks its folded part to stay one message.

**084 — 2026-10-19 — Basket: the shopping list priced at both shops, delivered as a shared Google Sheet checklist.**
The family wanted the weekly list as something to tick off on two iPhones. Google Keep has
no API for personal Gmail accounts, so the checklist is a Google Sheet ("Shopping list",
Drive → Family Coach) with real checkboxes (data validation BOOLEAN), shared as Editor with
both adults and with the service account that already writes the travel Sheet; it is
written by a new additive module, `lib/sheets_checklist.py` (whole-tab rewrite: values,
checkboxes, links), leaving `lib/sheets.py` unchanged. `jobs/grocery_basket.py` reads
`plan/meals/basket.md` — an explicit mapping of every `shopping.md` row to a shop search,
match words, a number + unit (kg / l / pcs / pack) and exclusion words — instead of
guess-parsing free-text amounts ("3–4 kg", "as needed"); "as needed" and "per recipe" rows
are listed as skipped. Each distinct search runs once at both shops, sequentially with a
1.5 s pause. Arithmetic is deterministic and tested (`lib/basket.py`): items sold by weight
cost kg × price with the shop's minimum order respected; packages are counted up to whole
packages (a pack up to 10% under the amount counts); pieces come from "10pcs" in the name;
the cheapest line cost per shop wins and the cheaper shop wins per item (Yerevan City on a
tie, decision 081). A product only counts when the item's type is among the first two words
of its name — whole-word matching alone priced shampoo as olive oil and cat food as trout on
the captured data. No match → "no match", out of the totals, run marked partial; a price is
never guessed. Output: the Sheet (tabs "This week" / "Monthly staples", grouped by shop,
Yerevan City first, 📱 app links, totals, budget check, a not-priced block) and one silent
Telegram message to both chats (`send_family`, docs/TELEGRAM_UX.md §5a) with totals, the
month at these prices (weekly × 52/12 + staples) against the 80–100k budget, one-shop-only
vs cheapest-of-each over items found at both shops, and a 📋 checklist button. The message
is sent before the Sheet is written, so a Sheets outage can't swallow it; a failed Sheet
write tells the owner. Run from 🛒 Shopping → 🧺 Basket or `/basket [monthly|all]`; the
bot never logs in to a shop, never touches a cart, never orders. On the first capture the
month came to ≈112k AMD — over budget, mostly staples (lactose-free milk, olive oil, fish).

**085 — 2026-10-21 — The plan lives in the bot: Today / Meals / Training templated from plan/, a 07:30 message and a Sunday menu.**
Roadmap stage B starts. The Home sections Today, Meals and Training stop being links to the
Drive copy and show the plan itself, read from the Markdown files by their stable ids
(`coach/plan_view.py`) and laid out in code (`coach/plan_text.py`) — no model call, no
invented dish, exercise or number, portions not calories (CLAUDE.md §2, decisions 054/055/
073). The plan week is computed from `plan_start_local` in `config_coach.json` — Monday
19 Oct 2026, the owner's answer — and the Yerevan date; a missing `week-NN.md` falls back to
the latest file and says so; an unknown id is shown with a note instead of failing. The
Drive docs stay as secondary link buttons, and a plan that can't be read falls back to them.
Two silent pushes to both chats (`send_family`, decision 082) come from a new job,
`jobs/coach_brief.py`: 07:30 daily (today's meals, prep, both sessions or "no session
today · walk", one habit nudge from `habits.md`; cues and videos folded) and Sunday 18:00
(next week's menu + a pointer to 🧺 Basket). Pushes carry a validity window in code
(morning until 10:00, week until 22:00, COACH_SPEC §12): late ones are dropped and logged.
Tasks `FamilyAssistant-Coach-Morning` / `-Week` use the travel task's logon setup
(`scheduler/register-coach.ps1`). `/today` is a typed shortcut. **Link rule (owner):** a
URL appears only if a job verified it (exercise videos from `jobs/exercise_videos.py`), it
is a hand-checked `ref` in `dishes.md` on an allowlisted free recipe site (BBC Good Food,
Armenian Institute, The Armenian Kitchen — four added, each opened and confirmed), or it is
built from a fixed search template; tested across every day of the plan. Videos never
change the exercise; an exercise's first day in a person's 12-week plan is marked *(new)*
with "watch the video before your first set; start with the lightest option." Plan text
avoids patient/condition/disease/illness/diagnosis/treatment, and Training plus the
morning message carry one folded safety line. No check-in, no kcal or macros, no adherence
prompts (the owner's light-tracking choice). Health briefs are not read; the §6.2
muscle-symptom question plugs into `plan_text.today_extras()` later. Messages stay one
message: on the heaviest days cues shrink from 3 to 2 (then 1) rather than splitting.
Rules: docs/TELEGRAM_UX.md §5c.

## Market watch

**086 — 2026-10-29 — Market watch: a shared nightly watch list priced to Yerevan; P0 discovery done.**
The owner wants items from foreign and Armenian marketplaces watched daily, with the cost
to bring each to Yerevan per forwarder and mode. Interviewed decisions: one shared list
(Davit and Karine), Telegram dialog plus an editable Sheet, full report every night at
~01:30, alerts on a ≥10% drop and back in stock, exact-or-similar per item (similar = code
rules + a Claude shortlist ranking, phase 2), weight and size asked once per item (Chinese
seller message for China items), up to ~20 items, original currency and AMD both shown.
Forwarders are data (Onex, Globbing, EasyTrans, BuyForYou — the owner's accounts), their
tariffs refreshed weekly, not daily. Delivery times keep each forwarder's own unit
(working / calendar days / months) and starting point (arrival vs dispatch). P0 found a
machine-readable tariff source for all four forwarders and the CBA rates; customs default
is the rule the forwarders apply (€200 duty-free, 15% above); Amazon UK/DE/IT and vega.am
read in a browser profile, Amazon US / Wildberries / Ozon do not (bot checks — the bot never
passes one itself), so P1 covers exact links on the readable stores. The bot only reads:
no login with the owner's password, no cart, no orders. Brief: docs/briefs/MARKET_WATCH.md.

**087 — 2026-10-29 — Market watch P1: exact links priced to Yerevan nightly, maths proven against each forwarder's own calculator, every store degrades instead of failing.**
Built `market/` (pure Python, no `lib/` change for the maths) and two jobs. **Numbers are code,
tested against the forwarders themselves**: Onex 90 calculator answers (P0), and three new
oracles captured today — Globbing's and BuyForYou's own calculator JavaScript run unchanged by
`tests/fixtures/market/oracle_calculators.js` (600 + 140 answers) and EasyTrans's
calculate-price API (16 answers); every answer is checked. Findings that changed the plan:
Globbing's `divider` is a rounding tolerance (a remainder under 3 g / 7 g rounds down to the
100 g step); Globbing charges by volume on USA/UK/UAE/Russia/Korea **air** too
(`compare_gross_and_dimensions`); Globbing's customs is the *larger* of 15% over €200 and €2/kg
over 30 kg, none from Russia; BuyForYou's calculator uses **16.2%**, not 15%, and has **no China
sea** (the brief's 1,100 AMD cell was wrong); EasyTrans has no weight step and ignores size.
Customs default stays the forwarders' rule per forwarder, EAEU 2026 a switch in
`market/customs.md`. Working days skip weekends and `market/holidays.md`; each route keeps its
own unit and start (EasyTrans from the truck's departure → "after dispatch").
**Tariffs** refresh weekly (`jobs/market_tariffs.py`, Sunday 01:00): a source that fails keeps
last week's routes with their date and is named in the report (first live read: 35 routes,
identical to the fixtures). **Stores**: Amazon US/UK/DE/IT and vega.am read in the bot's own
headed profile `.browser/market`, delivery set to the warehouses (19720, E17 4SX, 82152, 70122)
and local currencies; parsers written on real captures (price to pay, not the per-unit price;
delivery to the warehouse; "free on your first order" counts as **unknown**, never free;
dates; stock; weight/size). Wildberries ("checking browser") and Ozon ("no connection — turn off
VPN") showed the bot block pages again, so only their **detection** is built — no price parser
until a real product page is captured (the nightly run saves one if it ever opens). **Fallback
for every store**: one attempt per link per night, a block skips the store for the run, items
keep their last price marked ⚠️ with its date and raise no alert, one report line per blocked
store, one owner message after 3 blocked nights, `/watch price` for an owner's price, "no price
yet" otherwise — never a guessed number. **Nightly job** `jobs/market_watch.py` (01:30,
`scheduler/register-market.ps1`): one silent report to both chats, alerts with sound for a ≥10%
drop (fresh reads only) or back in stock; the report is sent before anything is saved. List in
`.browser/market_data/` (one writer per file) mirrored to the "Watch list" Sheet
(items/offers/history via `lib/sheets_checklist.write_tab`; phone edits merged, bad values
rejected whole); the Sheet id is empty until the owner creates and shares it. **Telegram**:
`/watch` + add dialog (`market/bot.py`), 🌍 Market on Home — `lib/ui.py` and `listener.py`
changed in their own additive commits with the full suite as the regression check (no
`docs/ARCHITECTURE.md` exists; docs/TELEGRAM_UX.md §5d carries the UI). Rules:
docs/briefs/MARKET_WATCH.md §10, docs/TELEGRAM_UX.md §5d.

## China search

**088 — 2026-11-09 — /china search: brief approved, P0 discovery — headless Chrome works for Pinduoduo and 1688, not for Taobao.**
The owner wants `/china <description>` (both chats, one shared Chrome session and queue) to search
Pinduoduo, Taobao/Tmall and 1688 in his own logged-in Chrome via the Claude in Chrome extension and
answer with results priced to Yerevan by the Market watch code (decisions 086–087). Brief:
docs/briefs/CHINA_SEARCH.md, approved 2026-11-09. Results will be Telegram Rich Messages
(`sendRichMessage`, Bot API 10.1–10.3) with a plain-HTML fallback; a test rendered correctly on the
owner's iPhone (table, details, slideshow, in-message buttons; button attribute is `data=`).
P0: `claude -p --chrome` runs headless on the Max subscription (`ANTHROPIC_API_KEY` unset) and must
select the Windows browser (a Mac is also connected). A full read (search, top 3 product pages with
variant picker, reviews) took ~4 min on Pinduoduo and ~4.5 min on 1688 with no prompt; Taobao asks
for permission on every action ("site-level permissions are disabled") and timed out unattended, and
its product page showed a `访问异常` notice after a few quick reads — never bypassed. Findings that
shape P1: the listing price is the cheapest variant, not the described one (¥109 shown, ¥189 for
the 100W); PDD web has only the group price; Tmall look-alike flagships (`品胜官方旗舰店` vs
`品胜快充旗舰店`); Taobao's brand chip is the compatible device; 1688 is served in English/USD
without factory marks on cards and quotes delivery to Yerevan; 1688 size tables mix mm and cm;
extension tool output is capped at ~1,000 characters and blocks URLs with query strings (links are
rebuilt in code from ids). A two-site run is ~$2.65 list-price equivalent of Max quota, so P1 uses
fixed extraction scripts and a cheaper browsing model. Taobao path ((a) bot profile, (b) link only,
(c) attended) is the owner's call. Fixtures: tests/fixtures/china/.

## Direction

**089 — 2026-11-09 — Direction: build everything in our own environment first, household-ready from now on; vision, roadmap and commercial research recorded.**
The owner set the big goal: a family life assistant (meals, training, shopping and prices, travel,
celebrations) that could one day become a product with invited users, roles and permissions, a
better interface (Mini App), a separate backend and workers — fully or partly, direction open.
The rule for now: every feature is built and polished in our own environment first and changed
step by step; even if it never becomes commercial it should be close to perfect. From now on new
features are **household-ready** (user ids and roles, not hard-coded chats; settings per
household; a permission check per module; private items possible). Recorded: docs/VISION.md
(product idea, users/roles, architecture direction, Celebrations idea, commercial findings),
docs/ROADMAP.md (China P1/P2 → users and roles → Celebrations → Mini App step 0 and screens), and
docs/research/2026-11-09-commercial.md (owner's research). Key findings: a Claude Pro/Max
subscription may not serve a product (a product uses the Anthropic API under commercial terms);
Telegram digital subscriptions must use Stars; Amazon forbids price alerts for Associates; health
and diet data are special-category. Mini App: one screen layer only — jobs stay on the PC, data
only through an authenticated tunnel, store pages are linked ("Open in app"), not embedded.
Celebrations: Google Calendar read-only, reminders 2 months / 1 month / 2 weeks / 1 week, person
notes, priced gift ideas checked for arrival in time, tracked with a deadline, private per
creator — built after users and roles. To verify now: the 2026 EAEU customs rule and Anthropic's
"API credits for subscribers".

**090 — 2026-11-09 — /china P1: text search built; Pinduoduo and 1688 automatic, Taobao a link; numbers in code, model answers validated whole.**
`/china <description>` (both chats, one queue, the same features — "household-ready" (089) where
cheap: the asking chat is carried through the job, `/china last` and every result button are per
chat and refuse another chat's results, settings live in `config_china.json`). The listener only
queues; `jobs/china_search.py` (one worker, lock file, `china/queue.py`) runs: a plan call (Chinese
query, category, 1–2 button questions when vague), one `claude -p --chrome` run per site on the
Max subscription (allow-listed read tools, typing/upload tools denied, `ANTHROPIC_API_KEY`
removed; Sonnet for browsing), validation of the whole answer (`china/validate.py`: allow-listed
ids, enums, no URLs, data fields strict, long English prose trimmed rather than rejected) with one
`--resume` repair re-ask, then everything numeric in code: `china/parse.py` (¥/$ strings, 万
counts, weights, mm-labelled-cm sizes, seller class from shop name and marks — only 官方旗舰店 is
official), `china/pricing.py` (market.pricing.quote per forwarder × mode from `config_china.json`
routes, 1 kg assumed and said in UPPERCASE when no weight, unknown China delivery never free, promo
prices — 新人价, 首件, 起, ranges — shown but never the 🏆 pick, the pick prefers an official /
authorised seller within 25% of the cheapest, parcel customs for several items). The answer is one
Rich Message (`lib/telegram.send_rich`, own commit) with a plain-HTML fallback; buttons
🔁 Only <site>, 💬 Reviews N, 👁 Watch N (adds the item to Market watch with today's price as the
owner's price). Live runs 2026-11-09 changed the plan twice: **Pinduoduo product pages now hide
prices** ("前往APP查看价格") — results come from the search listing, labelled "may be a cheaper
variant"; and **Taobao cannot be read**: the extension asks on every action, and the bot's own
browser fails Taobao's phone/slider check after QR login even when the owner does it by hand — not
bypassed, so Taobao is a search link in every answer (`taobao_mode: link`; the reader in
`china/taobao.py` stays for a later `profile` mode). Cost per site run measured at ~$0.4–0.7
list-price equivalent of Max quota (P0: ~$1.3). Docs: docs/briefs/CHINA_SEARCH.md §9,
docs/TELEGRAM_UX.md §3/§5e, docs/ROADMAP.md.


**091 — 2026-11-09 — /china: safer 🏆 pick for electronics, beauty and kids; suspiciously cheap listings never picked; 1688 product pages read with get_page_text.**
The first phone demo (`/china GaN charger 65W EU plug`) picked a no-name 1688 "65W" charger at
¥23.85 (1,888 AMD delivered) over brand-authorised Ugreen on Pinduoduo (~6,800 AMD), because the
official/authorised preference only applied within 25% of the cheapest. The owner chose a safer
rule: in `pricing.SAFETY_CATEGORIES` (electronics, beauty, kids) an official or authorised listing,
when one exists, is always the pick whatever the price gap, and the reason says so. In every
category a listing whose item price is below `suspicious_ratio` (0.25, `config_china.json`) of the
search's median item price (promo prices left out of the median) is marked "⚠️ suspiciously cheap"
in the table, its details and the plain fallback, and is never picked. The same run showed the
Chrome extension refusing `javascript_tool` on `detail.1688.com` ("Permission denied for JavaScript
execution on this domain"), so only 2 of 5 offers were read, from screenshots; `get_page_text`
works on those pages (checked live: supplier, attributes, weight/size table, variant prices), so
the 1688 prompt now reads each product page with one `get_page_text` call and never from
screenshots. Not changed: the in-message buttons (owner: wait for the Mini App). Fixture:
tests/fixtures/china/answer_1688_live.json. Docs: docs/briefs/CHINA_SEARCH.md §9,
docs/TELEGRAM_UX.md §5e.

**092 — 2026-11-09 — /china ranks by trust first, price second; reviews read on Pinduoduo even when prices are hidden.**
Owner: "the price is not so important — find the best and trustworthy product; make sure reviews and
all important things are counted, especially on Pinduoduo." Results are now ordered by a trust
score computed in code (`china/trust.py`, unit-tested): seller class (official 40, authorised 35,
flagship 25, reseller/factory 10, unmarked 0), a fake-compensation or genuine-goods guarantee (+5),
store age (+1/yr, ≤ 5), a 3C/CE certificate for electronics and kids (+5), sales (3·log10, ≤ 15),
review count (2.5·log10, ≤ 10), positive rate with ≥ 20 reviews (+10 at 100%, 0 at 90%, down to
−20), each complaint kind found in the reviews (fake, broken, unsafe, wrong specs, not as described
−12; poor quality −6; shipping, packaging, other −2), specs contradicting the title (−15), and
suspiciously cheap (−100). Delivered price orders only results in the same 5-point band. The 🏆 pick
is the top of that order across sites (never a promo or suspiciously cheap price) and its reason
lists the parts; each result's details show "🛡 Trust N: part +n · …" and the table's third column
is the trust score. This supersedes decision 091's 25% / safety-category rule (`trusted_within_pct`
removed); the suspicious-price rule stays. The model only reports what the page shows: new contract
fields `rating_text` (as shown), `complaint_types` (allow-list, validate.COMPLAINTS, anything else
rejects the answer) and `spec_mismatch`; the prompts now ask for the best and most trustworthy
listings, never the cheapest, and Pinduoduo reads the reviews page (counts, tag chips, 差评 and
追加 follow-up reviews) for the top listings even when product pages hide prices. Also fixed: tests
with a fake runner wrote their replies into `.browser/china_data/raw` and rotated real replies out;
only real runs are kept now. Docs: docs/TELEGRAM_UX.md §5e, docs/briefs/CHINA_SEARCH.md.

**093 — 2026-11-10 — /china trust score adds a brand list with look-alikes, reviews of the right variant, and photo reviews.**
Owner: "as a professional add the most important ones". Three signals, computed in
`china/trust.py`, unit-tested. (1) Brands: `config_china.json` `brands` per category, owner-editable
— a trusted brand +10, a known look-alike −30 (seeded with brands well known in China and the
look-alikes seen or documented: "UE" imitating Ugreen, seen live 2026-11-09; 乐拼/Lepin copying
LEGO). The brand is read only from the 品牌 spec, a brand store's name (旗舰店 / 专卖店) or the start
of the title: no-name titles say 适用苹果 ("fits Apple"), and accessory shops carry brand names.
(2) Variant: the model reports which variant the reviews it read were about (`review_variant`,
allow-list matching | mixed | other | unknown); matching +3, other −5. (3) Photo reviews:
`photo_review_count_text` as shown (图/视频(166)), 2·log10, at most +6. Considered and left for
later: grouping the same product across sites into one comparison (already shown as "same
product", decision 090). Docs: docs/TELEGRAM_UX.md §5e (trust parts), docs/briefs/CHINA_SEARCH.md.

## Mini App

**094 — 2026-11-10 — Mini App step 0 built: own React app served from the PC through Tailscale Funnel, Telegram's signature checked on every request.**
As briefed (docs/briefs/MINI_APP.md, owner answers 2026-11-10). A separate process,
`python -m miniapp.server` (scheduled task `FamilyAssistant-MiniApp` at logon, restarted if it
dies; `scheduler/register-miniapp.ps1`), stdlib `ThreadingHTTPServer` on 127.0.0.1:8790, GET only
(anything else 405): static files from `miniapp/web/dist` (paths normalised; anything outside
dist, `..`, encoded `..`, backslashes, drive letters, NUL is a 404) plus `/api/me` (name, role,
tabs) and `/api/status` (Yerevan time, version). `listener.py` is untouched. Auth
(`miniapp/auth.py`, pure): `Authorization: tma <initData>`, Telegram's HMAC algorithm with the
bot token from the existing env var (never sent to the page), duplicate keys / missing hash /
bad JSON / older than 24 h / more than 5 min ahead all rejected; the hash is checked over every
field and, failing that, over every field except `signature` (which form Telegram signs is
settled by the local real-capture test; accepting both forges nothing). 401 for bad auth, 403
`{"error":"private"}` for a valid Telegram user who is not in `miniapp/people.py`, 429 after 60
requests a minute per user id (and for unauthenticated requests as one bucket). People by
Telegram user id + role, household-ready (089): Davit = owner from `TELEGRAM_CHAT_ID`, Karine =
adult from `TELEGRAM_CHAT_ID_2`, names and roles in `config_miniapp.json`; Users and roles later
replaces the source, not the interface. Headers: CSP (self + telegram.org for the script,
frame-ancestors web.telegram.org), nosniff, no-referrer, HSTS, `Cache-Control: no-store` on the
API, `Server: miniapp` without a Python version. Logs (`.browser/miniapp.log`): masked user id
(last 3 digits), path without query, status, duration — never initData, hashes or tokens.
Web (`miniapp/web/`): React 18.3.1 (Telegram UI 2.1.13 needs 18), Vite 7.3.8, TypeScript 5.9.3,
exact versions and lockfile committed, `dist/` and `node_modules/` gitignored, built with the
PC's Windows Node 24 (machine.json `node_dir`); `tsc --noEmit` + `vite build` clean. Five
"Coming soon" tabs, "Signed in as … · role", a status card refreshed every 30 s, Telegram's
theme followed live (`themeChanged`), Telegram's back button walks back through tabs, and two
clear states: "This app is private" (401/403 or opened outside Telegram) and "PC is not
reachable" (no answer, timeout or a gateway error) with Try again. Checked in a browser with a
test-signed initData: owner view, live switch to dark, tabs + back button, stranger → private,
server stopped → unreachable. A cold open while the PC is off shows Telegram's own error page,
not ours (brief §3 trade-off). `miniapp/setup_bot.py` sets / checks / removes the 🏠 Family chat
menu button per person (`setChatMenuButton`). `lib/telegram.py` gained `{"web_app": url}` inline
buttons in its own commit (54fd773; docs/REGRESSION.md does not exist, so the full suite was the
regression check). The public URL lives only in gitignored `machine.json`
(`miniapp_public_url`); `tmp/*` and `machine.json` are now gitignored too. `selfcheck.py` gains a
MINI APP section (server on localhost, public URL, menu button per chat). Tunnel: Tailscale was
running but HTTPS certificates and the `funnel` node attribute were off, so the one-time
admin-console step is the owner's (docs/SECRETS.md §5); `register-miniapp.ps1` only reports the
Funnel status. pytest and ruff were not installed on the PC; both installed (`pip --user`) for
this phase's definition of done. Docs: docs/SECRETS.md (#10–12, §5), docs/TELEGRAM_UX.md §6,
ARCHITECHTURE.MD (processes, tunnel), docs/ROADMAP.md, docs/VISION.md §4, the brief's status.

**095 — 2026-11-10 — /china P2 photo search: 1688 searched by the photo, Pinduoduo by the words read from it, Taobao a link; photos asked about, never searched unasked, and deleted after the answer.**
The owner asked for photo search next ("start china P2 photo search"), ahead of keeping the sites
logged in; the brief's phases are renumbered (P2 photo, P3 keep logged in). Discovery: only
**1688** has a web image search the bot can drive — its `Image Search` file input takes the
Chrome extension's `file_upload`, headless included (60 visually similar results; offer ids from
the cards' `data-renderkey`). **Pinduoduo**'s photo search is app-only (its web code shows only
"go to the app"); **Taobao** cannot be read unattended at all (decision 090). So a photo job asks
`claude -p` what the item is (the image as a base64 block on stdin, every tool off, the answer
validated whole: is it a product, what it is, 2–6 Chinese search words, brand only if readable,
category), searches 1688 by the photo itself (falling back to its words if the upload fails),
Pinduoduo by the words (said in the answer), and gives the Taobao link with those words plus "tap
the camera in the Taobao app". Everything after is the text search unchanged: pricing, trust
ranking, 🏆, buttons, `/china last`. Only `file_upload` was added to the browser allow-list, and
only for the 1688 photo run. Photo routing: the listener dropped every message without text, so
nothing else in the bot reads photos; a photo with a `/china` caption searches, any other photo
gets one question with `🇨🇳 Search China` / `✖ No` (Health records, when built, reads photos only
inside `/health` and goes first). Privacy: photos are downloaded to the gitignored
`.browser/china_data/photos/`, deleted when the answer is sent (`photo_keep_minutes` 0), swept
at worker start and on each new photo; the file id is never logged with a chat id; chat ids
masked. Household-ready (089): photo jobs carry the sender's Telegram user id and role
(`config_miniapp.json` people); a viewer may not start a search. Measured live: photo plan 13 s
(~$0.07 list-equivalent of Max quota), 1688 by photo 3.8 min (~$0.66). Docs:
docs/briefs/CHINA_SEARCH.md §6/§10, docs/TELEGRAM_UX.md §5e, docs/ROADMAP.md, ARCHITECHTURE.MD
(listener).

**096 — 2026-11-10 — Mini App: Home list instead of a bottom tab bar; initData hash covers `signature` (from the real capture).**
Owner, first look (Telegram Desktop): with five bottom tabs the outer icons sit in the phone's
rounded corners and are hard to tap; "find a better solution". The app now opens on a Home list
— Telegram's own Settings pattern: signed-in line, one full-width row per section (icon, name,
one-line description, chevron), then the PC status card. A row opens its screen; Telegram's back
button returns Home (an in-page Home row only for clients older than Bot API 6.1). New sections
(Celebrations) add rows without crowding. China's icon is 🏮: Windows has no flag emoji and
showed 🇨🇳 as "CN". Checked at phone width with a test-signed initData (rows, open, back).
Auth tightened: a real initData captured on this PC (`--capture-initdata`, tmp/, never
committed) has fields auth_date, hash, query_id, signature, user, and its hash matches only with
`signature` included. Decision 094's fallback (also accepting a hash that skips `signature`) is
removed; that form is now a rejection test, and the real-capture test passes (no skips).
Docs: docs/TELEGRAM_UX.md §6.

**097 — 2026-11-10 — Mini App step 0 done; step 1 built: China results screen, 📱 Open in app on every /china answer, first POST endpoint, Market watch write lock.**
Step 0 owner demo passed 2026-11-10 (owner and Karine as adult, dark mode, Home list, back
button, PC-not-reachable and recovery). Owner: "go next and implement all together" — step 1
in the same session, scoped in docs/briefs/MINI_APP.md §12 before building. **Screen:** 🏠 Family
→ China, or the new first button row **📱 Open in app** on every `/china` answer (rich and
plain; `?screen=china`), shows the asking person's latest saved result (`last_<chat>.json`,
24 h; in a private chat the chat id is the user id, so nobody sees another person's search):
sites' status, 🏆 pick, one card per result in the chat's numbering with price, delivered
total and route, warnings, and a Details fold (routes, weight, trust parts, specs, reviews read,
restrictions, the model's "why", the ask-the-seller text). **Numbers are code:**
`miniapp/china_view.py` builds display strings with the same `china/report.py` helpers the chat
uses (HTML stripped) and the pick with `china/pricing.best_pick`; the page does no arithmetic.
Results saved before the trust score (092) show no pick. **Actions:** `POST /api/china/action`
`{"action": "watch"|"reviews", "job", "n"}` calls `china.bot.callback` exactly as the chat's 👁 / 💬
buttons — Watch adds to Market watch, Reviews queues the Chrome job and the answer arrives in the
chat. First POST: JSON only (415 otherwise), ≤ 1 KB (413, connection closed so an unread body
can't corrupt the next request), exactly these keys, job `[0-9a-f]{8}`, n 1–99, same signature /
rate limit / 403 as the GETs, plus a per-module permission (`people.can(person, "china")`,
owner and adult). Routes are a table; a wrong method on a known path is 405. **Lock:** the Mini
App server is now a second writer of `items.json` / `owner_prices.json`; their
read-modify-writes run under `market/state.write_lock` (O_EXCL lock file, 30 s wait, a file older
than 5 min is a crash leftover). Measured: two processes adding 25 items each kept 25 of 50
without the lock (and Windows refused one `os.replace` with PermissionError); 50 of 50 with it.
**Captured, not guessed:** a `web_app` `<tg-button>` inside a Rich Message is accepted and
returned as `{"web_app": {"url": …}}` (one test message to the owner's chat,
tests/fixtures/miniapp/rich_web_app_button.json). **Not built:** product photos — saved results
carry no image ids because the pipeline rejects model-reported URLs by design (090); photos need
the China extraction to keep per-site image ids and build CDN URLs in code (a China-session
follow-up). Sort and filters later. Checked in a browser with a test-signed initData and the
real result fixture (deep link, pick, Details, Watch through the server with a fake action, back
button, own-chat only). Tests: tests/test_miniapp_china.py, tests/test_market_lock.py, server
method tests updated; 564 passed. Docs: docs/briefs/MINI_APP.md §12 and status,
docs/TELEGRAM_UX.md §6, ARCHITECHTURE.MD (second writer, POST), docs/briefs/CHINA_SEARCH.md
(Mini App row), docs/ROADMAP.md (step 0 done, China screen built), market/state.py docstring.


**098 — 2026-11-10 — Mini App step 2: every section is a real screen (Today, China search form, Market, Basket, Travel); forms hand commands to the listener through an inbox.**
Owner, after trying step 1: the China screen only showed results ("we should have options" — a
search form) and the other four said "Coming soon"; "start and finish all job together".
**China:** a search box with All / PDD / Taobao / 1688 above the results; progress is polled
(`GET /api/china/status`: queue running / yours waiting) and the new results appear by themselves;
a vague request still gets its 1–2 questions in the chat; a photo search stays in the chat (a
Mini App cannot hand a photo to the bot). **Today:** Today · Meals · Training · Week tabs — the
chat's own text for the asking person (`coach/plan_text`), turned into display blocks by
`miniapp/screens.html_blocks` (bold, italic, code, https links, folds; nothing else survives).
**Market:** the watch list with best price to Yerevan, Open / ✅ Bought / 🗑 Remove (second tap),
an add form (name, store link, optional weight — the chat dialog's checks, then `market.bot._finish`),
and 🔄 Check prices now. Edits go through the same `_mutate` and write lock as `/watch`, by item
id (not list number, so a changed list cannot hit another item). **Basket:** the last priced list
(`.browser/basket_<kind>.json`) by shop with product links, totals and the cheaper-shop
comparison; 🧺 price it again; a Price check box. **Travel:** the daily scan's status, the
cheapest trips and best stays of the latest scan (Sheet tabs Trips and Stays, cached 5 min, an
empty read is never cached), Scan now / Send digest, and Search flights / Search stays forms.
**How commands run — the design decision:** the Mini App server never starts jobs. `POST /api/run`
composes a chat command from validated fields, checks it with the parsers the chat uses
(`flights.parse_command`, `parse_cmd.parse`, `china.bot.DESC_RE`, the price shape) so the form shows the
chat's own error sentence, and writes it to `.browser/miniapp_inbox/` (`miniapp/inbox.py`:
allow-list `/basket /scan /digest /flights /stays /china /price /watch check`, chat id must be an
allowed chat, expires after 2 min, at most once). A new thread in `listener.py` (`inbox_loop`,
its own additive commit 2506ea1, full suite as the regression check, ARCHITECHTURE.MD updated)
passes each text to the same `handle_text` as a typed message, so it gets the chat's validation,
the one-job-at-a-time runner and its "already running" reply, and the answer lands in the
person's chat. Rejected alternatives: the server launching subprocesses itself (second runner, no
mutual exclusion with the listener, Chrome profile clashes) and putting the commands behind new
chat buttons. Limits: `/api/run` has its own 10 requests/minute per user on top of the 60/minute;
all new routes need a known signed user and the module permission (`people.can`: owner and adult
for plan, market, basket, travel, run). Bodies: JSON, only the expected keys, string values ≤ 300
characters. **Checked** in a browser with a test token and the real read-only data (plan, basket
file, travel Sheet rows) and fake actions: every screen, the China form's composed command and
busy state. Tests: tests/test_miniapp_screens.py (blocks, plan, basket and travel on real
fixtures, composition accept/reject, market add/bought/remove on a temp dir, endpoints incl.
permission, validation, limits), tests/test_miniapp_inbox.py, tests/test_listener_inbox.py.
**Not built:** photo search in the app; editing a watched item's weight or links (use /watch);
tick-off of basket items (the Google checklist does that); the Today per-person health hook beyond
what `today_text` already shows. Docs: docs/briefs/MINI_APP.md §13, docs/TELEGRAM_UX.md §6,
docs/ROADMAP.md, ARCHITECHTURE.MD (inbox thread, new endpoints).

**099 — 2026-11-10 — Mini App review (steps 0 and 1): what was checked, what was fixed, what is proposed.**
An independent review of steps 0 and 1 the day they were built: tests, an attacker's probes against a
throwaway server with a test token, the lock, the phone UI. Findings and larger proposals:
`docs/briefs/MINI_APP.md` §14–§15. Each fix below is its own commit and has a test that failed first
(`tests/test_miniapp_hardening.py`, `tests/test_market_lock.py`, `tests/test_china_bot.py`).
- **A GET with a body is refused (400) and the connection closed.** Reproduced: `GET /api/status`
  with `Content-Length: n` and a second request as the body got two answers on one connection —
  the body ran as its own request. Behind Tailscale Funnel the proxy reuses one connection to the
  server for several clients, so unread bytes are a request-smuggling primitive (the classic
  outcome is one person receiving another person's answer). The cross-person leak itself was not
  demonstrated through the tunnel; the primitive was, and the fix is five lines. Why not ignore
  the body: reading and discarding it keeps the connection in step too, but a GET with a body is
  never ours, so refusing is the smaller promise.
- **A POST whose body never arrives is a 408, connection closed, nothing run.** Reproduced:
  `Content-Length: 100` with 10 bytes sent gave a 500 after 20 s and the server then read the
  timed-out socket again (traceback). Should-fix, not a leak.
- **An expired session says "expired", not "private".** Telegram's initData is made when the app
  opens and the server accepts it for 24 h; a window left open (or minimised) longer got 401 and
  the page told the owner "This app is private". The server now answers `{"error": "expired"}`
  when the signature is valid and only `auth_date` is too old, and the page shows "Session
  expired" with Close. This tells an attacker nothing new: to see it they need a string Telegram
  signed for this bot. A bad signature, a future date and an unknown person are unchanged.
- **The nightly job writes the watch list under the same lock as everyone else.** Asked by the
  owner: can the job clobber an add made during its run? During the minutes of page reading, no —
  it re-reads `items.json` before each write. In two windows, yes (reproduced with a slowed write,
  `tests/test_market_lock.py` NightlyJob): the Sheet merge at the start (read list → read Sheet for
  seconds → write list; only once `watch_sheet_id` is set, which it is not yet) and the page-weight
  fill (milliseconds). Both now run under `market/state.write_lock`
  (`jobs/market_watch.sync_list`, `apply_filled`). A list that stays busy is never a crash: the
  job uses the list on disk and the report says the Sheet edits were not merged; page weights are
  read again the next night.
- **A lock holder removes the lock file only while it is still its own** (a random token in the
  file). Reproduced: a holder that outlived `stale_s` was taken over, then removed the new
  holder's file on its way out, and a third writer entered beside it.
- **Known and left, for SQLite at Users and roles (MINI_APP.md §14):** `market/bot._mutate` holds
  the lock across the Sheet read, and writes the Sheet after releasing it, so two edits within the
  same second or two can still let a stale Sheet row undo the other edit. A lock file around JSON
  files and a Sheet cannot close that; one database transaction can.
- **👁 Watch on a product already on the list adds nothing** and answers "👁 Already on 🌍 Market
  watch: <name> — nothing added." (chat and Mini App; the page shows it as done). Reproduced: two
  taps made two items. Matched by the product link among active items, so a bought or removed
  item can be watched again. This also makes the Mini App's POST safe to repeat.
- **China card: the delivered total is the headline.** The card showed the listing price large
  and "5,233 AMD ($14.52) via Onex sea" small and grey under it; what the family pays at the door
  is the number that decides. Now "Delivered <total>" on top, "Item <price>" under it. Same
  strings from `china_view.py`; the page still computes nothing.
- **The lock no longer crashes on Windows when a holder re-takes it at once.** Found by running
  the committed state in a clean worktree: `os.open(O_CREAT|O_EXCL)` raised `PermissionError`
  when the previous holder had just deleted the lock file while another process still had it open
  for its age check (Windows keeps such a file in a "delete pending" state). Measured with three
  processes re-taking the lock 150 times each: a crashed writer in 2 runs of 6 with the lock as
  built in 097, 0 of 6 with a short retry. In real use this was a 👁 Watch or `/watch` command
  failing at random when two things wrote at once. The 097 test (two processes, 25 writes, a
  5 ms pause) was too gentle to show it.
- **Proposed, not built (owner decides): `docs/briefs/MINI_APP.md` §14.3** — a framework server,
  SQLite instead of JSON files with a lock, a session after the first initData check, a named
  tunnel on our own domain; all four at Users and roles, none now. **§14.4** — China photos through
  image ids and thumbnails served by the PC (decision 090 kept), sort orders sent ready-made by
  the server, a compact card. **§15** — the far goal: a household agent on a ladder from "inform"
  to "standing rules", an action ledger and limits in code before anything is spent, Telegram
  kept as the front door but not as the foundation.
