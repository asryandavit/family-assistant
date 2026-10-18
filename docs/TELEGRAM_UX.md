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
 ├─ 📅 Today      today's meals + sessions          (until the daily-plan job exists:
 ├─ 🍽 Meals      week menu, dishes, food rules       links to the plan docs in Drive)
 ├─ 🏃 Training   per-person plans, exercise library
 ├─ 🛒 Shopping   price check, shopping list, basket (when built)
 ├─ ✈️ Travel     scan, digest, flights/stays how-to, automation
 └─ ⚙️ System     status, automation, cancel, help
```

- **Home** opens with `/start`, `/menu` or the 🏠 Home key. Section taps **edit the same
  message** (no new message per tap) and every section has `⬅️ Home`.
- **Slash commands keep working** for everything (`/price`, `/flights`, `/stays`, `/scan`…).
  They're shortcuts; nobody has to remember them.
- **🔍 Price check** asks "Which product?" with a reply prompt; the answer runs `/price`.
- A feature that isn't built yet does not get a button. Today/Meals/Training link to the
  Drive plan docs until the daily-plan job replaces those links with live content.

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
| `cmd:<action>` | run a menu action (`scan`, `digest`, `status`, `cancel`, `auto`) | existing, kept |
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
| Travel scan and digest, scheduled or via `/scan` / `/digest`; deal alerts | Davit only |
| System and failure messages (`telegram.notify`) | Davit only |
| **Family content** — daily plan (07:30), Sunday week plan, basket / shopping list | **both**, via `telegram.send_family()` |

Each person gets the bottom keyboard on their own `/start`. No personal health data in
any message (tracking is light by the owner's choice). New features follow this table:
answers to a person go back to that person; family content uses `send_family()`.

## 6. Bot profile

Set from `listener.set_menu()` at startup so it can't drift:
- **Description** (start screen) and **short description** (profile page) — §7 text.
- **Command list** — grouped, short: `menu`, `price`, `flights`, `stays`, `scan`, `digest`,
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
