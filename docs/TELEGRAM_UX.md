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
 ├─ 🌍 Market     watch list, check now, add (§5d; /watch), 🇨🇳 China search (§5e; /china), 🛒 Amazon search (§5f; /amazon)
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

**Rich Messages** (decision 088): `lib/telegram.send_rich(cfg, rich_html, fallback_html,
buttons=…, chat_id=…)` sends `sendRichMessage` (Bot API 10.1+, `rich_message.html`) and, if
Telegram refuses it, the same content through `send_html()` as plain HTML with
`<blockquote expandable>` folds and an inline keyboard. Returns `("rich", message_id)`,
`("plain", None)` or `("failed", None)`. Rich HTML rules seen on the owner's iPhone
(2026-11-09): a newline is a space (use `<br>` / `<p>`); tables ≤ 4 columns; long parts in
`<details><summary>`; `<tg-slideshow>` for photos (HTTP(S) URLs); in-message buttons are
`<tg-button type="callback_data" data="…">` inside `<tg-button-row>` (`callback_data=` is
refused). Limits: 32,768 characters, 500 blocks, 50 media. Used by `/china` first; other
messages keep `send_html()`.

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
| `ui:<section>` | navigation: `ui:home`, `ui:today`, `ui:meals`, `ui:training`, `ui:shop`, `ui:market`, `ui:travel`, `ui:system` | new |
| `cmd:<action>` | run a menu action (`scan`, `digest`, `status`, `cancel`, `auto`, `basket`, `market`) | existing, kept |
| `mk:<action>` | Market watch actions (`mk:add` starts the add dialog) | new (decision 087) |
| `cn:<action>` | China search: `cn:ask` (prompt), `cn:only:<site>:<job>`, `cn:rev:<job>:<n>`, `cn:watch:<job>:<n>`, `cn:q:<job>:<q>:<option>` | new (decision 088) |
| `am:<action>` | Amazon search: `am:ask` (prompt), `am:q:<job>:<q>:<option>`, `am:watch:<job>:<n>` | new (decision 101) |
| `gl:<action>:<w\|m>` | Tick list: `gl:o` send, `gl:v` refresh, `gl:t:<w\|m>:<version>:<n>` tick item n, `gl:r` ask / `gl:R` clear every tick | new (decision 106) |
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

🛒 Shopping shows `🔍 Price check` · `🧺 Basket` (`cmd:basket`, weekly), `✅ Tick list`
(`gl:o:w`, §5g) and link buttons `📋 Checklist` (the Shopping list Sheet, `shopping_sheet_id`
in config_coach.json) and `📄 Shopping plan`. `/basket [weekly|monthly|all]` is the typed shortcut. The result is one
silent message to both chats: header `🧺 Basket · weekly|monthly`, total and per-shop
totals, the month vs the budget, one-shop-only vs cheapest-of-each (items found at both
shops), then one fold per shop (Yerevan City first) and a "Not priced" fold, with the buttons
`✅ Tick list` (`gl:o:w` / `gl:o:m`) and `📋 Sheet` (link). Each item line is the product link
with the amount, line cost and the 📱 app link for Yerevan City; a pick that is not simply the
cheapest has a second line `↳ <reason>` (decision 106: "Campagna is 2,000 ֏ less but not extra
virgin"); an item where nothing passed its quality rules is in "Not priced" with the reason.
Product names are dropped, then the 📱 links, before the message would split (both stay in the
Sheet, which also has a **Why** column).

### 5c. The plan in the bot (decision 085)

Today, Meals and Training are templated in code from the plan files (`coach/plan_view.py`
parses, `coach/plan_text.py` lays out) — no `claude -p`, no invented dish, exercise or
number, portions not calories. Ids are looked up in `plan/meals/dishes.md` and
`plan/training/exercises.md`; an unknown id is shown as the id with a note. The plan week
comes from `plan_start_local` in `config_coach.json` (Monday of week 1 = 2026-10-19) and the
Yerevan date (`lib.ui.now_local()`). Every plan week has a menu (decision 107): its
`plan/meals/week-NN.md` if one exists, week 1 for the trial weeks 2–4, otherwise a week built
by `coach/menu_gen.py` from the dish library — never another week's menu. A week that can't be
built shows one plain sentence ("This week's menu couldn't be put together from the dish
list. Davit has been told and will fix it.") and the scheduled job tells the owner. After week
12 training repeats weeks 9–12 and says so.

| Where | Content |
|---|---|
| 📅 Today / `/today` / 07:30 message | today's breakfast, lunch, dinner, prep for tomorrow, a 👶 line for the son and a 💡 tips line from the day's dishes, batch cooking on batch days (on Sunday: next week's Sunday batch); Davit's and Karine's session (time from `daily-rhythm.md`) or "no session today · walk", one habit nudge from `plan/habits.md`; each session folded (exercises, dose, 2–3 "how" cues, video); safety fold |
| 🍽 Meals | this week's menu: ✨ new dishes, batch cooking (with dates), one fold per day titled with the day's lunch and dinner (today marked), each meal with ✨ *new* and one `recipe` link per dish that has a ref, the 👶 and 💡 lines; an "Every day" fold (son, coffee, plate rule); the week's balance line counted in code ("fish 2× · legumes 4× · chicken or turkey 3× · eggs 4× · red meat 0×") |
| 🏃 Training | both sessions with the block's how-to and warm-up line, cues and videos; safety fold |
| Sunday 18:00 message | next week's menu as a **Rich Message** (`telegram.send_rich`): the same content with one `<details>` per day, and buttons 📱 Today · 🧺 Basket (Mini App, `?screen=today` / `?screen=basket`) when `miniapp_public_url` is set, else 🧺 Price the list at both shops (`cmd:basket`). The Meals-style HTML is the fallback. No file path, no "Home →" footer |

Messages stay one message (≤ 3900 characters): on the heaviest days cues drop from 3 to 2
(then 1) and Today leaves the block how-to to Training; menu folds drop the 💡 tips, then the
👶 line, then the recipe links (the Rich Message keeps all). Today is the compact form.

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
| The Mediterranean Dish | `www.themediterraneandish.com` |

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
`scheduler/register-coach.ps1`; silent, both chats (morning via `send_family()`, week as a Rich
Message per chat). `--owner-only` sends to the owner's chat only, for review. The generator's
warnings (a hand-edited week breaking a rule, fewer than 5 new dishes left) go to the owner. A morning message
that would arrive after 10:00 (week plan after 22:00) is dropped and logged to `Runs`; a
failure tells the owner and sends nothing to the family.

### 5d. Market watch (decision 087)

🌍 Market (Home, between Shopping and Travel) shows the watch list — number, name, stores,
the latest best total with its route and date, ⚖️ when a weight is missing — with
`🔄 Check now` (`cmd:market`, the nightly job run now), `➕ Add` (`mk:add`) and a
`📄 Watch list Sheet` link button once `config_market.json watch_sheet_id` is set.
Adding a link that is already on the list is refused ("Already on the list", decision 099).
Typed shortcuts: `/watch`, `/watch add`, `/watch bought|remove <n>`,
`/watch price <n> <amount> [store]`, `/watch weight <n> <kg> [LxWxH]`, `/watch check`.

**Add dialog** — four force-reply prompts headed `🌍 Market · add` (the listener routes an
answer to one into `/watch answer …`; a slash command typed as a reply is left alone):
1/4 name · 2/4 link(s), one per store, only stores in `market/stores.md` · 3/4 quantity ·
4/4 weight and box size (`2.4 kg 40x30x20`, or `skip`: the nightly run then takes them
from the Amazon page when it shows them, marked "page"). A rejected answer says why and
asks the same question again; `stop` ends it. China items without a weight get the fixed
Chinese seller message (code, not AI).

**Nightly report** (~01:30, silent, both chats via `send_family()`): header
`🌍 Market watch · <day>`, one line per item — best total in AMD with store, route and
arrival dates, `📉/📈 ±N% vs yesterday`, `⚠️` when that price was not re-read tonight,
"excl. store delivery" when the store's delivery cost is unknown — and the per-store
details folded: price in the store's currency, delivery to the warehouse, every forwarder
× mode (AMD/kg, chargeable kg, "(by volume)", total, days in the forwarder's own unit,
arrival dates), customs estimate (⚠️ within 10% of €200). Then one `🚫 <store> blocked
tonight` line per blocked store, and the footer: CBA rates with their date, tariff date,
customs rule. **Alerts with sound** (both chats): best total down ≥ 10% vs yesterday from a
fresh read, or back in stock. After 3 blocked nights in a row the owner alone gets one
message (open the link yourself or `/watch price`).

### 5e. China search (decision 088)

🌍 Market has `🇨🇳 China search` (`cn:ask`): a force-reply prompt "🇨🇳 China search · what are
you looking for?" whose answer becomes `/china <text>`. Typed: `/china <description>`,
`/china only pinduoduo|taobao|1688 <description>`, `/china last` (24 h), `/china cancel`.
Both chats, one shared queue (`china/queue.py`); the answer goes to the chat that asked.
The listener only queues: the plan, the browsing and the pricing run in
`jobs/china_search.py`, one job at a time, so other commands are never blocked.

Flow: a vague request gets 1–2 questions with buttons (`cn:q:…`, plus "➡️ Skip"); then
"⏳ Searching … (~N min)" (with the place in line if another search runs), one progress
line per site ("⏳ Pinduoduo done (1/3)…"), and one answer as a Rich Message (plain HTML
fallback): header, 🏆 best pick with its reason, sites that could not be read (🔑 logged
out / 🚫 check page / ⚠️ not read, each with a search link; Taobao is always 🔗 a search
link, decision 090; every search link uses the plan's short Chinese search words, never the
owner's sentence), brand guidance, Poizon hint for
clothes and shoes, restricted-goods warnings, one 4-column table per site, most trusted first (#, item, 🛡 trust = seller icon + score
from china/trust.py — seller, guarantees, reviews, rating, complaints, brand list and look-alikes
from config_china.json, photo reviews; total AMD; price orders only results of about the same
trust, decisions 092–093; `*` = weight not listed; `⚠️` = suspiciously cheap, far below the search's median
item price, never the 🏆 pick — decision 091; the 🏆 pick is the top of the trust order and its reason
lists the trust parts) and a `<details>` per result (variant, ¥ → AMD · USD,
China delivery, `⚠️ SHIPPING ESTIMATED FOR 1 KG — WEIGHT NOT LISTED`, every forwarder ×
mode with customs and total, seller class with its evidence, 🛡 the trust score with every part, specs, 👍/👎 reviews, the fixed
Chinese seller message, the product link built from its id). Buttons in the message:
`🔁 Only <site>`, `💬 Reviews N` (results whose reviews were not read), `👁 Watch N` (adds
the item to Market watch with today's price as the owner's price; a product already on the
list is not added again — "👁 Already on 🌍 Market watch", decision 099). Silent.

**Photo search (decision 095).** Send a photo (or an image as a file) with the caption
`/china`, `/china <note>` (e.g. `/china red, size 42`) or `/china only pinduoduo|taobao|1688
<note>` → "⏳ Searching China by your photo — 1688 by photo, Pinduoduo by the words in it, a
Taobao link… (~N min)" → the same progress lines and the same full answer, titled
"🇨🇳 China photo search · <item>", with a line "📷 <what the photo shows> · searched as
<Chinese words>". 1688 is searched with the photo itself (以图搜货); Pinduoduo's photo search
exists only in its app, so it is searched by the words read from the photo and says so;
Taobao stays a link (with those words) plus "📷 in the Taobao app, tap the camera in the
search bar to search by this photo". A photo **without** a `/china` caption is never
searched on its own: one question "📷 Search China for the item in this photo?" with
`🇨🇳 Search China` (`cn:ph:<id>`) / `✖ No` (`cn:phx:<id>`), valid 60 min
(`photo_ask_minutes`); a non-command caption is kept as the note. A photo with nothing to
buy gets "🤔 I don't see something to buy in this photo (…)". `🔁 Only <site>` on a photo
answer searches by the photo's words (the photo is deleted when the answer is sent;
`photo_keep_minutes` > 0 keeps it so 🔁 repeats the photo search). Health records, when
built, reads photos only inside an open `/health` conversation.

**When a search cannot run (decision 104).** The asker gets one plain line, with sound:
"⚠️ Your China search for “…” didn't start — please send it again." (the worker crashed before
it, or the job was stranded in the queue for more than 30 min with no worker) or "⚠️ Your China
search for “…” stopped before it finished — please send it again." (the worker died mid-job). The
owner gets the same line plus a "⚠️ SYSTEM:" reason; one message when the owner asked.

### 5f. Amazon search (decision 101)

🌍 Market has `🛒 Amazon search` (`am:ask`, next to 🇨🇳 China search): a force-reply prompt "🛒 Amazon
search · what are you looking for?" whose answer becomes `/amazon <text>`. Typed: `/amazon
<description>`, `/amazon only uk|de|it <description>`, `/amazon last` (24 h), `/amazon cancel`. Both
chats, one shared queue (`amazon/queue.py`), the answer goes to the chat that asked; the listener only
queues, `jobs/amazon_search.py` runs the job (one at a time).

Flow: clothing without an age/size gets ONE question with buttons (`am:q:…`, plus "➡️ Skip - search as
is"); the answer is added to the words and the plan is made again, so the German/Italian size words match.
Then "⏳ Searching Amazon UK, Amazon DE, Amazon IT for … (~5 min)", one progress line per store, one answer
as a Rich Message (plain HTML fallback): header, the translated words searched per store, 🏆 best pick
(seller line, total AMD, route, a one-sentence reason), stores that could not be read (🚫 check page - not
bypassed, kept out for 24 h / ⚙️ not set to the warehouse address / ⏳ in cool-down / ⚠️ not read, each with
a search link), "saw N results, read 3 in detail" per store, one table per store (#, item, seller icon +
class, total AMD; `*` = weight not listed; 📢 = sponsored) and a `<details>` per result (price → AMD · USD,
Amazon's delivery line to the warehouse - a "free on a first order" line is a condition and is NOT counted,
said so -, weight or `⚠️ SHIPPING ESTIMATED FOR 1 KG — WEIGHT NOT LISTED`, every forwarder × mode with
customs and total, seller evidence ("Sold by X · Dispatches from Amazon"), 🛡 trust with every part, link
built from the ASIN). Seller icons: 🟢 sold by Amazon, 🟡 dispatched by Amazon, 🟠 third party ships
itself, ⚪ not read. Buttons: `👁 Watch N` (adds the exact `/dp/` link to Market watch; a link already on
the list is not added again). No 📱 Open in app and no 💬 Reviews yet: the Mini App screen reads China's
answer (brief §4.1: it becomes the generic results screen in P1b). Silent. Limits in code: at most 10
searches a day, 3–6 s between pages, a store that shows a check page is skipped and not opened again for
24 h.

### 5g. Tick list (decision 106)

`/list` (this week) or `/list monthly`, 🛒 Shopping → `✅ Tick list`, or `✅ Tick list` under a basket
message. One silent message to the chat that asked: header `✅ Shopping list · this week` with the
week (`week 9 Nov – 15 Nov`) or the month, `N of M in the cart · last: Karine ticked Eggs 10:42`,
then the items grouped by aisle in walking order (Vegetables, Greens, Fruit, Dairy & eggs, Meat &
fish, Bread, Grains & legumes, Oils, cans & jars, Frozen, For this week's menu, Other) — `☐ <item>`
/ `✅ <s>item</s>`, the amount to buy and the shop dot from the last 🧺 Basket, the item name linking
to the product. **For this week's menu** holds what the week's dishes need that basket.md has no row
for (dishes.md `buy` words, e.g. `☐ Salmon · for Sheet-pan salmon`; not priced).
Buttons: one per item, two per row (`☐ Eggs` / `✅ Eggs`), then `🔄 Refresh` · `📦 Staples` (or
`🥬 This week`), then `♻️ New week` / `♻️ New month`, which first asks "Clear all N ticks on this
week's list?" with `Yes, clear the ticks` · `Cancel` (nothing ticked: says so, with `◀️ Back to the
list`). A tap ticks or unticks for the household and edits the list
message in **both** chats (the latest list message per chat is remembered); a button from an older
list (items changed since) redraws the list and says "tap the item once more". A new shopping week
(Saturday, Yerevan time — Saturday's shop is for the Sunday batch, so from Saturday the list is
next week's, labelled with that menu week) or month starts with nothing ticked. The Shopping list Sheet's boxes follow
each tick (one way). The Mini App shows the same list through `shopping/checklist.py`.

## 6. Bot profile

Set from `listener.set_menu()` at startup so it can't drift:
- **Description** (start screen) and **short description** (profile page) — §7 text.
- **Command list** — grouped, short: `menu`, `today`, `price`, `basket`, `watch`, `china`, `amazon`, `flights`, `stays`, `scan`,
  `digest`, `status`, `cancel`, `help`.
- Profile photo: BotFather only (not settable by a bot).
- **Chat menu button: 🏠 Family** (decision 094) — the button beside the message field opens
  the Mini App (docs/briefs/MINI_APP.md) inside Telegram. Set per chat for Davit and Karine by
  `python -m miniapp.setup_bot` (`--check` shows it, `--remove` puts back Telegram's default);
  `set_menu()` does not touch it. With it set, the command list is still there by typing `/`.
  The app opens on a Home list (Telegram's Settings pattern, decision 096): "Signed in as
  <name> · <role>", then one full-width row per section — icon, name, one-line description,
  chevron (Today · China · Market · Basket · Travel, "Coming soon" in step 0) — and a PC
  status card. No bottom tab bar: with five tabs the outer icons sat in the phone's rounded
  corners. A row opens its screen; Telegram's back button returns Home. Since decision 098 every
  row is a real screen: **Today** (Today · Meals · Training · Week tabs), **China** (a search form
  above the results), **Market** (list, ✅ Bought, 🗑 Remove, add by link, 🔄 Check now),
  **Basket** (last priced list by shop, 🧺 price it again, Price check) and **Travel** (cheapest
  trips and stays, Scan now, Send digest, Search flights, Search stays). Buttons that start a bot
  job queue the matching chat command for the listener; its answer arrives in the chat, as if
  typed. Icons avoid flag
  emoji (Windows shows 🇨🇳 as "CN"; China is 🏮). Decision 105 (improvement pass): the screen's one
  main action sits in **Telegram's bottom button** (MainButton) — 🔎 Search on China once there are
  3 characters, ➕ Add on Market once name and link are filled, 🧺 Price the list now on Basket — and
  an in-page button stands in on a client without it; actions whose result goes to the whole family
  (Basket, Check prices now) ask first in a native popup; a half-typed form asks before closing; every
  field has a visible label; your **tab choices are remembered** (Today tab, Basket weekly/monthly,
  China site and order; small UI choices only, in Telegram CloudStorage); China cards can be shown
  most-trusted-first or cheapest-delivered-first and filtered by site, and tapping the 🏆 pick jumps to
  its card; Travel says how old its data is ("15 days old — Search stays for fresh prices"); today's
  day starts open in Meals; Telegram's header takes the app's colour; Home offers "Add to home screen"
  once where the client supports it. Decision 108 (stage B): **Today** shows today's meals with recipe
  links, the batch session and training on top and this week's whole menu under it (days folded, today's
  open; the son's and tip lines and every recipe link, which the one-message chat texts have to drop);
  **Next week** is the Sunday menu; **Training** as before. **Basket** opens on the **shared tick list**,
  the same state as `/list`: tap a row to tick it for both of you (the name and time of who ticked show,
  the other person's ticks arrive within 15 s), ⓘ shows the shop, the product and why that pick, ♻️ New
  week asks first; a tick also edits both chats' list messages and the Sheet's box, as a tap in the chat
  does. Prices and "Price the list now" are below it. It follows Telegram's light/dark theme. Anyone
  else sees "This app is private"; a PC that stops answering shows "PC is not reachable"
  with Try again; a window left open for more than 24 h shows "Session expired" with Close
  (decision 099 — it used to say "private" to the owner).
- **📱 Open in app** (decision 097) — first button row on every `/china` answer (rich and
  plain). Opens the app straight on the China screen (`?screen=china`): the latest result as
  cards in the chat's numbering — 🏆 pick, price, delivered total, warnings, a Details fold
  (routes, weight, trust parts, specs, reviews read, "ask the seller" text to copy) and per
  card the delivered total first and the item price under it (decision 099), **Open on <site>**, **👁 Watch**, **💬 Reviews** (the reviews answer arrives in the
  chat). Same numbers as the chat: the PC builds them with the report helpers.

## 7. Copy

- Description: *"Family assistant for meals, training, shopping prices and travel deals.
  Tap 🏠 Home to start, or 🔍 Price check to compare Parma and Yerevan City."*
- Short description: *"Meals, training, grocery prices and travel deals for the family."*

## 8. Later (not built)

- **Family group with topics** (Travel / Meals / Training / Shopping) so Karine sees the
  shared plan and lists; personal things stay in private chat. Needs the multi-chat
  change to `lib/telegram.py` (Phase 0).
- **Mini App screens** — step 0 (empty, secure shell) is built: §6 🏠 Family. Screens follow
  one per session (docs/ROADMAP.md), China results first.
