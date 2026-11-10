# CHINA_SEARCH.md — `/china` search on Pinduoduo, Taobao/Tmall and 1688

Status: **brief approved by the owner 2026-11-09 ("go ahead"; Davit and Karine share one Chrome
session, one queue, the same features). P0 done (§8, decision 088); P1 built (§9, decision 090) — Pinduoduo and 1688 automatic, Taobao a search link. P2 photo search built (§10, decision 095) — 1688 by photo, Pinduoduo by the photo's words, Taobao a link.** Builds on Market watch (decisions 086–087): forwarder
tariffs, customs, CBA rates, working-day arrivals and the report helpers in `market/` are
reused, not rewritten.

---

## 1. What it does

`/china <description>` from Davit's or Karine's chat. The bot searches **Pinduoduo,
Taobao/Tmall and 1688** in the **owner's own Chrome** (where he is logged in), reads the
listings, product pages and reviews, and answers the chat that asked with the top results
priced all the way to Yerevan: item price of the matching variant in ¥ → AMD and USD,
China domestic delivery, shipping per forwarder × mode, customs. Each result says who the
seller is (official / authorised / reseller / factory), what buyers liked and complained
about, and why it is (or isn't) the pick.

**Poizon (得物) is skipped** (app-only). For clothes, shoes and sneakers the answer adds one
line: "👟 Also check Poizon on your phone — it has authenticated sneakers and clothes."

## 2. What the bot never does

Claude in Chrome only **searches and reads**. It never logs in, never types a password or
an SMS code, never adds to cart, never buys, never messages a seller, never solves a
CAPTCHA, slider or any bot check. A login page or a check stops that site for the run and
the owner is told ("🔑 Taobao logged out — open Chrome on the PC and sign in"). This is the
same rule as Market watch (decision 086): no stealth, no solvers, no proxies.

Enforced in code, not only in the prompt (§4.3): the `claude -p` run gets an **allow-list of
browser tools**; typing tools are not on it.

## 3. The agreed spec (owner, 2026-11-09)

| # | Topic | Agreed |
|---|---|---|
| 1 | Who | Both chats; the answer goes to the chat that asked |
| 2 | Sites | Pinduoduo, Taobao/Tmall, 1688. Poizon skipped (+ phone hint for clothes/shoes) |
| 3 | Where it runs | Owner's real Chrome via the Claude in Chrome extension (option a) |
| 4 | Vague request | Bot first asks 1–2 quick questions with buttons (budget, size, colour, brand only?) |
| 5 | Price | The **variant matching the description**, not the cheapest SKU; PDD group (拼单) and single (单独购买) prices kept apart; ¥ → AMD and USD at the CBA rate |
| 6 | Delivery | China domestic delivery if not free; China → Yerevan per forwarder × mode (Onex air/sea, Globbing air/sea, BuyForYou air, EasyTrans truck) from stored tariffs; customs if over €200 |
| 7 | No weight | Computed for 1 kg and said in UPPERCASE: `⚠️ SHIPPING ESTIMATED FOR 1 KG — WEIGHT NOT LISTED`; if it likely weighs more: `⚠️ PROBABLY OVER 1 KG`. A ready Chinese message to ask the seller weight / size / EU plug |
| 8 | Why this one | Brand guidance (which brand is better, look-alike brands flagged), key specs (wattage, EU plug, GaN…), clothes: **material composition**, size table + "runs small/large" from reviews |
| 9 | Reviews | Per link 2–3 liked points, 2–3 complaints, review count. **Option B**: reviews read for the **top 3 per site** (9 links); the rest get a `💬 Reviews` button |
| 10 | Official vs not | Every seller marked: official flagship (官方旗舰店) · brand-authorised (品牌授权) · reseller · factory (1688 源头工厂 / 实力商家) · unmarked. Plus **manufacturer / official dealer lookup** ("Grohe official store or dealer"): official store and authorised dealers first, factories listed apart with a warning that a factory selling a brand name is not official unless marked; shop links and how to contact them (the bot never contacts them) |
| 11 | Ranking | Trust marks, sales volume, returns shown. **Top 5 per site by total delivered price**, one 🏆 best pick with its reason; the same product on several sites side by side; forwarder restrictions flagged (power banks / batteries, liquids, magnets, aerosols); customs check for several items in one parcel |
| 12 | After a result | Buttons `🔁 Only Pinduoduo` / `Only Taobao` / `Only 1688` (typed: `/china only taobao <description>`); `👁 Watch` adds the item to the Market watch list; `/china last` shows the last results (kept 24 h) |
| 13 | Progress | "⏳ Pinduoduo done (1/3)…" messages; **one Chrome job at a time**, one queue for both users and the login check; a second request waits and is told its place |
| 14 | Photo search | Photo with a caption → image search → the same full answer. Own phase. **Built as P2 (owner, 2026-11-10; §10, decision 095)**: 1688 by photo; Pinduoduo's and Taobao's photo search are app-only / blocked, so Pinduoduo is searched by the words read from the photo and Taobao is a link + app tip |
| 15 | Keep logged in | At Windows logon Chrome opens with the three sites in tabs (plain Chrome, script under `scheduler/`). **Daily login check 09:00** through the same queue; logged out / Chrome closed / extension disconnected → both chats: "🔑 Taobao logged out — open Chrome on the PC and sign in" |

## 4. Architecture

### 4.1 Headless trigger — verified 2026-11-09 (before this brief, read-only probes)

The listener can drive the owner's Chrome without anyone at the keyboard:

```
claude -p --chrome --output-format json \
       --allowedTools "mcp__claude-in-chrome__<read tools>" --disallowedTools "Bash,Edit,Write"
```

- Runs on the owner's **Max subscription** (`ANTHROPIC_API_KEY` unset in the child env —
  `lib/claude.py` already runs `claude -p` this way; `selfcheck.py` warns if the key is set).
- `list_connected_browsers` showed **two** browsers on the account (Windows PC and a Mac).
  The run must pick the **Windows** one explicitly (`select_browser` by platform; the
  device id is stored in `machine.json`, gitignored) — otherwise nothing is returned.
- Probe: one Pinduoduo search (`mobile.yangkeduo.com/search_result.html?search_key=…`,
  "氮化镓充电器 65W") read headlessly in **49 s**, 20 listings, no login wall: titles,
  `券后` coupon prices, `本店已拼` / `全店总售` sales, `品牌授权`, `正品险` marks.
- Each `claude -p --chrome` call loads the Chrome tool definitions (~72k tokens of cache
  creation; the CLI reported a list-price equivalent of ~$0.55–0.60 per small call). On Max
  this is quota, not money, but a full `/china` (3 searches + 9 product pages with reviews)
  is a noticeable share of a 5-hour window. P0 measures a full run; the brief's ~6 min
  estimate is checked there.
- Taobao needed the extension's **per-site permission click** on 2026-11-09. Whether a
  headless run can trigger that prompt (and hang) is a P0 question; the answer decides
  whether the 09:00 check must also verify site permissions.

### 4.2 Flow

```
/china <text>  (listener, either chat)
  → china/bot.py: parse ("only <site>", "last", photo), vague? → 1–2 button questions
  → china/queue.py: append job to the single file queue, reply "⏳ queued (2nd)" if busy
  → jobs/china_search.py (one worker; a lock file guarantees one Chrome job at a time)
      per site:  claude -p --chrome  prompt prompts/china_site.md  → JSON
                 → china/validate.py  (schema, allow-lists; reject → re-ask once → site
                    marked "not read", never a partial result)
                 → progress message "⏳ Pinduoduo done (1/3)"
  → china/pricing.py  (Python: parse ¥ strings, pick group/single, domestic delivery,
                       market.shipping per forwarder × mode, market.customs, market.rates)
  → china/report.py   (template, folds, buttons)  → the asking chat
  → .browser/china_data/last_<chat>.json (24 h)   — saved after the message is sent
```

### 4.3 Numbers are code (CLAUDE.md §2)

The model **transcribes and classifies**; Python **computes**.

| The model returns | Python does |
|---|---|
| Price **as shown** (`"券后¥109"`, `"¥45.79"`, `"拼单¥39.9 / 单独购买¥45"`) and the SKU label it matched | parses the ¥ amount, keeps group and single apart, rejects anything unparsable |
| Domestic delivery text (`"包邮"`, `"运费¥8"`) | free / amount / unknown (unknown is shown as unknown, never as free) |
| Weight / size text from the spec table, if any | `market.readers.parse_weight_kg` / `parse_dims_cm`; none → 1 kg + the UPPERCASE warning |
| `likely_over_1kg: true/false` + a one-line reason | shows `⚠️ PROBABLY OVER 1 KG`; never changes the computed number |
| Sales and review count **as shown** (`"全店总售523万+"`) | parses to a number (万 = 10,000) for sorting |
| Seller class from an enum + the **raw mark text** as evidence | checks the evidence actually contains a mark of that class (官方旗舰店 / 旗舰店 / 品牌授权 / 源头工厂 / 实力商家…); otherwise downgraded to "unmarked" |
| Restriction flags from an enum (`battery`, `liquid`, `magnet`, `aerosol`) | looks up each forwarder's rule (data row in `market/forwarders.md`) |
| English title, liked / complaints, brand note, size advice, material composition (as shown) | lays them out; no number from these lines is used in any calculation |

Totals, ¥→AMD/USD, shipping, customs (single item and several items in one parcel), the
sort by total delivered price and the 🏆 pick's price comparison are all Python, unit-tested
on fixtures captured in P0. The 🏆 **reason** is words from the model, chosen among the top
results Python already ranked (an id outside that list is rejected).

The seller message is a **fixed Chinese template in code** (extends the one in
`market/bot.py`): weight, box size, and for electrics "is there an EU plug (欧标插头)?".

### 4.4 Queue and Chrome jobs

- One file queue in `.browser/china_data/queue/`, one worker process at a time
  (lock file with the worker's pid; a stale lock from a dead pid is cleared and reported).
- Jobs: `search`, `reviews` (the 💬 button), `photo`, `login_check`. FIFO; a waiting user is
  told their place; `/cancel` removes their own job.
- Time limit per site (default 6 min); a timeout marks that site "not read" and moves on.
- The worker never holds anything else open: no Sheets write, no database transaction
  while `claude -p` runs (CLAUDE.md §3 spirit — this feature keeps state in JSON files).

### 4.5 Keeping the sites open

- `scheduler/register-china.ps1`: at logon, start Chrome with the three sites in tabs; a
  09:00 daily `jobs/china_search.py --login-check` (queued like any job).
- The check opens each site's "my account" page read-only and looks for the logged-in
  marker found in P0. Logged out, check page, Chrome closed or extension disconnected →
  one message to **both** chats (the family can't search until the owner fixes it).
- Platform calls stay in `scheduler/` (CLAUDE.md §6).

## 5. Telegram (plugs into TELEGRAM_UX.md, no new top-level menu)

- 🌍 Market section gets a `🇨🇳 China search` button (prompt "What are you looking for?").
- Typed: `/china <description>`, `/china only pinduoduo|taobao|1688 <description>`,
  `/china last`, a photo with caption `/china …` (photo phase).
- New callback prefix `cn:` (`cn:only:<site>:<job>`, `cn:rev:<job>:<n>`, `cn:watch:<job>:<n>`,
  `cn:q:<answer>` for the vague-request questions). Old buttons keep working.
- Replies to the asking chat, silent; the 🔑 login problem is with sound to both chats.

### 5.1 Rich Messages from day one (owner, 2026-11-09)

Results are sent as a Telegram **Rich Message** (`sendRichMessage`, Bot API 10.1 of
2026-06-11; tables and media 10.2; in-message buttons, compact tables and expandable
quotes 10.3 of 2026-08-24 — read on core.telegram.org/bots/api 2026-11-09):

- `InputRichMessage.html` (exactly one of `html` / `markdown` / `blocks`): `<table compact>`
  for the top 5 per site (site · seller mark · total AMD · USD · cheapest route), one
  `<details><summary>` per site and per result for the long parts (every forwarder × mode,
  reviews, specs, seller message), `<tg-slideshow>` of product photos (HTTP(S) URLs only;
  a media element is its own block), `<tg-button>` rows for 🔁 / 💬 / 👁 (callback_data).
- Limits checked in code before sending: ≤ 32,768 characters, ≤ 500 blocks (rows, list
  items and details count), ≤ 16 nesting levels, ≤ 50 media, ≤ 20 table columns.
- Edited with `editMessageText(rich_message=…)` (e.g. progress → final result);
  `reply_markup` inline keyboards remain available.
- **Fallback**: if `sendRichMessage` fails (error, older client report, limit hit) the same
  result goes out through today's `send()` as plain HTML with `<blockquote expandable>`
  folds (TELEGRAM_UX.md §2). Never no answer.
- The new send helper in `lib/telegram.py` (`send_rich(html, chat_id, buttons=None)`) is its
  **own additive commit** with the regression check (CLAUDE.md §1); existing `send()` is
  untouched.
- P0 sends one real rich test message to the owner's chat (with his OK) and saves the
  returned `Message` JSON to `tests/fixtures/china/telegram_rich_sent.json` before any
  code relies on the format; the owner says how it renders on his iPhone and Karine's
  phone.

Result layout (illustrative — numbers below are placeholders, not computed; in the rich
version the numbered lines are a table and the folds are `<details>`):

```
🇨🇳 China search · GaN charger 65W, EU plug
<i>3 sites · top 5 each by total to Yerevan · CBA 9 Nov</i>
━━━━━━━━━━━━
🏆 Ugreen 65W GaN (Pinduoduo, ✅ brand-authorised) — <total> AMD (<usd>) via <route>
   Why: <reason>
1. … one line per result: site · seller mark · total AMD · cheapest route
▸ Pinduoduo (fold): per result — title (EN), variant, ¥ group / single → AMD · USD,
  domestic delivery, every forwarder × mode, customs, ⚠️ weight line, specs,
  👍 liked / 👎 complaints (n reviews), size advice, link, seller message
▸ Taobao (fold) · ▸ 1688 (fold) · ▸ Same product on several sites (fold)
━━━━━━━━━━━━
⚠️ Battery item: Onex/Globbing air may refuse — check before ordering
[🔁 Only Pinduoduo] [🔁 Only Taobao] [🔁 Only 1688]
[💬 Reviews 4] [💬 Reviews 5] … [👁 Watch 1] …
```

## 6. Phases (one per session, CLAUDE.md §9)

| Phase | Content | Done when |
|---|---|---|
| **P0 Discovery** | In the owner's Chrome (he clicks the extension's per-site "Allow"), capture to `tests/fixtures/china/`, per site: a search result page, a product page with variants (SKU prices; PDD group vs single), the reviews section, shop / official marks (官方旗舰店, 品牌授权, 源头工厂, 实力商家), the logged-in marker, a login/check page if one appears, and the image-search entry point. Repeat one search **headlessly** (`claude -p --chrome`) per site and time a full 3-site + 9-review run. Send one Rich Message test (§5.1) and capture the response | A table: site → what is readable, the field names, time and quota per run, whether headless needs a permission click; the rich test renders on both phones |
| **P1 Text search** | `china/` (bot, queue, validate, pricing, report), `prompts/china_site.md`, `jobs/china_search.py`; vague-request buttons; reviews for top 3 per site; seller classes + official/dealer lookup; restrictions; parcel customs; progress messages; `💬 Reviews`, `🔁 Only <site>`, `👁 Watch`, `/china last`. `listener.py` / `lib/ui.py` changes in their own additive commits | A real `/china` from both phones answered with all three sites; tests green |
| **P2 Photo search** (was P3; the owner moved it first, 2026-11-10 — "China P2") | Photo + `/china` caption (or a yes to "Search China?") → 1688 image search with the extension's `file_upload`; Pinduoduo by the words read from the photo (its photo search is app-only); Taobao link + app tip → the same answer. **Built, §10, decision 095** | A photo of a real item from the owner's phone answered end to end |
| **P3 Keep logged in** (was P2) | Logon script with the three tabs, 09:00 login check through the queue, both-chat 🔑 message, staleness line at listener startup | Logging out of one site produces the 🔑 message at the next check |
| **Mini App (built: Mini App step 1, decision 097)** | China screen in the 🏠 Family app, opened from Home or the **📱 Open in app** button now on every answer (`report.buttons(app_url=…)`, a `web_app` `<tg-button>`); reads the saved `last_<chat>.json`; 👁 Watch / 💬 Reviews go through `china.bot.callback`. Still open: **photos** (results carry no image ids — the extraction would need to keep per-site image ids and build CDN URLs in code), sort, filters | `docs/briefs/MINI_APP.md` §12 |

Each phase ends with a decision entry (088+), a doc update and a phone demo.

## 7. Open questions for the owner

1. **Quota**: a full `/china` costs a noticeable share of the Max 5-hour window (§4.1). OK,
   or should reviews for the top 3 be on a button too (fewer calls)?
2. **Mac browser**: the extension is also connected on a Mac. The bot will always pick the
   Windows PC — confirm.
3. **Karine's searches** run in your Chrome on the PC while you may be using it (tabs open
   in their own group and close at the end). OK?
4. **Exchange to USD**: CBA AMD/USD rate (same source as AMD) — OK?
5. **Rich test message** in P0: OK to send one test Rich Message from the bot to your chat
   (and Karine's, to see it on her phone)?

## 8. P0 results so far (2026-11-09)

Captured in the owner's Chrome through the extension, logged in. Fixtures in
`tests/fixtures/china/` (other buyers' and reviewers' names and the account name are never
stored). Search used for every site: "氮化镓充电器 65W".

### What each site gives

| Site | Search | Product page | Reviews | Seller / official marks | Weight |
|---|---|---|---|---|---|
| **Pinduoduo** (`mobile.yangkeduo.com`) | **Structured JSON** in `window.rawData…ssrListData.list` (20 per page): `goodsID`, `goodsName`, `price` (fen, before coupon), `priceInfo` + `pricePrefixInfo` (`券后` / `限1件` / `新客`), `salesTip`, `tagList` (`绿联·品牌授权`, `正品险`, `假一赔十`, `退货包运费`…) → `pdd_search_gan65w.json` | No JSON (client-rendered); text: shop name (`绿联UGREEN赛文斯专卖店`), `品牌授权`, guarantees, spec block (brand, 3C number, ports, protocol). **Variant prices only in the picker** opened by `发起拼单` (selecting an option changes `券后¥… 券前¥…`; nothing is confirmed) → `pdd_goods_796316919192.json` | `goods_comments.html?goods_id=` readable: total `全部(2321)`, tag counts, each review with its **variant** (`型号：100W…`) → `pdd_comments_…json`. No negative-review filter on the web | `品牌授权` tag, `专卖店` / `旗舰店` in the shop name | not listed |
| **Taobao / Tmall** (`s.taobao.com`) | Readable as card text (37 per page): title, chips, price split `¥|109|.34` + label (`券后价`/`补贴价`/`首单价`), `N+人付款`, origin, shop name last, `品牌旗舰` chip → `taobao_search_gan65w.json` | **Degraded after ~6 automated reads in a few minutes**: `访问异常提示 — 系统检测到当前访问存在异常…` — details/specs/reviews hidden, price + shop rating + variant names still shown → `tmall_item_…_anomaly.json`. Not bypassed; Taobao paused | not reached (hidden by the notice) | shop name: `品胜官方旗舰店` **vs** `品胜快充旗舰店` (look-alike "flagship" that is not the official one), `专卖店`, `直销店`, `港澳直营店`, `天天特卖工厂` | not reached |
| **1688** (`s.1688.com`) | Served in its **international English/USD form** to this account (`AM-English-USD`): card = machine-translated English title + `¥price` only — **no supplier, no factory marks, no MOQ, no sales** → `1688_search_gan.json` | Rich: supplier company (`深圳市同长盛电子有限公司`, `入驻15年`, `四星供应链`, quality/fulfilment/repeat rates), `Factory direct supply`, attributes incl. `是否原装: 否` and `插头标准: 英标`, variants (EU adapter…), quantity price tiers → `1688_offer_735345997702.json` | rating + one review on the page; full reviews not yet opened | supplier tier text; `Factory direct supply` badge | **per-variant weight table (g)** — but sizes labelled cm are mm (180 g, "197 L") |

### Findings that change the plan

1. **Listing price ≠ the described variant** (confirmed): PDD shows ¥109 for a "100W" title;
   that is the 45W variant — 100W is ¥189 after coupon (¥229 before). P1 must open the
   picker for the top results; the listing price is only a sort hint.
2. **PDD mobile web has no 单独购买 (single-buy) price** — only 发起拼单 (group). The result
   says "group price; single price only in the app".
3. **Taobao reacts to automated reading within minutes** (soft notice, not a CAPTCHA). The
   per-run budget for Taobao must be small and slow (P1: search + ≤ 3 product pages, spaced),
   and the notice is detected and reported like a check page.
4. **1688 international form hides the trust marks** on search cards; the offer page has
   them. Whether the Chinese form (with 源头工厂 / 实力商家 on cards) can be shown is a
   language/site preference in the owner's account — not changed by the bot; owner's call.
5. **1688 delivery is quoted to Yerevan** (the account's address), not to a forwarder's
   China warehouse: it is not the China domestic delivery the maths needs → "unknown".
6. **Look-alike flagships are real** (`品胜官方旗舰店` vs `品胜快充旗舰店`): seller class is
   decided in code from the shop name (`官方旗舰店` only = official), not from `旗舰店`.
7. **Taobao's brand chip is the compatible device** (`Apple/苹果` on Pisen/Anker cards),
   not the maker — never used as the brand.
8. **Extension limits that shape the design**: page-JS results are capped at ~1,000
   characters (read in chunks, or use `get_page_text`); URLs with query strings and
   base64 are blocked in tool output (product links are rebuilt in code from ids:
   `goods.html?goods_id=`, `item.taobao.com/item.htm?id=`, `detail.1688.com/offer/<id>.html`);
   a batched action on a new site can fail with `permission_required` (needs a standalone
   call so the owner is prompted) — a headless run must treat that as "site not permitted".
9. **Rich Message** test sent (2 copies; the first save crashed): `sendRichMessage` returns
   the parsed `rich_message.blocks` (`paragraph`, `table` with cells/`is_header`/`align`,
   `details`, `slideshow` of photos with sizes, `buttons`) → `telegram_rich_sent.json`.
   Button attribute is `data=`, not `callback_data=` (the latter returns
   `BUTTON_DATA_INVALID`). A newline in `html` becomes a space — use `<br>` or blocks.

### Rich Message on the owner's iPhone (screenshots, 2026-11-09 17:05)

Renders as designed: bordered striped table with caption and a header row (4 columns fit
the phone width; long cells wrap to 2–3 lines), the `<details>` row shows collapsed with a
chevron, the slideshow swipes (page dots, caption under it), the two in-message buttons
show as a row (primary style blue; URL button with ↗). Confirmed rules for P1:
- Title and subtitle ran into one paragraph (`
` → space): use `<br>` or separate blocks.
- Phone table: **≤ 4 columns**, short cell text (site · total AMD · route; details go in
  the `<details>` fold).
- Plain-HTML fallback stays for Karine's phone / older clients until seen there.

### Full headless run (2026-11-09 17:11–17:31)

One `claude -p --chrome` call per site, in sequence, same rules prompt (read-only, stop on
login/check), top 3 per site with product page and reviews. Prompts and the model's JSON
answers: `tests/fixtures/china/headless_*`.

| Site | Time | Turns | Tokens (cache read / created / output) | List-price equivalent | Result |
|---|---|---|---|---|---|
| Pinduoduo | **4.0 min** | 42 | 2.02 M / 85 k / 11.5 k | ~$1.32 | **ok, no prompt**: search, 3 product pages with the picker (EU-plug variants found: `多头版(配中/英/欧/美规四种插头)` ¥159 after coupon), 3 review pages (274–640 reviews; liked / complaints in English, e.g. "gets hot during fast charging", "bulkier than a normal 65W") |
| Taobao | 10.5 min | 32 | 1.43 M / 73 k / 9.8 k | ~$1.07 | **failed**: search page read (27 of 39 cards), then every `javascript_tool` and the navigation to `item.taobao.com` waited on the extension's **per-action permission prompt** and timed out — "Site-level permissions are disabled for this site", so it asks on every action and cannot be allowed once. No product page read |
| 1688 | **4.5 min** | 45 | 1.75 M / 85 k / 14.6 k | ~$1.33 | **ok, no prompt**: supplier company, variants, **weight row** (72–100 g; one table again in mm), one attribute mismatch caught (title 65W, attributes 25W / British plug). Prices on detail pages in **USD** (international mode); no factory badges on these 3 |

What this means:

1. **Headless works unattended for Pinduoduo and 1688**: ~4–4.5 min per site for search +
   3 products + reviews.
2. **Taobao cannot run unattended through the extension**: it requires a human click on
   every action (site-level allow is disabled for it — a setting of the extension, not
   ours to change). Options for the owner:
   (a) Taobao through the bot's own browser profile (Playwright, owner signs in once —
   decision 086 #5), reading only, slowly; it may still hit `访问异常`, which is then
   reported, not bypassed; (b) no Taobao reading: the answer carries a Taobao search link
   built in code; (c) Taobao only when the owner is at the PC to click Allow (not
   automatic). Recommended: try (a) in P1's first step, fall back to (b).
3. **Quota**: a two-site run is ~3.8 M cache-read tokens and ~$2.65 list-price equivalent
   (three sites would be ~$3.7). On Max this is quota, not money, but several searches a
   day are a large share of a 5-hour window. P1 cuts it: fixed extraction scripts (the
   model calls them instead of exploring), a cheaper model for browsing (`--model`), one
   call per site, reviews for top 3 only on PDD/1688.
4. **The model's JSON needs the validator in §4.3**: price fields were sometimes null with
   the price elsewhere ("限时价 ¥159" moved to a note), `首件¥89.9` is a first-item price,
   1688 prices came in USD, and 1688 weight tables mix mm and cm.

### Owner's answers (2026-11-09, "do it with the best recommended ways")

- **Taobao**: option (a) — read Taobao in the bot's own browser profile (Playwright, the
  owner signs in once himself; reading only, slow: search + ≤ 3 product pages, spaced).
  If it shows a check / `访问异常` / login, the answer says so and falls back to (b): a
  Taobao search link built in code. Never bypassed.
- **Pinduoduo and 1688**: headless `claude -p --chrome` in the owner's Chrome (works
  unattended, P0).
- **1688 language**: stays as the account has it (English/USD); seller class comes from the
  offer page (supplier company, tier, badges), not the search card. ¥ vs USD read from the
  page and converted by code.
- **Quota**: fixed extraction scripts in the prompt (the model runs them instead of
  exploring), a cheaper model for browsing, one call per site, reviews for the top 3 on
  PDD and 1688. P1 measures and reports usage per `/china`.
- Windows browser always; Davit and Karine share the session and queue; CBA rate for USD.

### Still open

- Image-search entry points — found in P2 (§10): 1688 only.

## 9. P1 results (2026-11-09, decision 090)

### Built

| Part | Files | Proven by |
|---|---|---|
| Parsers (prices, counts, weights, mm/cm, seller class, promo, restrictions, links from ids) | `china/parse.py` | `tests/test_china_parse.py` on the P0 captures |
| Answer contract, whole-answer rejection, prose trimming, JSON extraction | `china/validate.py` | `tests/test_china_validate.py` |
| Money: ¥/$ → AMD/USD, China delivery, forwarder × mode, customs, 1 kg rule, ranking, trust-first ranking and 🏆 pick (`china/trust.py`, decisions 092–093: seller, guarantees, store age, certificates, sales, reviews, rating, complaint kinds, spec mismatch, brand list and look-alikes, variant of the reviews, photo reviews; suspiciously cheap never picked, decision 091), same product, parcel customs | `china/pricing.py`, `china/trust.py`, `config_china.json` | `tests/test_china_pricing.py` (hand-checked totals on `market/tariffs.json` and a fixed CBA rate set), `tests/test_china_trust.py` |
| Rich answer + plain fallback, buttons | `china/report.py`, `lib/telegram.send_rich` | `tests/test_china_report.py`, `tests/test_telegram_rich.py` |
| `claude -p` calls (plan, site, Taobao text, reviews), repair re-ask | `china/runner.py`, `prompts/china_*.md` | `tests/test_china_search.py` (Repair) |
| Queue + worker | `china/queue.py`, `china/search.py`, `jobs/china_search.py` | `tests/test_china_queue.py`, `tests/test_china_search.py` |
| Telegram | `china/bot.py`; `listener.py` (own commit); 🇨🇳 button in 🌍 Market | `tests/test_china_bot.py`, `tests/test_listener_china.py` |
| Taobao reader (bot profile; not used while `taobao_mode` is `link`) | `china/taobao.py` | live: logged-out detection |

### Live runs (owner's chat)

| Run | Result |
|---|---|
| PDD + 1688, 17:56 | 1688 ok (5 offers, weights from the page); PDD stopped as "check": product pages hide prices → prompt fallback added. Found: 1688 "新人价CN¥3.90起" promo → promo rule added |
| PDD, 18:03 | rejected: one prose field 202 > 200 chars → prose trimmed instead; JSON extraction hardened |
| PDD, 18:06 | ok in 73 s, 14 turns, ~$0.41 list-equivalent: 5 results from listings, notice shown |
| Phone demo, 23:14 (`/china GaN charger 65W EU plug`) | answer in 4 min from both sites + Taobao link. 🏆 went to a no-name 1688 "65W" charger at ¥23.85 over brand-authorised Ugreen → safer pick rule and "⚠️ suspiciously cheap" (decision 091). 1688 product pages refused JavaScript (2 of 5 read, from screenshots) → 1688 prompt reads them with `get_page_text`. The 🔗 Taobao link searched the whole English request with the question answers ("What will it charge…"), and Taobao matched "it" to the i.t clothing brand → links now use the plan's Chinese words (`氮化镓充电器 65W 欧规`) |
| Taobao sign-in | owner tried QR login in `.browser/taobao`: Taobao then demands phone confirmation with a slider that fails in the bot's browser → `taobao_mode: link` |

### Demo from the phone (P1 done when this passes)

Once: restart the listener so it loads the new code (stop / wait 3 s / start the
`FamilyAssistant-Listener` task).

1. 🏠 Home → 🌍 Market → **🇨🇳 China search** → type `GaN charger 65W EU plug` →
   "⏳ Searching Pinduoduo, Taobao, 1688…" → "⏳ Pinduoduo done (1/3)…", "⏳ 1688 done (3/3)…"
   → one rich answer: 🏆 pick with reason, 🔗 Taobao search link, tables, details per result.
2. Tap a result's details: price ¥ → AMD · USD, `⚠️ SHIPPING ESTIMATED FOR 1 KG` when no
   weight, every forwarder × mode, seller class, the Chinese seller message.
3. Tap **🔁 Only 1688** → a new search on 1688 only. Tap **👁 Watch 2** → "Added to 🌍 Market
   watch"; /watch lists it.
4. `/china running shoes` → 1–2 questions with buttons (size, budget) → answer with the 👟
   Poizon line.
5. From Karine's phone at the same time: `/china kids raincoat` → "you are 2nd in line"; her
   answer comes to her chat only. `/china last` on each phone shows that phone's last answer.

### Not done in P1

- Taobao reading (blocked by its sign-in check); 💬 Reviews for Taobao items.
- Pinduoduo variant prices and reviews (product pages hide prices on the web now).
- Photo search (built in P2, §10), the logon tabs and the 09:00 login check (§6 P3), Mini App.


## 10. P2 photo search (2026-11-10, decision 095)

The owner asked for photo search next ("start china P2 photo search"), so the brief's P3 became
P2 and "Keep logged in" became P3 (§6).

### Discovery (owner's Chrome, then headless)

| Site | Photo search on the web | Headless (`claude -p --chrome`) | Used as |
|---|---|---|---|
| **1688** | Yes: `Image Search` button next to Search → `input[type=file].image-file-reader-wrapper` (jpg/png/webp/bmp) → preview + `Search for` → `air.1688.com/kapp/1688-search/pc-image-search/?tab=imageSearch&imageId=…`. 60 cards, **not links**: the offer id is the last number of `data-renderkey`; `detail.1688.com/offer/<id>.html` opens the same product. Matches are visually similar, not always the same item (a Switch dock and a Bluetooth receiver among GaN chargers) → `1688_image_search.json` | **Works**: `file_upload` (path) accepted, 60 cards, 2.5 min, ~$0.39 → `headless_1688_photo.json` | photo search |
| **Pinduoduo** | **No**: mobile web has no file input; its JS bundle only shows the modal "需前往拼多多APP 使用拍照搜同款" (go to the app) | — | text search with the Chinese words read from the photo; the answer says so |
| **Taobao** | Has an image search on `s.taobao.com`, but Taobao cannot be read unattended at all (P0/P1: per-action permission prompts, phone/slider check) | — | link with the photo's words + "📷 in the Taobao app, tap the camera in the search bar" |

The photo itself is read by `claude -p` as a base64 image block on stdin
(`--input-format stream-json`, `--tools ""`, the mechanism the Health records probe proved):
13–14 s → `{"is_product", "seen", "query_cn", "query_en", "brand_seen", "category"}`, validated
whole (`validate.photo_plan`) → `photo_plan_live.json` ("UGREEN 65W GaN … swappable plugs",
`绿联 65W氮化镓充电器 旅行套装`). The first call cost ~$1.18 list-equivalent (cache creation),
later ones ~$0.07.

### Built

| Part | Files | Proven by |
|---|---|---|
| Image in the message, caption command, Bot API download (10 MB cap, no partial file, token never shown), delete and sweep, id masking | `china/photo.py` | `tests/test_china_photo.py` Helpers |
| Photo plan (image on stdin, no tools) and its validator; 1688 photo run with `file_upload` added only there (`upload_image`, `form_input`, `Bash`… still denied) | `china/runner.py`, `china/validate.py`, `prompts/china_photo_plan.md`, `prompts/china_1688_photo.md` (+ steps 2–4 of `china_1688.md`) | Runner, PlanValidator tests |
| Photo job: download → plan → 1688 by photo (falls back to words if it fails) / Pinduoduo by words / Taobao link + tip → same pricing, trust, 🏆, report ("China photo search", "📷 … · searched as …") → `/china last`; photo deleted after the answer | `china/search.py`, `china/report.py`, `jobs/china_search.py`, `config_china.json` (`photo_keep_minutes` 0, `photo_ask_minutes` 60) | Worker tests, incl. the live 1688 answer priced end to end |
| Telegram: `/china` caption → search; other photos → one question `🇨🇳 Search China` / `✖ No` (`cn:ph:` / `cn:phx:`); 🔁 on a photo answer by words (or by photo while kept); user id + role on every photo job, viewers refused | `china/bot.py`; `listener.py` (own commit) | BotPhoto tests, `tests/test_listener_china.py` |

Photo uses elsewhere in the bot: none today — the listener dropped every message without text.
Health records (brief) reads photos only inside an open `/health` conversation; it must be
checked before the China route when built.

### Live runs

| Run | Result |
|---|---|
| Headless probe, 1688 by photo (Ugreen 65W listing image) | ok: upload accepted, 60 cards, 2.5 min, 21 turns, ~$0.39 |
| Real code, photo plan + 1688 by photo, 2026-11-10 | plan 13 s (~$0.07); 1688 ok in 3.8 min, 44 turns (~$0.66): 4 results with page weights (58–120 g), suppliers and reviews; the model flagged an "Anker"-named listing whose page says 是否原装: 否 → `answer_1688_photo_live.json` |
| Phone demo | pending — see below |

### Demo from the phone (P2 done when this passes)

Once: restart the listener so it loads the new code (stop / wait 3 s / start the
`FamilyAssistant-Listener` task).

1. Take a photo of a real item (e.g. a charger or a toy), send it with the caption
   `/china` → "⏳ Searching China by your photo — 1688 by photo, Pinduoduo by the words in it,
   a Taobao link… (~10 min)" → "⏳ Pinduoduo done (1/3)…", "⏳ 1688 done (3/3)…" → one answer
   "🇨🇳 China photo search · …" with "📷 … · searched as …", 🏆, tables, details, the 🔗 Taobao
   line with the app tip, and "ℹ️ Pinduoduo: searched by the words read from your photo…".
2. Send another photo **without** a caption → "📷 Search China for the item in this photo?"
   → tap ✖ No → "OK — not searching." Send it again, tap 🇨🇳 Search China → the search starts.
3. Caption `/china only 1688 black` on a photo → 1688 only, by photo.
4. `/china last` shows the photo answer; 🔁 Only Pinduoduo on it searches by the photo's words.
5. Check: `.browser\china_data\photos\` is empty after each answer.

## 11. Worker supervision (2026-11-10, decision 104)

| Failure | What happens now |
|---|---|
| Jobs wait and no worker is alive (it died, or the PC restarted) | A worker is started on the next enqueue and at listener startup (`china/watch.ensure_worker`) |
| The worker crashes before taking a job (e.g. an import error) | The watcher thread drops that job, tells its asker "didn't start — please send it again" and the owner with the last line of `.browser/china_data/worker.err`; other waiting jobs get a new worker |
| The worker dies in the middle of a job (killed, PC off) | `current.json` is left behind → the asker gets "stopped before it finished — please send it again", the owner the same with the reason; found by the watcher, or at the next startup / enqueue |
| A job was stranded in the queue | Dropped when a worker starts if it was queued before that worker and is older than `stale_job_minutes` (30): "Your China search for “…” didn't start — please send it again." |
| An exception inside a job | Unchanged: "⚠️ China search failed (…)" to the asker, SYSTEM line to the owner |

The worker's stderr is kept in `worker.err` (never DEVNULL); `worker.log` is unchanged.

