# MARKET_WATCH.md — watch items on foreign and Armenian marketplaces (brief, not built)

Status: **confirmed 2026-10-29; P0 discovery done (§9)**; Wildberries/Ozon in P1 with the store fallback (§9). P1 not started.
Facts below were seen on 2026-10-29 from this PC (Armenian IP); research notes with sources:
discovery step P0 re-captures them as fixtures before any parser is written (CLAUDE.md §8).

---

## 1. What it does

A shared watch list (Davit and Karine). Every night at ~01:30 the bot reads each item's
product pages in the stores chosen for that item, adds the cost to bring it to Yerevan
(the store's own shipping to the forwarder's warehouse, each forwarder × each mode, customs
estimate), converts everything to AMD, and sends **one full report per day** to both chats.
Instant alerts (with sound) for a **big drop** and **back in stock**.

The bot only reads prices. It never logs in with your password, adds to cart or buys.

## 2. Decisions taken in the interview

| # | Question | Answer |
|---|---|---|
| 1 | Daily message | Full report every day (all items, all offers) |
| 2 | "Similar" items | Rules in code filter; Claude only ranks the shortlist and gives a reason (phase 2) |
| 3 | Users | Davit and Karine, one shared list |
| 4 | Adding items | Telegram dialog (`/watch add`) **and** an editable Google Sheet |
| 5 | Taobao / Pinduoduo | Bot's own browser profile; **you** sign in once yourself; it reuses the session to read only |
| 6 | Amazon | Free first: real browser profile (like the stays scan). If Amazon blocks it, decide then (Keepa ~€49/mo or links only) |
| 7 | Alerts | Big drop, back in stock (no target-price alert) |
| 8 | Price includes | Shipping per mode per forwarder, store's own delivery to the forwarder, customs estimate (not home delivery) |
| 9 | Weight / size | Asked once per item, stored. For China items the bot gives a ready Chinese message to send the seller |
| 10 | List size | Up to ~20 items; each stays until you mark it bought or remove it |
| 11 | Run time | ~01:30 at night |
| 12 | Forwarder tariffs | **Not** read daily: refreshed weekly (Sunday), stored, changes reported |
| 13 | First version | Shipping calculator + exact product links; search and similar later |

## 3. Data (no database — Git files + one Sheet, like the basket)

**Google Sheet "Watch list"** (shared, phone-editable), tabs:

- `items` — one row per item:
  `id · name · mode (exact|similar) · links (exact: one URL per store) · keywords / must-have
  specs / exclude words (similar) · stores to search · qty · weight_kg · size_cm (L×W×H) ·
  max_age · added_by · status (active|bought|removed) · notes`
- `offers` — the last run's offers (written by the bot): item, store, title, price in store
  currency, in-store shipping, stock, link, seen_utc.
- `history` — one row per item per day: best total per mode (AMD) — the source for "big drop".

**In Git** (`market/`, edited by hand, reviewed like the plan):

- `market/stores.md` — every store: country, currency, how it reaches Armenia, and the
  forwarders/warehouses allowed for it. Different per store, as you asked:

  | Store | Ships to | Routes to Yerevan |
  |---|---|---|
  | Amazon US | Onex / Globbing USA warehouse (Onex: Delaware, no sales tax) | air · sea |
  | Amazon UK | UK warehouse | air |
  | Amazon DE | Germany warehouse | air · truck |
  | Amazon IT | Italy warehouse | truck |
  | Wildberries, Ozon | direct to Armenia (own pickup points) — or Russia warehouse | store delivery · Russia air · Russia truck |
  | Taobao, Pinduoduo, AliExpress | China warehouse | air · truck · sea |
  | Armenian shops (vega.am, yerevanmobile.am, mobilecentre.am) | local | none (or the shop's delivery) |

  You add stores or routes by adding a row; the code knows nothing store-specific beyond
  its page reader.
- `market/forwarders.md` — Onex, Globbing, EasyTrans, BuyForYou (more later): warehouses,
  modes, tariff source, volume rule.
- `market/tariffs.json` — the forwarder tariffs (written by the weekly refresh): per
  forwarder × warehouse × mode: price per kg, minimum charge, first-kg or ≤1 kg band,
  rounding step, volumetric divisor and which modes it applies to, transit days.
  Sources: Onex calculator JSON (`onex.am/calculator/cost`), Globbing tariff table embedded
  in its page. Seen today (AMD/kg, both nearly equal): USA/UK/DE air 6,000; DE truck 4,000;
  USA sea 1,500 (min 15,000); China air 8,000 / truck 3,500 / sea 1,500; Italy truck
  4,000–4,500; Russia air 2,000 / truck 1,000.
- `market/customs.md` — the rule in use, as config. **Open: which rule applies in 2026**
  (old: duty-free ≤ €200 and ≤ 31 kg per parcel, 15% over; EAEU from 2026-07-01: 5% of the
  full value, min €1/kg, plus 20% VAT above €200). The report always marks customs as an
  estimate and flags items within 10% of the limit.
- Exchange rates: Central Bank of Armenia (`api.cba.am`), once per run, cached for the day.

## 3a. Coverage: origin × forwarder (seen 2026-10-29; times are **working days**)

AMD per kg · days exactly as the forwarder publishes them. "—" = no such route.
EasyTrans (owner's screenshot of its tariff table, 2026-10-29) lists **only two routes**:
China truck and Poland air, its page says "calendar days" ("օրաց. օր") but the owner's experience (~1.5 months) means **working days**, counted **from
dispatch out of the warehouse** (its footnote). Other cells marked P0 are re-checked there.

| Origin | Mode | Onex | Globbing | BuyForYou | EasyTrans |
|---|---|---|---|---|---|
| USA | air | 6,000 (≤1 kg: 4,900) · *days: P0* | 6,000 · 3–9 wd | 4,100 · 7–10 wd | P0 |
| USA | sea | 1,500, min 15,000 · *P0* | 1,500, min 15,000 · ~3.5 months | 1,100, min 11,000 · *P0* | P0 |
| UK | air | 6,000 (≤1 kg: 4,900) | 6,000 · 5–10 wd | — | P0 |
| **Germany** | air | 6,000 (≤1 kg: 4,900) | 6,000 · 5–10 wd | — | P0 |
| **Germany** | truck | 4,000 | 4,000 · 15–20 wd | — | P0 |
| **Italy** | truck (only mode) | 4,500 | 4,500 · 7–13 wd | — | P0 |
| China | air | 8,000 (≤1 kg: 6,900) | 8,000 · 5–11 wd | 4,900 · *P0* | P0 |
| China | truck | 3,500 | 3,500 · ~45 wd | — | 1,500, min 1,500 · ≤35 wd from truck departure |
| China | sea | 1,500 | 1,500 · ~2.5–3.5 months | 1,100, min 11,000 | P0 |
| Russia | air | 2,000 | 2,000 · 2–4 wd | — | P0 |
| Russia | truck | 1,000 | 1,000, min 4,000 · 9–17 wd | — | P0 |
| Poland | air | — (Onex: truck 3,000) | — | — | 3,000, min 300 · ≤20 wd |

BuyForYou has **USA and China warehouses only** (its calculator and its "Places" page list
only those two), so for Germany, Italy and UK the report offers Onex and Globbing (and
EasyTrans if P0 shows it has them). Spain, Greece, Poland, UAE and Korea exist at Onex /
Globbing too and can be added as stores later. Onex does not publish delivery times in its
calculator; P0 looks for them on its pages, otherwise they are entered by hand with the date.

### Delivery time (in the unit each forwarder uses)

Every route stores its time exactly as the forwarder states it: `min`, `max`, and the
**unit** — `working` days (Globbing, BuyForYou), `calendar` days (none so far), or `months`
(sea) — plus **from when** it counts (`arrival` at the warehouse, or `dispatch` from it, as
EasyTrans says). Working days skip weekends and holidays; calendar days don't; the report
writes the unit next to the range so the two are never mixed up.
The report shows both the range and an **estimated arrival date**:

```
arrival = today
        + store's delivery to the warehouse (from the product page when shown, e.g. Amazon's
          date; else "store time unknown" and the date is marked as excluding it)
        + the forwarder's waiting time until dispatch when the time counts from dispatch
          (unknown → the date says "after dispatch")
        + the forwarder's min … max in its own unit; working days count Mon–Fri only and
          skip Armenian public holidays (list in market/holidays.md, reviewed each January)
```

Example line: `Globbing air 6,000/kg · 2.4 kg → 14,400 · 5–10 working days · arrives
~Mon 9 – Mon 16 Nov`. Code, unit-tested (weekends, a holiday inside the range, month end).

## 4. The money maths (code, unit-tested — CLAUDE.md §2)

```
chargeable_kg = max(actual_kg, L×W×H / divisor)   (only for modes where the forwarder applies volume)
                rounded UP to the forwarder's step (100 g today)
shipping      = forwarder band(chargeable_kg)       (min charge, ≤1 kg band, per-kg rate)
total_AMD     = qty × price × rate  +  in-store shipping × rate  +  shipping  +  customs estimate
```

- One total per **forwarder × mode**, each with its working-day range and arrival dates
  (§3a). The cheapest and the fastest are named, with the reason.
- A price that can't be read is shown as "not read" — never guessed. No weight → shipping
  shown per kg and the item flagged "weight needed".
- Tested against real calculator answers captured from Onex and Globbing (e.g. 1.0 kg vs
  1.05 kg across the ≤1 kg band).

## 5. Telegram

New Home section **🌍 Market** (TELEGRAM_UX.md §1), commands `/watch`:

- `/watch` — the list with buttons (check now, open Sheet, add).
- `/watch add` — dialog: name → paste link(s) or keywords → exact or similar → which stores
  (buttons, only stores from `stores.md`) → qty → weight and size (or "I don't know").
  If you paste a link the bot reads the product first and asks only what's missing.
- China item without weight → the bot sends a fixed Chinese template (written once in code,
  not by AI) to copy to the seller, asking package weight and dimensions:
  "您好，请问这个商品包装后的重量（公斤）和尺寸（长×宽×高，厘米）是多少？谢谢！"
- `/watch bought <n>`, `/watch remove <n>`, `/watch check` (run now).

**Daily report** (01:30, silent, both chats; fold per item):

```
🌍 Market watch · Fri 30 Oct
━━━━━━━━━━━━
Airfryer Philips HD9252 — best 41,200 AMD (Globbing air, ~7 days) · 📉 −8% vs yesterday
  ▸ Amazon US $79.99 + $0 to Delaware
     Onex air 6,000/kg · 2.4 kg → 14,400 · total 43,300 · 5–9 wd · ~6–12 Nov
     BuyForYou air 4,100/kg → 9,900 · total 38,800 · 7–10 wd · ~9–13 Nov
     Globbing sea → 30,100 (min 15,000) · ~3.5 months
     customs: none (≤ €200)
  ▸ Wildberries 9,890 ₽ + store delivery → 44,900 · 7 d
━━━━━━━━━━━━
Rates CBA 30 Oct · USD 360.5 · EUR 401.0 · CNY 54.1 · tariffs from Sun 25 Oct
```

Alerts with sound: best total down ≥ X% since yesterday (X = 10% unless you say otherwise),
or an exact item back in stock.

## 6. Tokens and time

- Phase 1 uses **no model at all**: reading pages, maths and the report are code.
- Phase 2 calls `claude -p` only for "similar" items, only on the shortlist the rules left
  (≤ 10 per store), returning candidate ids from that list (an id outside it is rejected).
- Each item only visits its chosen stores. ~20 items × 1–3 stores at a polite pace ≈ 10–20 min
  at 01:30. The PC must be on (Task Scheduler "wake to run"). A run that misses the night is
  reported at the next logon (staleness audit, CLAUDE.md §5).

## 7. Phases

| Phase | Content | Done when |
|---|---|---|
| **P0 Discovery** | Capture real pages/answers to `tests/fixtures/market/`: Onex calculator for each warehouse/mode at 0.5 / 1.0 / 1.05 / 2.4 kg; Globbing tariff JSON; CBA rates; one product page per Phase-1 store opened in the bot's browser profile (Amazon US/UK/DE/IT, Wildberries, Ozon, vega.am). Record which stores actually load. | A table: store → readable / blocked, with the captured fields |
| **P1 Exact links + calculator** | `lib/`-free code in `market/` + `jobs/market_watch.py` (nightly), `jobs/market_tariffs.py` (weekly); Sheet; `/watch` dialog and 🌍 Market section (listener change = own commit); daily report and alerts | Report on the phone for 3 real items; tests green |
| **P2 Search + similar** | Store search pages, rules filter, Claude shortlist ranking | Similar item finds offers in ≥ 2 stores |
| **P3 Taobao / Pinduoduo / AliExpress** | You sign in once in the bot's browser profile; reading only | Prices read for 2 real China items |
| **P4 More Armenian shops** | list.am / zigzag.am if a browser gets past their check | — |

Each phase ends with a decision entry (086+), a doc update, and a demo from the phone.

## 8. Owner's answers (2026-10-29)

1. Customs rule 2026: unknown → `customs.md` holds both rules; the report uses the
   **stricter** result and labels it "estimate (rule unconfirmed)"; flagged within 10% of €200.
2. Big-drop alert: **10%** (best total vs yesterday's).
3. Forwarders: accounts at **Onex, Globbing, EasyTrans, BuyForYou**; more may come.
   Forwarders are **data**: one row per forwarder in `market/forwarders.md` (name, site,
   tariff source, warehouses, modes, volume rule) — adding one later = a row + its tariff
   reader, no change to the maths.
4. Wildberries / Ozon: show **both** — direct delivery to Armenia and via a Russia warehouse.
5. Currency: show **both** — original price ($ / € / £ / ₽ / ¥) and AMD.

### First look at the two new forwarders (2026-10-29, to be re-captured in P0)

- **BuyForYou** (buyforyou.am): USA and China only. The calculator is plain JavaScript in
  the page: air USA 4,100 AMD/kg (min 1,400), air China 4,900 AMD/kg (min 490), sea
  1,100 AMD/kg (min 11,000); rounded up to 100 AMD; volume weight L×W×H/**6000**, only when
  a side is over 60 cm; customs threshold shown as €200. The weekly refresh reads these
  numbers from the page.
- **EasyTrans** (easytrans.am): an Angular app with a "delivery calculator" talking to
  `api.easytrans.am`; tariffs are not in the page. P0 finds the calculator's API call in the
  browser; if there is none readable, its rates are entered by hand in `forwarders.md`
  (with the date) and the weekly refresh reminds you when they are older than 60 days.

Note how much the forwarders differ (USA air 4,100 vs 6,000 AMD/kg; volume divisor 5000 vs
6000; ≤1 kg bands) — this is exactly why each forwarder × mode gets its own line in the
report.

## 9. P0 results (2026-10-29)

Fixtures in `tests/fixtures/market/` (real captures, this PC, Armenian IP). Store search
pages (1–2 MB each) are kept out of Git until P1 trims them to the needed parts.

### Forwarders — every one has a machine-readable source

| Forwarder | Source (weekly refresh) | Fixture | Days unit | Notes |
|---|---|---|---|---|
| Onex | `GET https://onex.am/en/tariff` → JSON list: country, type, `estimated_day_from/to`, `mini`/`standard` (AMD per 100 g, `min_cost`, `max_weight`, `is_v_weight`, `rounding`) | `onex_tariff_en.json` | working ("working days" label on its page) | 15 routes. ≤1 kg *mini* band confirmed. Calculator (`POST /calculator/cost`) captured for 70 weight × route answers → `onex_calculator.json`, the test oracle |
| Globbing | `let shippingConditions = {…}` in `https://am.globbing.com/en` | `globbing_home_en.html` | text `≈ 5-10 աշխ. օր` = working; `≈ 3,5 ամիս` = months | warehouse id → country from the page's `<option>` list (Armenian names); also `customsLimitConverted` = 81,600 AMD (€200 × 408), `customsWeightLimit` = 30 |
| BuyForYou | `const usdPrice / cnyPrice` + sea constants in `calculateShipping()` on `https://www.buyforyou.am/` | `buyforyou_home_hy.html`, `buyforyou_places_hy.html` | working ("աշխատանքային օր", 7–10 for USA air) | USA + China only; volume ÷6000 only when a side > 60 cm |
| EasyTrans | `GET https://api.easytrans.am/address/all-available-simple` → JSON per country/method: `transportationPrice`, `minimalWeight`, `minimalPrice`, `expectedArrivalDay`, `isSale` | `easytrans_address_all-available-simple.json` | working, from truck departure (owner, §9 end; the page text says "calendar") | China ground, Poland air only. `common/all-page-configuration` carries the **next truck departure** ("The truck will depart on October 31"; days count from departure) — shown as text, not parsed. `common/delivery-rate` = home delivery tiers (not used) |
| CBA rates | SOAP `ExchangeRatesLatest` at `https://api.cba.am/exchangerates.asmx` | `cba_latest.xml` | — | rate ÷ `Amount` |

### Customs — answered by the forwarders themselves

Onex FAQ, Globbing's calculator and BuyForYou's calculator all apply: **duty-free up to
€200 per parcel; above it 15% on the part over €200**; weight limit 31 kg (Onex) / 30 kg
(Globbing; above it 15% of the whole value + €2 per extra kg). → default rule; the EAEU
2026 rule stays in `customs.md` as a switch.

### Stores — what the bot's browser (`.browser/market`) can read

| Store | Result | P1 plan |
|---|---|---|
| Amazon UK / DE / IT | **readable** (18–54 products, `data-asin`, `a-offscreen` price) | DE and UK showed **USD** and "delivery to United States" (Amazon's converter + default address); IT showed €. P1 sets the profile's currency to the local one and the delivery postcode to your forwarder's warehouse, so price and in-store shipping are the real ones |
| Amazon US | **product pages readable** (re-test 2026-10-29 after the owner opened the profile: no check was shown; `/dp/<ASIN>` gave title, price, delivery date to the warehouse, "Delivering to New Castle 19720", Package Dimensions in inches). **Search** redirects to `/checkpoint/continue` — a normal page of other products, not a challenge — so search is not usable | P1 (exact links); search revisited in P2 |
| Wildberries | **anti-bot wall** in the bot's browser ("suspicious activity" + CAPTCHA; also with the installed Google Chrome, re-test 2026-10-29). Opens normally in the owner's own Chrome, no login. Owner: likely a temporary block of a few hours | **in P1, treated as readable**, with the fallback below |
| Ozon | **blocked** in the bot's browser ("no connection — turn off VPN"; same at `am.ozon.com`, the Armenian site ozon.ru redirects to). Opens normally in the owner's own Chrome, no login | **in P1 via `am.ozon.com`**, with the fallback below |
| vega.am | **readable** (`/en/index.php?route=product/search&search=`, prices in ֏) | P1 |
| yerevanmobile.am | loads (`/en/catalogsearch/result/?q=`), no Philips items — re-test with a real item | P1 if a real item reads |

### What this means for P1

Exact product links for **Amazon US / UK / DE / IT, Wildberries, Ozon (`am.ozon.com`) and
vega.am**, all four forwarders, customs, CBA rates, working/calendar-day arrival dates.

**Fallback — every store, not only WB/Ozon** (owner, 2026-10-29). The bot never tries to
pass a bot check, CAPTCHA or block itself; when a page can't be read the run degrades,
it doesn't fail:

1. One attempt per link per night; a check/block page is recognised and the store is
   skipped for the rest of that run (no retry loop, no hammering).
2. The item keeps its **last read price**, shown with its date and ⚠️ "not re-read
   tonight"; shipping, customs and totals are still computed from it. No drop or
   back-in-stock alert is raised from a stale price.
3. The report has one line per blocked store ("Wildberries blocked tonight — 3 items on
   last price"). After **3 nights in a row** the owner gets one message: open the link
   yourself, or send the price.
4. **Owner's price**: `/watch price <item> <amount>` stores a price typed by the owner
   (marked "owner, <date>") and is used exactly like a read one.
5. An item that has never been read and has no owner's price shows the link only, with
   "no price yet" — never a guessed number.

Owner's forwarder warehouse postcodes (2026-10-29), set as the delivery location in the
store profile so prices and in-store shipping are quoted to the warehouse — not secrets,
kept in `market/stores.md`: USA 19720 (Delaware, no sales tax) · UK E17 4SX · Germany
82152 (Munich) · Italy 70122 (Bari) · Greece 10437 (Athens) · Spain 08016 (Barcelona).

EasyTrans days — owner (2026-10-29): the China truck takes "about 1.5 months" in practice.
35 calendar days is ~1.2 months, 35 working days ~1.6 months, so its number is read as
**working days counted from the truck's departure** (matching its own key
`expectedUntilWorkingDay`); the page's "calendar" wording is treated as a site typo.
