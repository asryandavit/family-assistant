# COACH_SPEC.md — Family Coach Bot, v2

Supersedes Baseline Spec v1. Every difference from v1 is recorded in `docs/DECISIONS.md`.

---

## 1. Product

Two adults in Yerevan (Davit, wife), one toddler son (born 29 Dec 2024), delivered
through the existing family-assistant Telegram bot.

**Goal: recomposition.** Fat loss is the priority, but muscle retention is part of the
target outcome, not a side effect. This has a consequence that is stated here so it is
never discovered as a surprise: **this system will rarely cut calories.** The deficit is
conservative (15%), the plateau rule is deliberately hard to trigger, and training
progression and adherence are the primary levers. Eight weeks in, the honest answer to
"why hasn't it changed anything" is "because it is working as specified."

**The son is not a tracked user.** He appears as one daily movement-play idea in the
morning brief and as inline baby modifications in every meal (no added sugar, minimal
salt, safe cut sizes, choking-hazard list), plus an optional `/baby` note log. No calorie
counting for the baby, ever.

**Equipment: a mat and nothing else.** This is enforced structurally (§7), not advisory.
No purchase suggestions, ever, not even framed as optional.

**Food: realistic for Armenian markets** (SAS, Yerevan City, Carrefour, Evrika, GUM) —
matsun, tvorog, lori/chanakh, eggs, chicken, beef, trout, lentils, beans, bulgur,
buckwheat, oats, lavash, seasonal produce. Imports are optional swaps, never requirements.

**One family meal.** The same dish for everyone, per-adult portions in grams, baby
modifications inline. Never separate cooking for separate people.

**Language: English only**, both users.

---

## 2. Users, roles and privacy

Both adults hold the `owner` role — full access to every command including `/scan`,
`/stays`, `/auto`, `/cancel`. Default deny for anyone not on the allowlist.

Role governs the machine, not each other's bodies:

| Data | Visibility |
|---|---|
| Own weight, waist, adherence, interview answers | Self only |
| Postpartum symptoms, `/pain` flags, clearance status | Self only, and never mirrored anywhere |
| Family meal plan, shopping list, freezer inventory, week schedule | Both |
| Coach Sheet weight tabs | Per-user consent, revocable in `/settings` |

Scheduled travel digests continue to go only to the env chat id. Holding the role means
either adult can run `/scan`; it does not subscribe them to the other's digest.

Onboarding runs separately and privately for each adult. `/forgetme` deletes your own data.

---

## 3. Module boundary

- `coach/core` — users, weights, state, decisions, event bus, deterministic calculators,
  trend engine, scheduling helpers, interview engine.
- `coach/training` — owns `workout_plans`, `workout_feedback`, `progression_state`,
  `exercises`, postpartum gating. Commands `/workout /done /missed /move /pain`.
- `coach/meals` — owns `meal_week`, `meal_log`, `food_db`, `recipes`,
  `recipe_ingredients`, `freezer_inventory`, shopping list, substitutions, cheat and
  cooking-practice events, hydration. Commands `/meals /shopping /sub /event /ate
  /cooking /swap`.

**Hard rule:** modules never read or write each other's tables. They interact only
through core APIs and the event contract. Each must run with the other disabled via
feature flags. Contract tests enforce this.

---

## 4. Storage

SQLite is the source of truth. See `CLAUDE.md` §3 for the invariants — they are
operating rules for every session, not spec prose.

**Google Sheets is a read-only mirror.** No coach code path ever reads from a Sheet. The
moment a number can come back from a spreadsheet, a hand-edit becomes an input.
Recovery from the mirror is a deliberate manual act, never a code path.

- A **new coach Sheet**, separate from the travel Sheet, because Drive sharing is
  per-file and the travel Sheet holds flight monitoring and the ops log.
- Per-user tabs (`Weight_Davit`, `Weight_Wife`), per-user target Sheet id in
  `config_coach.json` from day one, defaulting to the same file. Revocation is: stop
  future writes, delete that tab, log a DECISIONS entry.
- **Weights and waist mirror on every successful write**, not only nightly — a year of
  measurements cannot be recovered from anything else. Everything else mirrors nightly.
- The user is confirmed from the **SQLite** write. The mirror is attempted after and
  queues to `pending_sheets.jsonl` on failure.
- **The sensitive tier is never mirrored**: postpartum symptoms, pain flags,
  breastfeeding status, medical clearance.
- Coach jobs append run rows to the existing `Runs` tab. **Job-level only** —
  `coach_meals | ok | week 31 generated`, never `coach_weight | ok | wife 68.4`.
  No names, no numbers about people.

### Backups

`VACUUM INTO` a local staging path (never a plain file copy — a copy of a live database
with a hot WAL restores to a state that never existed) → encrypt with `pyzipper`
(AES-256 ZIP) into the Drive folder's `.staging\` → atomic rename within that directory.
The unencrypted `.db` must never exist inside the synced tree, even briefly.

Retention 7 daily + 4 weekly. Passphrase lives in a Windows user env var **and** in the
password manager — an unattended job needs it on the machine, and disk-failure recovery
needs it off the machine.

**The restore drill is automatic**, part of the nightly job: decrypt the snapshot just
written, open it at a temp path, run a real query against the `weights` table. Result
goes into the nightly `Runs` row, so a drill that stops running is distinguishable from
a drill that passes. The monthly review states how many drills passed in the period.

Recovery precedence: **the encrypted snapshot is the primary path.** The Sheet mirror is
human-readable insurance for when both disk and snapshots are gone.

---

## 5. Data model

`users(id, tg_id, name, role, sex, dob_local, height_cm, activity_mult, breastfeeding,
clearance_confirmed, postpartum_status, kcal_target, protein_g_target, protein_g_per_kg,
deficit_pct, kcal_floor, weekday_active_min, weekend_active_min, new_dish_rate,
waist_tracking_enabled, sheet_id, sheet_consent, paused_until_local, created_ts_utc)`

`weights(id, user_id, date_local, kg, waist_cm, hips_cm, context, ts_utc)` — context is
`normal | travel | paused`

`exercises(id, name, session_type, pattern, equipment, impact, core_pressure,
postpartum_tier, unit, progression_axis, cues, source, active)`

```sql
CREATE TABLE exercises (
  id               INTEGER PRIMARY KEY,
  name             TEXT NOT NULL,
  session_type     TEXT NOT NULL CHECK (session_type IN
                     ('strength','conditioning','yoga','mobility','breathwork','wind_down')),
  pattern          TEXT NOT NULL,
  equipment        TEXT NOT NULL CHECK (equipment IN ('none','mat')),
  impact           INTEGER NOT NULL CHECK (impact IN (0,1)),
  core_pressure    TEXT NOT NULL CHECK (core_pressure IN ('low','med','high')),
  postpartum_tier  INTEGER NOT NULL CHECK (postpartum_tier IN (0,1,2)),
  unit             TEXT NOT NULL CHECK (unit IN ('reps','seconds')),
  progression_axis TEXT NOT NULL,
  cues             TEXT NOT NULL,
  source           TEXT NOT NULL,
  active           INTEGER NOT NULL DEFAULT 1
) STRICT;
```

A dumbbell exercise cannot be inserted. Adding equipment later is a migration — a
deliberate act.

`workout_plans(id, user_id, week_no, date_local, session_type, session_json, status)` —
status `planned | done | missed | moved`
`workout_feedback(plan_id, rpe, energy, pain_flag, note, ts_utc)`
`progression_state(user_id, pattern, level, next_step, last_advanced_local)`

`recipes(id, name, active_minutes, total_minutes, freezer_friendly, portions_yield,
equipment_needed, is_family_original, source, notes)`
`recipe_ingredients(recipe_id, food_id, grams)` — macros are **computed from food_db**,
never stored from a model's answer. A cached macro column is permitted only with a test
that recomputes and asserts equality.
`food_db(id, item, kcal_100g, protein_100g, carbs_100g, fat_100g, aliases,
armenian_note, season, source)`
`meal_week(id, week_no, version, plan_json, relaxations_json, generated_ts_utc, status)`
`meal_log(user_id, date_local, adherence, est_delta_kcal, note, ts_utc)`
`freezer_inventory(id, recipe_id, portions_remaining, frozen_date_local, use_by_local,
last_confirmed_local)`
`cook_schedule(user_id, weekday, is_cook)` plus per-date overrides written by `/swap`

`interview_questions(id, module, section, order_no, type, text, validation_json, active)`
`interview_answers(user_id, question_id, answer_raw, answer_typed, ts_utc)` — raw always
stored; typed where parseable. Free-text answers are read by the model at generation
time; code never parses them.

`conversations(user_id, kind, state_json, last_activity_ts_utc)`
`events(id, ts_utc, type, payload_json, processed)`
`decisions(no, date_local, text, reason)`
`travel(id, city, start_date_local, end_date_local, note)`
`state(key, value)`

---

## 6. Calculators

Pure functions, pytest-covered. The model never performs this arithmetic.

- `bmr_msj(sex, kg, cm, age)` — men `10*kg + 6.25*cm - 5*age + 5`; women `-161`.
- `tdee = bmr * multiplier` (1.2 / 1.375 / 1.55 / 1.725, chosen honestly at onboarding).
- **Deficit: 15%** (band 15–25%, conservative end chosen deliberately — aggressive
  deficits cost lean mass). Rounded to 50 kcal.
- **Protein: 2.0 g/kg** (band 1.6–2.2, top end for recomposition).
- Expected loss ~0.25–0.5 kg/week at this deficit.
- **Floors, hard and configurable: 1,500 kcal (Davit) / 1,300 kcal (wife).** Rebalancing
  may never breach a floor.
- **Breastfeeding gate: dormant.** Wife is not breastfeeding; the son eats solids. The
  `breastfeeding` and `clearance_confirmed` columns and the calculator branch remain in
  place — one boolean and one `if`, already tested. If breastfeeding were ever Yes, the
  floor rises to 1,800 kcal, loss caps at 0.5 kg/week, and **no deficit at all applies
  until medical clearance is confirmed**. Her answer comes from her own private
  onboarding, not pre-set from the other adult's account.
- `trend(user)` — rolling average over available readings; weekly delta measured on the
  trend, never on a single reading. **No trend emitted below 3 readings spanning 14 days.**
- `portion_scale(dish, kcal_share, protein_min)`.
- `rebalance(remaining_days, overage_kcal)` — spread proportionally, cap −15%/day,
  respect floors, ignore overage below 150 kcal.
- Alcohol estimates: beer ~150 kcal, 150 ml wine ~125, 44 ml shot ~97, sweet cocktail
  250–450.

### 6.1 Plateau detection (v2)

The v1 rule (21 days, weight only, cut ~10%) is **replaced**. Successful recomposition
looks exactly like a v1 plateau — fat down, muscle up, scale flat — and cutting calories
would be the precise opposite of the correct response.

```
PlateauDetected(user) fires only when ALL hold:
  window                = 28 days
  weight readings       >= 4, spanning >= 21 days
  |weight trend delta|  < 0.3 kg across the window
  adherence             >= 80%
  travel/paused days in window = 0
  waist:       tracking disabled, OR waist trend delta > -1.0 cm
  progression: no advance in progression_state within the window
```

28 days rather than 21 because weigh-ins are weekly: 21 days is three readings, which
cannot separate a real stall from one odd Saturday.

The −1.0 cm threshold reflects real measurement error (±1–2 cm from tape tension, breath
phase, landmark drift, time of day) against real change (~0.5–1 cm/month at this
deficit). The rule survives that noise because it is **asymmetric**: waist only ever
*suppresses* a cut, never triggers one. A false "still falling" delays a cut by four
weeks; a false "flat" fires nothing on its own, because progression must also be stalled.

**Measurement protocol, fixed and restated with each Saturday prompt:** at navel level,
Saturday morning, before eating, at the end of a normal exhale, tape snug without
compressing. Navel rather than "narrowest point" — narrowest requires a judgement call
that moves between sessions.

`waist_tracking_enabled` is per user, asked in that user's own onboarding. If declined,
that user's rule falls back to weight-only with the same window — degraded, not broken.

```
RecompositionProgress(user) — weight flat, waist falling more than 1.0 cm over the window.
  Effect: no calorie change, and an explicit message saying this is the goal being met
  and that the scale is the wrong instrument for it.
```

This message is mandatory, not optional. The absence of a plateau alarm communicates
nothing; only a positive statement counters what a flat scale appears to say.

```
HardPlateau(user) — weight AND waist both flat for 56 days, adherence >= 80%.
  Fires regardless of progression_state. Applies the ~10% cut, floors respected.
```

The override exists because progression is unreliable as a suppressor early on: an
untrained person's numbers climb on motor learning — better bracing, better position,
more confidence — for months, with little relation to tissue. Without it, a genuine
stall could be suppressed indefinitely by the very signal meant to detect success.
56 days is exactly two consecutive 28-day windows.

**Monthly review headline order:** waist change, then weight trend, then progression
advances, then adherence. Weight is one line of four, not the number the report is about.

---

## 7. Training

Owned by `coach/training`.

**Session types are first-class**, each with its own progression: `strength`,
`conditioning`, `yoga`, `mobility`, `breathwork`, `wind_down`. Yoga, mobility,
breathwork and wind-down are not rest-day filler — with a toddler in the house the
stress and sleep side matters as much as the training side. They are mat-only by nature.

**Equipment enforcement:** the generator receives a candidate list filtered from
`exercises` and returns `exercise_id` values from it. Ids outside the list are rejected
and re-asked once, then a deterministic session is served. If a session cannot be built
from the table, that is a table problem for the owner to fix — never a licence to
improvise.

**Progression axes**, in order: reps → tempo → range → leverage → density.

**Postpartum gate, fully in force.** Postpartum is not the same as breastfeeding: at 19
months, pelvic-floor and abdominal-wall considerations do not expire. Onboarding
includes the symptom screen (doming, leakage, heaviness). Until symptom-free and
confirmed, tier-0 only (breathing, TA activation, glute bridge, bird-dog) and impact
moves locked. `/pain` or any symptom flag triggers immediate regression and recommends
pelvic-floor physiotherapy. The bot is not a medical provider and says so where relevant.

---

## 8. Meals

Owned by `coach/meals`.

**Start from the existing rotation.** Family dishes are captured first and the plan
adjusts portions, protein and balance before introducing anything new. New dishes arrive
at a rate the owner sets (`new_dish_rate`), never by default. Novel dishes every week is
how a plan dies in week three.

**Effort is a hard constraint, like calories.** Recipes carry `active_minutes` and
`total_minutes`. Each day is validated against **that day's cook** — the wife is the
default cook, Davit's days are the exception, and `/swap` flips a day's cook and
re-validates that day's meal against the new ceiling, offering a faster alternative if
it no longer fits. Weekday ceilings bind; weekend ceilings may be higher.

### 8.1 Batch cooking and the freezer

Recipes are tagged `freezer_friendly` with a `portions_yield`. The Sunday plan includes
a batch session: cook this much, eat this now, freeze this many portions. Shopping
quantities reflect batch amounts, not single-meal amounts. Freezer capacity from the
interview caps how aggressive this can be.

**Deduction is the default, not a report.** If a day's plan says "freezer portion of X"
and the adult taps **Followed** at the 21:00 evening check, the portion is deducted
automatically. Only deviation needs a report — tapping **Deviated** raises one follow-up
button: "Did the freezer portion still get used? [Yes] [No]".

The burden is inverted deliberately: freezing happens at a moment of high engagement
(Sunday, batch session, one button); eating happens on a Tuesday with a toddler.

**Trust decay:** if the inventory has not been confirmed for 3 weeks, the generator stops
planning meals *from* the freezer and plans only *into* it until reconciled. Staleness is
a representable state, and the failure degrades to a slightly worse plan rather than to a
missing dinner.

### 8.2 Constraint relaxation order

Some weeks have no valid solution. The order is fixed in code so the model never chooses
which rule to break.

**Never relaxed:** calorie and protein floors · one family meal · effort ceilings.

**Relaxed automatically, in this order:**

1. Novelty — new dishes dropped, known dishes only
2. Variety — a dish may repeat within the week
3. Freezer targets — batch goals shrink for the week
4. Portion rounding — up to ±5% on individual meals, exact across the day

Every relaxation applied is named in the plan message.

**If still unsolvable**, the Sunday 16:00 job fails to the owner only, naming the exact
conflict with resolution buttons. A plan that breaches a hard constraint is never served.

### 8.3 Cooking practice (`/cooking`)

Davit holds a Scoolinary membership and will cook course dishes on notice. This is a
planned deviation with advance warning — the `/event` shape, positive rather than
negative.

`/cooking` → "What are you making?" → free text → the displaced planned meal is handled
explicitly (**[Push to tomorrow] [Cancel it] [Keep ingredients for later]**) → rough
calorie ballpark buttons (**[Lighter ~500] [Normal ~700] [Rich ~900]** per portion) →
`rebalance()` absorbs it within caps and floors.

Logged as cooking practice, **not** as a deviation — practising cooking is pro-plan
behaviour and must never count against adherence. A successful dish gets a one-tap
"add to our rotation?" offer, queueing it for recipe capture.

### 8.4 Cheat and event protocol (`/event`)

Wizard: when + kind (party | restaurant | holiday) + who.

1. **Before** — same-day strategy: lighter higher-protein earlier meals, protein and veg
   first, drink estimates, alternate with water, pick one or two treats you actually want.
2. **After** — quick buttons Light ~+300 / Medium ~+600 / Heavy ~+1000 / custom.
3. `rebalance()` spreads the overage within caps and floors; confirmation shows the new
   per-day targets.
4. **Training is explicitly untouched.** No punishment cardio, no guilt language, 80/20
   framing.

### 8.5 Substitutions (`/sub`)

`/sub <ingredient>` (+ reason) → the model proposes 2–3 Armenian-available swaps **from
`food_db`** with macro deltas (Greek yogurt → matsun; cottage cheese → tvorog; salmon →
trout; quinoa → bulgur) → the user picks → code recalculates portions, day macros and
shopping quantities. Items missing from `food_db` are added with sourced per-100g values
first. Nutrition numbers are never invented.

---

## 9. Event contract

| Event | Producer | Consumers | Effect |
|---|---|---|---|
| `WeightLogged(user, kg, waist_cm, date_local)` | core | core | update trend; may emit `TargetsRecalculated` |
| `TargetsRecalculated(user, kcal, protein_g)` | core | Meals | rescale portions for the remaining week |
| `WorkoutCompleted(user, session, rpe, energy)` | Training | core | log; feeds `LowEnergyStreak`. No calorie credit |
| `WorkoutMissed(user, reason)` | Training | Training | reshuffle week keeping ≥48h between hard sessions. No meal change |
| `CheatEventReported(user\|family, date_local, kind, est_kcal)` | Meals | Meals | same-day strategy + `WeekRebalanced` |
| `CookingPracticeReported(user, dish, est_kcal, date_local)` | Meals | Meals | displace planned meal, rebalance; **not** an adherence miss |
| `WeekRebalanced(user, per_day_deltas)` | Meals | core | decision logged; next briefs reflect new targets |
| `PlateauDetected(user)` | core trend job | Training, then Meals | training progression first; if none, Meals cuts ~10% (floors respected) |
| `RecompositionProgress(user)` | core trend job | core | **no calorie change**; explicit success message |
| `HardPlateau(user)` | core trend job | Meals | ~10% cut regardless of progression, floors respected |
| `LowEnergyStreak(user, n>=3)` | core | Training + Meals | deload scheduled; kcal raised 100–200 if intake < 75% TDEE |
| `PostpartumFlag(user, symptom)` | Training | Training | regress to tier-0; advise pelvic-floor physio |
| `FreezerPortionUsed(user, recipe_id, date_local)` | Meals | Meals | decrement inventory |
| `FreezerInventoryStale(days)` | Meals | Meals | stop planning from freezer until reconciled |
| `TravelModeStarted(dates, city)` / `TravelModeEnded` | core | Training + Meals | see §10 |
| `TrackingPaused(user, until)` / `TrackingResumed` | core | Training + Meals | see §10 |

---

## 10. Travel and pause

**Travel** — `/travel <city> <dd.mm-dd.mm>`, ending automatically on the end date.
Meals switch to principles (protein first, vegetables at every meal, one treat you
actually want, water between drinks) and local-food guidance; no shopping list, no
portioned home cooking, no adherence buttons that can only be failed. Training switches
to a no-equipment 15–20 minute set and **suspends** progression rather than regressing
it. Weight readings inside a travel window are tagged `travel` and excluded from the
trend engine — no plateau detection, no target recalculation. On return, the previous
progression level resumes; nothing resets.

**Pause** — `/pause [days]` and `/resume` per user. A sick toddler, an illness or a bad
week is a first-class state, not a silent failure streak. Paused users receive no
scheduled pushes, no adherence prompts, and no plateau or streak detection.

---

## 11. Telegram UX

Timezone Asia/Yerevan. Allowlist of exactly two Telegram user IDs, default deny.

**Menu-first.** Six top-level buttons — Training · Meals · Weight · Baby · Status ·
Settings — each opening a submenu (Meals → Today's meals, Shopping list, Substitute,
Report an event, Cooking practice). Slash commands remain as unlisted power-user
shortcuts. `callback_data` carries only ids and short codes within the 64-byte cap, with
a `co:` prefix for coach buttons so unprefixed legacy travel buttons keep routing.

### Update routing precedence

Evaluated top-down, first match wins:

1. Sender not on the allowlist → ignored silently.
2. Callback query → `answerCallbackQuery` **first**, before any database access
   (a `busy_timeout` wait would otherwise render as a dead button), then route by prefix.
3. Message starting with `/` → command. Commands always pre-empt an active conversation,
   which is **suspended, not discarded** — state is in SQLite and resumes on the
   matching command. A user is never trapped in a wizard.
4. Active, non-expired conversation for this sender → input belongs to that conversation.
5. Bare input with no active conversation → parse as weight (30–250 kg). Failure returns
   a human sentence naming what was expected.
6. Anything else, including non-text updates → a short hint. Never silence.

**Conversation expiry: 30 minutes** of inactivity. Past that, bare input no longer routes
to the conversation — otherwise a Saturday weigh-in reply would be swallowed by an
onboarding question abandoned on Tuesday. An expired conversation produces a **signpost,
not a fallthrough**: "Onboarding is paused at question 6. Send /onboarding to resume, or
a number on its own to log a weight."

**Edited messages are not read**, and say so once rather than being silently ignored.

**Staleness:** a command message whose Telegram timestamp is older than 10 minutes at
the moment of processing is discarded with a count logged. This applies at processing
time, not only at startup — the machine sleeps without restarting the listener, so
commands typed during a sleep arrive on wake and would otherwise fire hours late.
**Callback queries in the startup backlog are discarded wholesale** regardless of age: a
tap from before a crash should be re-tapped, since "confirm rebalance" is not idempotent.
Live taps on old messages are unaffected.

`/cancel` keeps its exact current meaning — sweep running jobs, owner-only. **`/stop`**
aborts the caller's own conversation. No overloading.

**Commands:** `/start /onboarding /today /workout /meals /shopping /weight /event /sub
/ate /cooking /swap /done /missed /move /pain /baby /travel /pause /resume /settings
/report /stop /help`.

---

## 12. Schedule

All times Asia/Yerevan. All coach tasks: `LogonType=S4U` (runs whether or not anyone is
signed in), `DisallowStartIfOnBatteries=$false`, `StopIfGoingOnBatteries=$false`,
`MultipleInstances=IgnoreNew`, `ExecutionTimeLimit=PT30M` (nightly `PT1H`).
Task names prefixed `FamilyAssistant-Coach-`.

| Time | Job | Model call | Catch-up if missed |
|---|---|---|---|
| 03:15 daily + at boot | Nightly: selfcheck → trend → `VACUUM INTO` → encrypt → move → restore drill → copy `docs/*.md` → prune → Sheets export → `Runs` row | no | **yes** |
| 07:30 daily | Morning brief | no | no |
| 21:00 daily | Evening check | no | no |
| Sat 09:00 | Weigh-in prompt (weight + waist) | no | no |
| Sun 16:00 | **Generate + validate** next week's plan, store only | **yes** | yes |
| Sun 18:00 | **Send** plan + shopping list from the store | no | no |
| 1st, 10:00 | Monthly review | yes | yes |

**Nightly ordering matters:** `selfcheck.py` regenerates the `ARCHITECTURE.md` generated
section *before* the docs copy, or Drive receives yesterday's inventory every night.

**Evening check at 21:00**, not 20:30 — 20:30 is toddler bedtime, and an unanswered
check-in becomes false non-adherence data feeding a rule that requires ≥80% adherence.

**Sunday is split** so a model failure or a >5% macro mismatch surfaces to the owner at
16:00 with two hours of slack, rather than reaching both adults at 18:00 as silence or a
stale plan. If unresolved by 18:00, last week's plan is sent **labelled as last week's** —
degraded but honest, never silent.

**Quiet hours 22:00–07:00, enforced in code, not by trigger times.** Every scheduled push
carries a validity window: morning brief until 10:00, evening check until 22:00, weigh-in
until 12:00. Outside it the push is dropped, logged to `Runs`, and surfaced in the next
brief ("no evening check logged yesterday"). `StartWhenAvailable=$false` on all pushes,
so a catch-up cannot deliver a morning brief at 14:00.

**Listener startup staleness audit:** last snapshot, last restore drill, last travel
scan, and per-task missed-run counts, read through `lib/tasks.py` so the Windows-only
call stays inside the portability boundary.

**`/cancel` safety:** coach writes are transactional *and* cancel is scoped to the named
running job. Transactions protect the database; scoping protects the outcome. A
cleanly-rolled-back Sunday generation still leaves no plan for the week, so the 07:30
brief fails loudly when no plan exists for the current week.

---

## 13. AI layer

Via `claude -p` (Claude Code CLI) as a subprocess, prompt piped via STDIN (Windows argv
caps near 32k), `--output-format json`, prompts stored as markdown files, strict JSON
out, parsed defensively. This draws on the existing Max subscription and is free. **Not**
the Anthropic API or Agent SDK.

Batch, never per-message: Sunday plan generation, workout variety within
`progression_state`, `/sub` proposals, event and cooking-practice strategy text, monthly
review narrative.

**Validation loop:** recompute the macros of any proposed plan in code. Off by more than
5% → adjust portions programmatically or re-ask once. **Fallback:** on failure, serve the
cached plan plus a deterministic default session; log and continue.

Daily 07:30 and 21:00 messages are templated from the stored plan with **no model call**.

**A cross-process lock file wraps every `claude -p` invocation.** Both the travel digest
and coach generation now draw on one Max subscription from Task-Scheduler-launched
processes that do not share the listener's in-memory lock. A throttle would surface as a
JSON parse failure and be misdiagnosed as a prompt bug.

---

## 14. Interview

**All questions upfront in Phase 1** — roughly 50 per adult, one at a time, resumable
across sittings, grouped in sections with progress shown ("section 3 of 5"). The full
catalogue is authored and reviewed on paper before Phase 1 builds it, so the consuming
data shapes are designed at the same time, where rework is free.

**Boundary:** the interview collects dish *names* only. The dish-by-dish capture of the
existing rotation — ingredients and grams for roughly 15 family dishes — is Phase 3a,
not part of the interview.

Sections:

1. **Basics** (calculator-critical): sex, DOB, height, weight, activity multiplier,
   breastfeeding, waist tracking opt-in.
2. **Training history**: what has been tried before and specifically **why it stopped** —
   the single most predictive answer either adult will give; injury history, not just
   current pain.
3. **Movement self-screen**: squat to depth, push-up form, plank hold, single-leg
   balance, any position that hurts. Baseline capacity numbers to set a starting level.
4. **Life**: sleep hours and quality honestly, stress and what is already done about it,
   real training windows (nap times, before he wakes, after he sleeps), what is enjoyed
   and what is hated, yoga and mobility experience and what is wanted from it.
5. **Kitchen**: who cooks and when, real cooking skill and confidence, weekday versus
   weekend active-time ceilings, equipment including oven, slow cooker and **freezer
   capacity**, dishes already cooked and liked, foods that will not be eaten, tolerance
   for repeats, current breakfast, eating out frequency, where and how often shopping
   happens, and what the son actually eats today including textures and refusals.

Reasoning is shown occasionally so it reads like a professional asking rather than a form
being filled. At the section-5 break the interview states plainly that meal planning
arrives in a few weeks and these answers are so it starts right.

**The movement self-screen is low-fidelity by nature.** "Can you squat to depth"
self-assessed over text is a guess with a number attached. It sets a conservative
starting level only; the first two weeks of RPE and pain flags do the real calibration.

---

## 15. Phases

| Phase | Contents |
|---|---|
| **0** | Scaffold: module structure, `config_coach.json`, schema applied, `lib/telegram.py` multi-chat, `lib/sheets.py` queue fix, listener changes (per-update isolation, offset file, conversation delegation, roles, menus), two-user allowlist, `/health`, one scheduled test job, pytest + ruff, `REGRESSION.md`, `RUNBOOK.md`, `SECRETS.md`, `machine.json` |
| **1** | Core: interview engine + full catalogue, `/weight` with waist, calculators with full tests, trend job, pause/travel state, DECISIONS plumbing, Sheets mirror, `RECOVERY.md` |
| **2** | Training end to end: `exercises` seeded and reviewed, plan storage, 07:30 card, 21:00 buttons, `/done /missed /move /pain`, progression engine, postpartum gate |
| **— GO LIVE —** | **Both adults use the system for two weeks before meals is built.** |
| **3a** | Recipe capture: `food_db` seeded with ~60 sourced Armenian staples, the existing family rotation captured dish by dish with computed macros |
| **3b** | Meal generation: Sunday generation within budgets and effort ceilings, per-adult portions, freezer system, `/meals /shopping /sub /cooking /swap` |
| **4** | Interconnection: event bus, cheat protocol, plateau v2 + low-energy rules, rebalance engine, travel mode wiring, contract tests proving module isolation |
| **5** | Automation polish: Sat/Sun/monthly jobs, backups, deployment, `/report` |
| **Backlog (not v1)** | Sheets charts, grocery ordering, baby milestone tracker, voice notes, automatic hand-off from the flight monitor into travel mode |

**Go-live after Phase 2** applies the project's own build-order rule at project scale.
Two weeks of real use answers what design cannot: whether 21:00 is the right hour,
whether the morning brief is short enough to read, whether the evening buttons actually
get tapped — and, most importantly for Phase 3b, whether freezer deduction can be
trusted. Those answers should shape meals rather than arrive after it is built.

**Phase 0 discovery items** (assumptions that must be measured, never assumed):

- **Does `claude -p` work under an S4U task?** S4U runs as the user without an
  interactive session; whether the CLI's stored credentials resolve there is unverified.
  Only Sunday 16:00 and the monthly review depend on it — the nightly job makes no model
  call. Test with a throwaway task before any coach job depends on it.
- `pyzipper` round-trip on this machine (7-Zip is not installed, and a binary dependency
  would break the portability rule).
- The new coach Sheet must be shared with
  `sheets-writer@family-assistant-503305.iam.gserviceaccount.com` as Editor, or the first
  write fails with a 404 that reads like a bad id.
- Delete the unused placeholder `Training` and `Meals` tabs from the travel Sheet.
- Extend `selfcheck.py` to cover coach modules, config keys and scheduled tasks.
