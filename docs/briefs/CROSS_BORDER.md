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

## 6. X0 results

(empty until X0 runs)
