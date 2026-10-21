# TELEGRAM_UX.md — how the bot looks and is navigated

Source of truth for the bot's structure, message templates and button conventions
(decision 080). Every new feature plugs into this; it never adds its own top-level menu.
Everything here uses free, built-in Telegram Bot API features — verified on this bot on
2026-10-18 (expandable blockquote, chat action, delete).

---

## 1. Structure

```
Bottom keyboard (always visible)      [ 🏠 Home ] [ 🔍 Price check ]

🏠 Home  — one message, edited in place as you navigate
 ├─ 📅 Today      today's meals, prep, both sessions   (live from plan/, §5c; /today)
 ├─ 🍽 Meals      this week's menu, one fold per day, recipe references
 ├─ 🏃 Training   today's session per adult: cues, videos, safety
 ├─ 🛒 Shopping   price check, 🧺 basket, 📋 checklist (Sheet), shopping plan
 ├─ ✈️ Travel     scan, digest, flights/stays how-to, automation
 └─ ⚙️ System     status, automation, cancel, help
```

- **Home** opens with `/start`, `/menu` or the 🏠 Home key. Section taps **edit the same
  message** (no new message per tap) and every section has `⬅️ Home`.
- **Slash commands keep working** for everything (`/price`, `/flights`, `/stays`, `/scan`…).
  They're shortcuts; nobody has to remember them.
- **🔍 Price check** asks "Which product?" with a reply prompt; the answer runs `/price`.
- A feature that isn't built yet does not get a button. Today/Meals/Training show live
  content from `plan/` (§5c); the Drive plan docs stay as secondary link buttons.

## 2. Message template

Every message the bot authors follows one shape (helpers in `lib/ui.py`):

```
<icon> <b>Title</b> · <i>context</i>        header — one line
<i>subtitle: date, filters, scope</i>       optional, grey
━━━━━━━━━━━━                                divider (lib/fmt.BAR)
key content: the 3–5 lines that matter     always visible
▸ details folded in an expandable block    long lists, cues, "and N more"
━━━━━━━━━━━━
<i>footer: legend / source / next step</i>  optional, short
```

Rules:
- **Lead with the answer.** The verdict or today's plan comes first; lists after.
- **Fold, don't truncate.** Anything beyond the top 3–5 lines goes into
  `<blockquote expandable>` — the reader taps to open it.
- One icon per section, from §4. No decorative emoji strings.
- Numbers come computed (CLAUDE.md §2); templates only lay them out.
- English only (CLAUDE.md §7). Product names from the shops are data and stay as given.
- Stay under the 4096-character limit; `lib/telegram._split` keeps folded blocks intact
  if a message ever has to be split.

## 3. Buttons and routing

| Kind | Looks like | Use |
|---|---|---|
| Bottom keyboard | big keys under the text field, always there | Home, Price check — nothing else |
| Inline navigation | buttons under the Home message | sections and ⬅️ Home; edits in place |
| Inline action | buttons under a result | run something (scan, digest, sort cheapest/best match) |
| Link button | opens a page | plan docs in Drive, shop pages |

`callback_data` prefixes (64-byte cap, ids and short codes only):

| Prefix | Meaning | Status |
|---|---|---|
| `ui:<section>` | navigation: `ui:home`, `ui:today`, `ui:meals`, `ui:training`, `ui:shop`, `ui:travel`, `ui:system` | new |
| `cmd:<action>` | run a menu action (`scan`, `digest`, `status`, `cancel`, `auto`, `basket`) | existing, kept |
| `st:` `o:` `g:` | stays search / filter panel | existing, kept |
| `sw:` | automation switches | existing, kept |
| `co:` | reserved for coach actions (COACH_SPEC §11) | reserved |

Buttons in old messages must keep working — prefixes are never renamed or reused.

## 4. Icons

| Section | Icon | | Section | Icon |
|---|---|---|---|---|
| Home | 🏠 | | Shopping / prices | 🛒 |
| Today | 📅 | | Travel / flights | ✈️ |
| Meals | 🍽 | | Stays | 🏨 |
| Training | 🏃 | | System / automation | ⚙️ |
| Running | ⏳ | | Warning | ⚠️ |
| Compare | ⚖️ | | Deal / drop | 📉 |

Shops: 🟢 Parma · 🔴 Yerevan City. Yerevan City products also carry a small **📱 app** link that opens the iPhone app (decision 083); messages listing products should keep it.

## 5. Notifications

| Message | Sound |
|---|---|
| Deal alerts (price drop, new route, new cheap trip) | **on** — it's worth interrupting |
| Weekly digest, morning plan, Sunday week plan | silent |
| Replies to your own commands and button taps | silent (you're already looking) |
| System problems (job failed, scan blocked) | **on** |

While a search runs the bot shows "typing…"; button taps answer with a short toast.

### 5a. Who receives what (two people — decision 082)

The bot answers two chats: Davit's (`TELEGRAM_CHAT_ID`) and Karine's (`TELEGRAM_CHAT_ID_2`),
both Windows user environment variables, never in Git. Any other chat is ignored and logged.

| Message | Goes to |
|---|---|
| Replies, Home and section navigation, Price check prompt | the chat that asked |
| Results of `/price`, `/flights`, `/stays` (and Price check) | the chat that asked — the listener passes `TELEGRAM_REPLY_CHAT_ID` to the job |
| "Running…" acks, incl. 🧺 Basket / `/basket` | the chat that asked |
| Travel scan and digest, scheduled or via `/scan` / `/digest`; deal alerts | Davit only |
| System and failure messages (`telegram.notify`) | Davit only |
| **Family content** — daily plan (07:30), Sunday week plan, basket / shopping list | **both**, via `telegram.send_family()` (the basket job sends it itself; `basket` is not in `listener.REPLY_JOBS`) |

Each person gets the bottom keyboard on their own `/start`. No personal health data in
any message (tracking is light by the owner's choice). New features follow this table:
answers to a person go back to that person; family content uses `send_family()`.

### 5b. Basket (decision 084)

🛒 Shopping shows `🔍 Price check` · `🧺 Basket` (`cmd:basket`, weekly) and link buttons
`📋 Checklist` (the Shopping list Sheet, `shopping_sheet_id` in config_coach.json) and
`📄 Shopping plan`. `/basket [weekly|monthly|all]` is the typed shortcut. The result is one
silent message to both chats: header `🧺 Basket · weekly|monthly`, total and per-shop
totals, the month vs the budget, one-shop-only vs cheapest-of-each (items found at both
shops), then one fold per shop (Yerevan City first) and a "Not priced" fold, with a
`📋 Open checklist` link button. Each item line is the product link with the amount, line
cost and the 📱 app link for Yerevan City; product names are dropped before the message
would split (they stay in the Sheet).

### 5c. The plan in the bot (decision 085)

Today, Meals and Training are templated in code from the plan files (`coach/plan_view.py`
parses, `coach/plan_text.py` lays out) — no `claude -p`, no invented dish, exercise or
number, portions not calories. Ids are looked up in `plan/meals/dishes.md` and
`plan/training/exercises.md`; an unknown id is shown as the id with a note. The plan week
comes from `plan_start_local` in `config_coach.json` (Monday of week 1 = 2026-10-19) and the
Yerevan date (`lib.ui.now_local()`); a missing `plan/meals/week-NN.md` shows the latest week
file and says so; after week 12 training repeats weeks 9–12 and says so.

| Where | Content |
|---|---|
| 📅 Today / `/today` / 07:30 message | today's breakfast, lunch, dinner, prep for tomorrow, batch cooking on batch days; Davit's and Karine's session (time from `daily-rhythm.md`) or "no session today · walk", one habit nudge from `plan/habits.md`; each session folded (exercises, dose, 2–3 "how" cues, video); safety fold |
| 🍽 Meals | this week's menu, one fold per day (today marked), batch sessions, notes fold; at most one recipe reference per meal |
| 🏃 Training | both sessions with the block's how-to and warm-up line, cues and videos; safety fold |
| Sunday 18:00 message | next week's menu + "🏠 Home → 🛒 Shopping → 🧺 Basket" |

Messages stay one message (≤ 3900 characters): on the heaviest days cues drop from 3 to 2
(then 1) and Today leaves the block how-to to Training. Today is the compact form.

**Links — hard rule.** No URL is typed from memory or generated by a model. A URL appears
only if it is (a) a video in `plan/training/exercise-videos.md` with a Verified date,
written and re-checked by `jobs/exercise_videos.py`; (b) a `ref` in `plan/meals/dishes.md`
on an allowlisted site, opened and checked by hand before it was added; or (c) built in
code from a fixed template — `https://www.youtube.com/results?search_query=<name>+form+tutorial`
when an exercise has no stored video. Tested over every day of the plan. A video never
changes which exercise is shown. The day an exercise first appears in a person's 12-week
plan (computed from the plan files) it is marked *(new)* with one line: "watch the video
before your first set; start with the lightest option."

**Recipe allowlist** (free, stable; a ref on any other host is ignored):

| Site | Host |
|---|---|
| BBC Good Food | `www.bbcgoodfood.com` |
| Armenian Institute (food) | `www.armenianinstitute.org.uk` |
| The Armenian Kitchen | `thearmeniankitchen.com` |

A recipe link is for technique only — the dish, portions and family-meal rules stay ours.
Dishes without a ref get no link. Scoolinary is referenced by title only, never by URL.

**Wording and safety.** Plan text never uses the words patient, condition, disease,
illness, diagnosis or treatment (tested). Training and the 07:30 message carry one folded
line: stop and seek medical care for chest pain, fainting, severe breathlessness, dark
urine with muscle pain, yellowing of eyes or skin, or severe abdominal pain. No check-in,
no kcal or macros, no adherence prompts. Health briefs are not read here;
`coach.plan_text.today_extras()` is the hook for the one exception
(docs/briefs/HEALTH_RECORDS.md §6.2), and `ui.section()` passes it the asking chat.

**Schedule.** `jobs/coach_brief.py --morning` (07:30, `FamilyAssistant-Coach-Morning`) and
`--week` (Sunday 18:00, `FamilyAssistant-Coach-Week`), registered by
`scheduler/register-coach.ps1`; silent, both chats via `send_family()`. A morning message
that would arrive after 10:00 (week plan after 22:00) is dropped and logged to `Runs`; a
failure tells the owner and sends nothing to the family.

## 6. Bot profile

Set from `listener.set_menu()` at startup so it can't drift:
- **Description** (start screen) and **short description** (profile page) — §7 text.
- **Command list** — grouped, short: `menu`, `today`, `price`, `basket`, `flights`, `stays`, `scan`, `digest`,
  `status`, `cancel`, `help`.
- Profile photo: BotFather only (not settable by a bot).

## 7. Copy

- Description: *"Family assistant for meals, training, shopping prices and travel deals.
  Tap 🏠 Home to start, or 🔍 Price check to compare Parma and Yerevan City."*
- Short description: *"Meals, training, grocery prices and travel deals for the family."*

## 8. Later (not built)

- **Family group with topics** (Travel / Meals / Training / Shopping) so Karine sees the
  shared plan and lists; personal things stay in private chat. Needs the multi-chat
  change to `lib/telegram.py` (Phase 0).
- **Mini App** (a full screen inside Telegram, free on GitHub Pages) — only if the chat
  UI proves limiting.
