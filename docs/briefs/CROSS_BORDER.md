# CROSS_BORDER.md — "where to buy it and how": China and Amazon UK/DE/IT

Status: **plan, not started** (2026-11-17). Owner's request: "add details for cross country like
pinduoduo, taobao, amazon de, it and dubai in future and give details where to buy it."

**Owner's answers (2026-11-17):**
- The owner always buys **directly on the site**. There is no buy-for-me path, no buyout fee, and no "can I pay here" check.
- Onex, Globbing, BuyForYou and EasyTrans are all **shipping companies (forwarders)** with different prices
  and different warehouse locations. "How to buy" = buy on the site yourself, ship to the right
  forwarder warehouse, choose the forwarder × mode the totals favour.
- **No Dubai for now.** It is parked under §4 "Later".

Builds on `CHINA_SEARCH.md` (`/china`: Pinduoduo, Taobao, 1688) and `AMAZON_SEARCH.md` (`/amazon`:
UK, DE, IT; the shared engine and `/find` in §3–§4). Nothing here replaces them. One phase per session
(CLAUDE.md §9). `lib/` and `listener.py` are not touched unless a phase says so in its own commit (§1).

---

## 1. The gap today

A `/china` or `/amazon` answer already says **what** to buy and **what it costs delivered**. For every
result it gives: the item price, the price in AMD, each forwarder × mode, customs, the arrival range,
the seller's trust, and a link.

It does not say **how to actually buy it**. That leaves these open:

| Question the family has at the moment of buying | Today |
|---|---|
| Which of my forwarder addresses do I type at checkout (China / Germany / Italy / UAE warehouse, my suite code)? | not said (the bot knows the postcode, the person has to remember the rest) |
| Which forwarder and mode should I pick in my forwarder account, and why? | the cheapest line is visible; no "pick this" |
| Is there a minimum order (1688), a group price that needs a partner (Pinduoduo), or a coupon condition? | partly (PDD group/single prices kept apart) |
| Will the forwarder refuse it by air (battery, liquid, magnet, aerosol)? | flagged per result in China; not tied to "so choose truck/sea" |
| Customs: does this one parcel cross €200, and would two parcels be cheaper? | per item only |
| When will it be in Yerevan? | arrival range per line; no single "arrives about 3–5 Dec" on the pick |

---

## 2. What "where to buy" means in an answer (target)

Every answer gets a **🛍 Where to buy** block under the 🏆 pick, and every result fold gets a
**How to buy** section. All numbers come from Python (CLAUDE.md §2); all how-to text comes from a
hand-edited data file (§3), never from the model's memory.

This is an illustration of the layout only. The 8,470 and 8,793 AMD totals are from the real P1 run
(AMAZON_SEARCH §11.2). The arrival dates and the air difference are made up for the example.

```
🛍 Where to buy
🏆 Anker Nano II 65W — Amazon DE, sold by Amazon
   Cheapest delivered: 8,470 AMD · Onex truck · arrives about 3–9 Dec
   Fastest: 8,793 AMD · Amazon UK → Onex air · arrives about 26–28 Nov (+323 AMD)
   Most trusted: same as cheapest
How to buy (Amazon DE)
 1. Pay on amazon.de with your own card (EUR). Amazon's delivery to the warehouse: free on a first order (a condition, not counted).
 2. Address at checkout: your Onex Germany warehouse address (82152) with your suite code — from your Onex account.
 3. In Onex: choose truck (cheapest) or air (+1,400 AMD, ~10 days sooner).
 4. Customs: 0 (under €200). Restrictions: none.
Checked 2026-11-xx · market/buying.md
```

For China the same block says which forwarder's China warehouse to ship to (each forwarder × mode
priced: Onex, Globbing, BuyForYou, EasyTrans), the site's own delivery to that warehouse, the minimum
order (1688), and the group vs single price (Pinduoduo).

Three lines, always the same three: **cheapest delivered**, **fastest**, **most trusted**. If one
result is all three, it says so in one line. Each line carries its reason (CLAUDE.md §5).

---

## 3. Data: `market/buying.md` (new, hand-edited, like `stores.md` and `forwarders.md`)

One row per store. The owner buys directly on every store, so there is one path: pay on the site,
deliver to a forwarder warehouse. The code knows nothing store-specific; a new store is a new row.

| column | meaning |
|---|---|
| store | key from `market/stores.md` (`pinduoduo`, `taobao`, `1688`, `amazon_de`, `amazon_it`, `amazon_uk`) |
| min_order | `moq` when the site has minimum quantities (1688) |
| address | which warehouse to type: `forwarder:<origin>` (the person's own address in that forwarder account; the bot shows the postcode only) |
| steps | short template lines with `{placeholders}` filled by code (price, forwarder, mode, arrival) |
| checked | date the row was verified on the real site, and the source page |

Rules:
- A row older than 90 days shows "⚠️ buying steps last checked on <date>" — still shown, never hidden.
- No suite codes, account names or addresses are stored. The person's own address stays in their forwarder account.
- Forwarder prices are not in this file. They stay in `market/tariffs.json` (refreshed weekly) and every
  total comes from `market.pricing.quote`, as now.

---

## 4. Phases

Each phase: `pytest` green, ruff clean on changed files, a phone demo, a DECISIONS entry and a named
doc change (CLAUDE.md §10).

### X0 — Discovery (no code; read-only checks in the owner's Chrome and the bot's browser)

Fill `market/buying.md` with **verified** rows, each with a source and date. Check, by looking:

1. **Which forwarder warehouses serve each store.** China: Onex, Globbing, BuyForYou (air), EasyTrans
   (truck) — the China warehouse city of each, so the site's own delivery to it is right. Amazon UK/DE/IT:
   which forwarders have each country (already in `market/forwarders.md`; re-checked).
2. **Pinduoduo and Taobao:** what the checkout shows when the address is a forwarder's China
   warehouse — domestic delivery fee, "包邮" conditions, how long the seller takes to dispatch.
3. **1688:** the minimum order (起批量) as the page shows it, so a result below the minimum is marked.
4. **Amazon DE / IT / UK:** items Amazon refuses to send to forwarder addresses, and any first-order
   delivery conditions. Most of this is already known from P1 (§11 of AMAZON_SEARCH).
5. **Forwarder restrictions** per forwarder × mode (battery, liquid, magnet, aerosol), re-checked on each
   forwarder's site, so the restriction-aware route in X2 uses current rules.
6. **Customs:** the existing open item. Is the EAEU 2026 rule in force (`market/customs.md` switch)?
   This changes every total, so it is settled here.

Output: `market/buying.md` and a discovery table in this brief (§6).

### X1 — "How to buy" in every China and Amazon result

- `market/buying.py` (new): reads `buying.md`, gives `how_to(store, offer, quote_lines) → steps[]`.
  Pure functions, tested, including the rejection path (missing row, stale row, unknown warehouse).
- Steps:
  1. buy on the site yourself (link);
  2. deliver to <forwarder>'s <country> warehouse (postcode; your suite code is in your account);
  3. in <forwarder>, choose <mode> (the cheapest), or the fastest alternative with its difference;
  4. customs and restrictions.

  1688 adds the minimum order; Pinduoduo says which price is the group price.
- `china/report.py` and `amazon/report.py`: a "How to buy" section in each result fold. The plain-text
  fallback gets the same lines.
- Mini App China screen: the same section (it reads the saved answer, so no new endpoint).
- Tests on the existing fixtures: the answer for a known fixture contains the expected steps.

### X2 — The 🛍 Where to buy block (cheapest / fastest / most trusted)

- Python picks the three from the already-ranked results:
  - cheapest = lowest delivered total above the trust floor;
  - fastest = `market.pricing` fastest line (exists: earliest latest-arrival, then price);
  - most trusted = the top of the trust order.
- Each line shows the difference against the cheapest ("+323 AMD, ~10 days sooner").
- **Restriction-aware route:** a battery item never gets an air line as "cheapest" or "fastest" when
  that forwarder refuses it by air. The line says why ("air refused: battery").
- **Parcel note** for several items in one answer (opt-in button "🧮 Buying more than one?"):
  - shows whether together they cross €200;
  - says whether two parcels would be cheaper;
  - uses the existing customs code in `market/customs.py`.
- The 🏆 reason sentence from the model stays as it is: numbers are only from the facts it is given.

### X3 — Shared engine (= AMAZON_SEARCH P1b, already planned)

The extraction into `find/` with golden files (AMAZON_SEARCH §3.2). Needed before X4: one "Where to
buy" across China and Amazon is only clean when both use one engine. "Where to buy" moves into
`find/report.py` with no change in output (golden files prove it).

### X4 — `/find` across markets with one "Where to buy" (= AMAZON_SEARCH §4.1)

- One answer from China and Amazon (UK/DE/IT); Armenia and Russia when their adapters exist.
- The three lines of X2 work across markets: "Amazon DE is 600 AMD dearer than Pinduoduo but arrives
  5 weeks sooner".
- Mini App: a market chooser with chips, remembered per person, and the generic results screen.
- The same product on several markets is one row with several prices (`same_product`).

### Later, only if wanted

- **Dubai (Amazon.ae, noon.com)** — parked by the owner 2026-11-17. When it starts:
  - discovery first:
    - are the pages readable?
    - how is the UAE warehouse set as the address, since the UAE has no postcodes in common use?
    - is AED in the CBA rate feed?
  - then an adapter on the X3 engine.

  Onex and Globbing UAE air prices are already in `market/tariffs.json`.

- **Price watch with "where to buy" kept fresh.** The 👁 Watch line says "now cheapest at Amazon IT"
  when the nightly check finds another store cheaper for the same item. This needs a product match
  across stores, so it comes after X4.
- **A tracking-number field.** Paste a forwarder tracking number, and Home shows the "in Yerevan
  about …" date. It is optional and has no reminders (light-tracking preference).
- **Taobao read automatically.** This needs China P3 "keep logged in" (already on the ROADMAP).

---

## 5. Questions for the owner

Answered 2026-11-17 (see the top): buys directly on the site; the four forwarders are shipping companies; no Dubai now.
Order: X0 → X1 → X2 → X3 → X4.

---

## 6. X0 results (2026-11-18, decision 114)

Read-only checks: the forwarders' public sites, the EasyTrans API the tariff refresh already uses, the
captured `/china` and `/amazon` results in the repo, and a web search on the customs rule. No account
was signed in to, nothing was ordered. Output: `market/buying.md` (two tables, every row dated and sourced).

| # | Question | Found | What it changes |
|---|---|---|---|
| 1 | Forwarder warehouse per store | China: Onex, Globbing, BuyForYou (air) and EasyTrans (truck), as in `tariffs.json`. UK, DE and IT as in `stores.md`. **No forwarder publishes its warehouse city**: Onex and Globbing name countries only (Globbing: the US one is in Delaware); BuyForYou says "USA and China"; the EasyTrans site renders only in a browser | The steps say "your <forwarder> <country> warehouse address — from your account" and print only the public postcode we already have (Amazon). No address is stored |
| 2 | Pinduoduo / Taobao delivery to the warehouse | Already in every `/china` result: `domestic_delivery_text` (包邮 = free, ¥ fee, or unknown, never shown as free when unknown) | No new reading. X1 puts it in step 2 |
| 3 | 1688 minimum order | Already captured on every 1688 result (`min_order_text`, e.g. "1个起批", "1套起批") with quantity tiers in the reason | X1 moves it from the fold's end into "How to buy" |
| 4 | Amazon refusals to forwarder addresses | None seen in P1's real runs. Amazon's first-order free delivery is a condition on every store | Kept as in P1: the condition is said, not counted. Nothing new to build |
| 5 | Forwarder restrictions | **Globbing** publishes a list (batteries only inside a device and ≤ 100 Wh; perfume ≤ 200 ml; magnets and pressurised items not allowed; not split by mode). **Onex, BuyForYou, EasyTrans publish none** that can be read | X2 cannot say "air refused" for Onex, BuyForYou or EasyTrans. For them the line says "check with <forwarder> before ordering"; for Globbing the route is marked from the table |
| 6 | Customs | Onex's and Globbing's FAQs (read 2026-11-18) still state **€200 and 31 kg duty-free, 15 % of the part over €200, €2 per kg over 31 kg** (Globbing cites the SRC announcement of 2024-03-29). The EAEU 5 % rule is reported for **1 Jan 2027**, not 1 Jul 2026 (a news article; not official). BuyForYou states no rule | `market/customs.md` stays on `default`. Re-check in January 2027 |
| 7 | EasyTrans China truck days | API `expectedArrivalDay: 35` (the owner's experience: about 1.5 months from departure) | No change; the existing note stands |

**Not done in X0, on purpose:**
- No login was made to read the warehouse addresses: they are the owner's account data.
- No message was sent to any forwarder.

Asking Onex and BuyForYou for their battery and liquid rules is the owner's call: a message on the
owner's behalf needs the owner's yes.

**Next: X1** — `market/buying.py` and the "How to buy" section in `/china` and `/amazon` results.

---

## 7. X1 results (2026-11-18, decision 115)

### Built

- **`market/buying.py`** (new) reads both tables of `market/buying.md` and gives:
  - `how_to(data, store, quote, price_text, delivery_text, flags, extra, today, store_rows) → steps[]`;
  - `attach(offers, step_fn, today, log)`, which sets `offer["how"]`.
- **The steps, in order:**
  1. Pay: the row's words and the price as the result shows it.
  2. Deliver to your forwarder's <country> warehouse. The public postcode is shown when `stores.md`
     has one (the Amazon stores only), and the site's delivery there as the result read it.
  3. The cheapest forwarder × mode with its delivered total and arrival.
  4. "Faster: …, +N AMD" when another route arrives sooner. The difference is the only sum made
     here (AMD minus AMD).
  5. Customs: none, about N AMD, or near the €200 limit.
  6. "Check: …" from the row.
  7. Extra lines (1688's minimum order).
  8. One ⚠️ line per restriction flag, judged for the cheapest route's forwarder from the
     restrictions table: "publishes no rule — check with …", "does not take it", or "takes it only if …".
  9. A dated ⚠️ when the row is older than 90 days.
- **Wired in:**
  - `china/search.how_steps` + `assemble`, and `amazon/search.how_steps` + `assemble`. The steps are
    set on the ranked results before the answer is built, so they are saved in `last_<chat>.json`
    and the Mini App shows them without a new endpoint.
  - `china/report.how_lines` (the Amazon report imports it): a "🛍 How to buy" label, then the steps
    numbered; ⚠️ lines are not numbered. It goes at the end of each result's fold, before the link,
    and the plain fallback gets the same lines.
  - 1688's separate "Minimum order" line is dropped when the steps carry it.
  - Mini App China card: a "How to buy" section under "Shipping to Yerevan" (`china_view.py` passes
    `how`; `ChinaScreen.tsx` numbers it the same way).
- **Failure:**
  - A store with no row gets no steps, never invented ones.
  - A missing or broken `buying.md` never fails a search: every result says "How to buy is
    unavailable: market/buying.md could not be read" and the worker log has the reason.
- **Fix found while testing:** the DE and IT rows' check column said only "Same". It is now the
  sentence, and a test keeps every row's check a real sentence.

### Example (Amazon DE, from the captured test pages)

```
🛍 How to buy
1. Buy on amazon.de with your card — €19.99.
2. Deliver to your forwarder's Germany warehouse (82152) — the full address and your code are in
   your forwarder account. Amazon's delivery there: FREE delivery Friday, 13 November on eligible
   first order (free on a first/eligible order only - real cost unknown — not counted).
3. In your forwarder account choose Onex truck — the cheapest, 12,796 AMD delivered,
   arrives ~Fri 4 – Fri 11 Dec · 15–20 wd.
4. Faster: Onex air, +900 AMD, arrives ~Fri 20 – Fri 27 Nov · 5–10 wd.
5. Customs: none (under €200 and 31 kg).
6. Check: Seller and "Dispatched by Amazon" line, shown on every result.
```

### Tests

- `tests/test_buying.py` (new, 12 tests):
  - the committed file loads (6 stores, 16 restriction rows);
  - the order and words of the steps, and the faster line only when it is really faster;
  - unpriced and customs (over and near);
  - restriction unknown / refused / limited;
  - China row with the 1688 extra;
  - no row gives no steps;
  - a stale row shows its date;
  - a file with no Stores table is refused;
  - `attach` with a broken file tells every result.
- `tests/test_china_search.py` and `tests/test_amazon_search.py`: the end-to-end answers contain
  "🛍 How to buy" and the first step, and the saved answer carries `how`.
- Full suite: 968 passed, 846 subtests. Ruff: the new files are clean. The changed files have no
  new findings: the counts are the same as before the change, because the repo has no ruff config
  and the defaults flag the old `%` formatting.
- Mini App: `npm run build` clean.

### Phone demo (owner)

1. `/amazon usb c charger 65w` → open any result's fold. The last part is **🛍 How to buy**,
   steps 1–6 as above, with the store's postcode and Amazon's delivery line.
2. `/china usb c charger 65w` → a Pinduoduo result's fold:
   - "Buy in the Pinduoduo app yourself — ¥…";
   - "Deliver to your forwarder's China warehouse …";
   - the cheapest route and, when one arrives sooner, the faster route;
   - "Check: Group price (拼单) …".

   A 1688 result also shows "Minimum order: …".
3. A power-bank search shows "⚠️ Battery: … publishes no rule — check with … before ordering" when
   Onex is cheapest, or "Globbing takes it only if …" when Globbing is.
4. Mini App → 🇨🇳 China → a card → Details → **How to buy**, numbered the same way.

The China and Amazon workers and the Mini App server must be restarted once to load the new code.

**Next: X2** — the 🛍 Where to buy block (cheapest / fastest / most trusted) above the results.
