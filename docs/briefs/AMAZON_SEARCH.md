# AMAZON_SEARCH.md — `/amazon` find-and-compare, and the road to one `/find`

Status: **P0 done (2026-11-10, decision 100). Nothing is built.** Waiting for the owner's answers
(§8). Source of truth for this feature; if code and this file disagree, fix this file in the same commit.

Reads with: `docs/briefs/CHINA_SEARCH.md` (the pipeline this reuses), `docs/briefs/MARKET_WATCH.md`
§8–§9 (stores, forwarders, customs), `docs/VISION.md` (gift ideas and shopping use the same search).

---

## 1. What `/amazon` does, and how it differs from `/china`

`/amazon <what you want>` — same chat flow as `/china`: a description (or a vague one gets 1–2 button
questions, e.g. baby size), a plan, a read of Amazon UK, DE, IT and US, then **one answer ranked by
the price delivered to Yerevan** (item + Amazon's own delivery to the forwarder warehouse + forwarder
× mode + customs, all in AMD, from `market.pricing.quote`), with a 🏆 pick and its reason,
📱 Open in app, 👁 Watch and 💬 Reviews buttons.

| | `/china` | `/amazon` |
|---|---|---|
| Reader | `claude -p --chrome` in the **owner's Chrome**; the model reads app-like pages | the **bot's own browser** (Playwright, `scrapers/market.py` Session) and a **Python parser** — Amazon search and product pages are plain HTML (§2). The model never reads a page |
| Model's job | transcribe + classify per site (expensive, §6) | plan (translate the query into German/Italian, category, size questions) and phrase the answer. Both cheap, no browsing |
| Trust problem | fake shops, look-alike brands (Tmall), fake ratings; seller class from badges | none of that. Trust = **who sells and who ships** + rating + review count (§1.1) |
| Currency | CNY, USD | GBP, EUR, USD (store's own, set in the profile, §2) |
| Delivery to Armenia | never direct; forwarder | never direct; forwarder (Amazon delivers to the warehouse postcode) |
| Weight | often unknown → 1 kg + warning | many product pages carry item weight / package size; unknown → same 1 kg + warning |

### 1.1 Seller trust for Amazon (data fields in §2; weights are config, not code constants)

Evidence is only what the page shows; each line below is a *reason* printed next to the result.

1. **Sold by Amazon** (page says `Sold by Amazon…` / `Shipper / Seller Amazon`) — highest.
2. **Third party, Dispatched by Amazon** (`Dispatches from Amazon`, `Ships from Amazon`) — good:
   Amazon handles storage, packing and returns.
3. **Third party, ships itself** (`Shipper / Seller <name>` with a name that is not Amazon) — lower.
4. **Rating and review count together**: a 5.0 from 6 reviews is not a 5.0. Under
   `MIN_REVIEWS_FOR_RATING` (China uses 20) the rating carries no weight and the line says so.
5. Badges that exist: Amazon's Choice (`Overall Pick`), Best Seller, "N+ bought in past month",
   Limited time deal, Small Business. Shown as facts; "bought in past month" counts as sales evidence.
6. **Sponsored** results are not dropped, but are marked and never win a tie.

No brand look-alike check (China's `trust.brand_of`) — not needed for Amazon.
Prime is displayed on cards but is **not** a ranking input: Prime benefits do not apply to a parcel
sent to a warehouse (§8 question 2 asks the owner if he wants it shown anyway).

---

## 2. P0 discovery — what the four Amazons give the bot (2026-11-10)

Method: the bot's browser profile `.browser/market` (signed out — the page header reads "Hello,
sign in"), one attempt per page, 3–6 s apart, no login, no check page met. Postcodes via
`python scrapers/market.py --setup` (first run today showed *Deliver to United States* on UK/DE/IT
because the profile had lost them; `--setup` restored them and everything was captured again).
Queries: electronics = *USB-C charger 65 W* (German *usb c ladegerät 65w*, Italian *caricatore usb c
65w*); baby = *baby romper 6-12 months* (German *baby strampler 68*, Italian *tutina neonato 6-9
mesi*). 16 pages, fixtures in `tests/fixtures/amazon/` (trimmed; README there).

### 2.1 Findings table

| | Amazon UK | Amazon DE | Amazon IT | Amazon US |
|---|---|---|---|---|
| Search page | **readable**, both queries | **readable** | **readable** | **readable today** (on 2026-10-29 it redirected to `/checkpoint/continue` — see 2.3) |
| Product page `/dp/<ASIN>` | readable | readable | readable | readable |
| Check / CAPTCHA seen | none | none | none | none |
| Result cards in the page as loaded | 22 (electronics), 60 (baby) | 22 / 60 | 60 / 60 | 22 / 60 — electronics pages load fewer cards until scrolled |
| ASIN | `data-asin` on every card; `/dp/<ASIN>` | same | same | same |
| Title | card + product page | same | same | same |
| Price + currency | `a-offscreen` on the card: **£**, with list price (`RRP`/`Was`) when discounted | **€** | **€** | **$** |
| Price depends on delivery address? | **No** — the same ASIN (IT `B0GQSWQJ8D`) read €25.99 with the profile on a US address and on the Bari postcode. Delivery **fee and date do** change (UK card: a £8.89 delivery to "United States" became "FREE delivery … to UK or Ireland"). VAT: shown inclusive in the store's currency; US shows no tax (Delaware 19720) | same | same | same |
| Currency depends on profile? | the `i18n-prefs` cookie set by `Session` gives the store's own currency (on 2026-10-29 UK/DE had shown USD — fixed by the cookie) | same | same | n/a |
| Delivery to the warehouse | card line `FREE delivery <date> … to UK or Ireland` / `Fri 13 Nov`; product page: delivery date + `Deliver to London E174SX` | `Deliver to Krailling 82152` | `Deliver to 70122` | `Delivering to New Castle 19720`; `FREE delivery Sunday, November 15 on orders shipped by Amazon over $35` |
| Delivery **fee** as a number | on the card only when not free (`£8.89 delivery`); otherwise "FREE … on eligible/first order" — a threshold, not a number | same | same | same, plus "over $35" threshold |
| Seller / fulfilment | **product page only**: `Dispatches from Amazon` + `Sold by <name>`, or one row `Shipper / Seller <name>`. **Not on cards** | same labels | same labels (`Shipper / Seller Amazon` seen) | `Ships from Amazon` + `Sold by <name>` |
| Prime | on cards/pages as text ("Join Prime to get FREE delivery" on US); not decisive for us | rare on cards | rare on cards | on most cards |
| Rating, review count | card: `4.2 out of 5 stars (418)`; product page: same + count | same (`(2K)` abbreviations on cards, exact `2,061` on the page) | same (`(3.6K)`) | same (`(3.2K)`, page `3,430`) |
| Badges | `Amazon's Choice`, `Best Seller`, `500+ bought in past month`, `Limited time deal`, `Small Business`, `Climate Pledge Friendly`, `New on Amazon in past month`, voucher (`You pay £6.79 with voucher`) | same set (German page text was in English: `locale=en-US`) | same | `Amazon's Choice: Overall Pick`, `10K+ bought in past month` |
| Sponsored cards | 9–14 of 22–60 (labelled) | 9–14 | 13–15 | 8–15 |
| Weight / dimensions | on many product pages in the details table (not on cards); US pages gave inches (10-29 capture) | kg / cm | kg / cm | lb / inches |
| "Cannot ship to selected location" | not met in 16 pages | not met | not met | not met |

Counts are from the full pages (before trimming). The trimmed fixtures keep 8 cards per search.

### 2.2 What this changes

1. **No model is needed to read Amazon.** Cards and product pages have stable, labelled fields; a
   Python parser written against the 16 fixtures reads them for 0 model tokens and cannot hallucinate a
   price (CLAUDE.md §2: numbers are code). China needed the model because Pinduoduo/1688 are app-like.
2. **Seller is one page deeper than search.** Search gives price, rating, count, badges and a
   delivery line; "sold by / dispatched by" needs a `/dp/` read. So a run is: 1 search page per store,
   then product pages for the candidates that survive a price/rating cut (default top 3 per store,
   §8 question 3). Cheap candidates with no seller read are shown with "seller not read".
3. **The delivery postcode must be set, and checked at the start of every run.** The profile had
   lost three of four postcodes. A run reads the `Deliver to` block first and stops that store with a
   message ("Amazon UK is not set to the warehouse — run setup") instead of quoting a wrong
   delivery fee. The product price itself was address-independent in the one case compared, but only
   one ASIN was compared; P1 re-checks on 3 more.
4. **Lazy cards.** Electronics pages gave 22 cards as loaded and baby pages 60. P1 scrolls once (the
   same politeness limits) or works with what loads; either way the answer says how many results it saw.
5. **The bot's profile is shared with the nightly market scan** (`.browser/market`). A Chromium
   profile has one owner at a time, so `/amazon` takes the same lock as `jobs/market_*` (or the run
   waits and says so). Decision for P1; a separate `.browser/amazon` profile is the alternative and
   costs a second `--setup`.

### 2.3 Amazon US

Search worked in both runs today; it redirected to `/checkpoint/continue` on 2026-10-29 and the
product pages never failed. So: **US is searched like the others, and a `blocked`/redirect result
degrades to "US search unavailable now — send me /dp links"** (the `/watch` exact-link path, which
already works) instead of failing the run. P2 decides whether US stays in the default set (§8 q1).

---

## 3. The shared engine question (China → market-agnostic)

China's pipeline is `plan → per-site read → validate → price → trust rank → rich answer + 📱 card +
Watch/Reviews`. Everything after the read is market-agnostic in intent but China-shaped in code.

### 3.1 What is generic and what is not (read from `china/` as of 2026-11-10)

| Step | File | Generic already? |
|---|---|---|
| queue + single worker, last-answer store, progress messages, `/cancel` | `china/queue.py`, `china/search.py` (`run_search`, `save_last`, `load_last`) | **Yes in behaviour**, China-named. Site list `SITES` is hard-coded |
| plan (description → query, category, 1–2 questions) | `china/runner.plan`, `validate.plan`, `prompts/china_plan.md` | Shape generic; prompt and `query_cn` are Chinese-specific |
| read | `china/runner.site`, `prompts/china_*.md` | **No** — Chrome + model. Amazon uses Playwright + parser |
| validate | `china/validate.py` | The *method* (reject whole answer, re-ask once, allow-lists) is generic; the schema (CNY, seller classes, 万 counts) is not. Amazon's parser output is code-made, so it needs a smaller **sanity check**, not an answer validator |
| price | `china/pricing.price_result` → `market.pricing.quote` | Mostly generic: currency + weight → quote lines. China-only: domestic delivery in ¥, `FREE_WORDS` |
| trust + rank + pick | `china/trust.py`, `pricing.rank / best_pick / mark_suspicious / same_product` | Ranking, ties by price band, suspicious-cheap, same-product grouping are generic. The *score* is market-specific |
| answer | `china/report.py` | Layout, folds, blocks limit, buttons generic; strings, 🟥🟧🟦, seller message in Chinese are not |
| Mini App | `miniapp/` China screen | Reads `last_<chat>.json`; screen is China-named |

### 3.2 Decision: rule of two — extract after Amazon works, not before

China is market one; Amazon is market two. Extract **after P1 is demo-passed, as its own session**,
because only then are there two real implementations to compare. Extracting now would freeze China's
shape, which is the wrong shape for a parser-based market.

**Now (P1) — no change to `china/` or `lib/`.** New package `amazon/` with the same file names as
`china/` (`bot.py`, `search.py`, `parse.py`, `pricing.py`, `trust.py`, `report.py`, `queue.py` reuse),
importing the already-generic parts from `market/` and `china/` where they exist (`market.pricing.quote`,
`market.readers.parse_money / parse_weight_kg`, `china.queue`). Copy only what must differ. Where it
copies, a comment says `# same as china/…` so the extraction session can diff.
New code is written to a **common offer shape** from the start (below) so extraction is a move, not a rewrite.

**Common offer shape (the seam).** One dict, adapter-filled, engine-read:

```
{market, site, id, url, title, price, currency, price_kind, list_price,
 delivery_fee, delivery_text, delivery_eta,
 seller: {name, class, evidence}, fulfilment, rating, reviews, sales_text, badges[], sponsored,
 weight_kg, dims_cm, restrictions[], category, notes[]}
```

**After P1 (first step of P3, "extract" session — pure refactor):**

```
find/                      new, market-agnostic
  engine.py                run(job, adapters) : queue, progress, last_<chat>.json, errors per site
  rank.py                  order_key, rank, best_pick, mark_suspicious, same_product   (from china/pricing)
  price.py                 price_offer(offer, store_row) → market.pricing.quote lines
  report.py                rich answer / plain fallback / buttons, labels from the adapter
  contract.py              the offer shape + sanity check (ranges, currency known, id format)
  adapters/
    china.py               plan + read via runner.site + validate + trust (the current code, moved)
    amazon.py              plan + Playwright read + parser + trust
    (vega.py, ru.py, … later: one file each)
china/ and amazon/ keep their bot.py (command words, buttons) and thin wrappers.
```

Adapter contract (what a market must provide): `sites`, `plan(description) → {query_by_site, category,
questions}`, `read(site, plan) → offers + status`, `trust(offer, category) → (score, reason)`,
`labels` (site name, icon, seller-message template or none), `store_row(site)` (a row of `market/stores.md`).

**Guard for the refactor:** before moving anything, record China's output on its captured fixtures
(`tests/fixtures/china/*`) as golden files; after the move the rich answer, the ranked order and every
AMD total must be **byte-identical**, `pytest` green, and a live `/china` run passes the phone demo.
`lib/` and `listener.py` stay untouched unless a new command needs them (own commit, CLAUDE.md §1).

---

## 4. Later markets are adapters

| Market | Reader | Prices / money | Open questions to settle **by looking**, not by assumption |
|---|---|---|---|
| **Armenian shops** — vega.am first (readable, `route=product/search`, ֏), then shops the owner names | Playwright + parser (bot browser), like Amazon | AMD already; `modes = local` → **no forwarder, no customs**, only the shop's delivery fee / pickup. Trust = shop reputation is out of scope: a shop on the list is trusted; the line says "in stock / pickup" | Which shops are readable? (P3 discovery table, same method as §2.) Stock and pickup text per shop |
| **Wildberries** | `claude -p --chrome` in the **owner's Chrome** (blocked in the bot's browser: anti-bot wall 2026-10-29) — China's reader path | RUB → AMD (CBA rate already in `market/rates.py`) | Both routes the owner asked for (§8 answer 4 of MARKET_WATCH): direct to Armenia and via a Russia warehouse. **Intra-EAEU customs and delivery rules must be verified** (Armenia and Russia are both in the EAEU; `market/customs.md` holds the 2026 switch that is still unverified — "Waiting on the owner" in the ROADMAP). Do not assume "no duty" |
| **Ozon** (`am.ozon.com`) | same as Wildberries | same | same; plus Ozon's own Armenia delivery terms |

So adapters have **two reader kinds**: `playwright` (deterministic, 0 tokens, bot profile) and
`chrome-model` (owner's Chrome, model + validator, as China). The engine does not care which.

### 4.1 The merged `/find`

`/find <what>` asks the planner once, runs the chosen markets' adapters, and gives one answer:

- **Market chooser in the Mini App** (chips: China · Amazon · Russia · Armenia, remembered per person);
  in the chat, `/find` with words (`/find usb charger only amazon, armenia`).
- **Ranking across markets** needs one rule that is honest about different trust scales: rank
  *within* each market by its own trust score and price (as now), then build the merged list from
  results above a **trust floor** (config), ordered by delivered price, each row showing market,
  seller line, **arrival date** (an Armenian shop is tomorrow; China sea is ~1.5 months) and the reason.
  The 🏆 pick says which trade it made ("€4 dearer than China, 5 weeks sooner, sold by Amazon").
- `same_product` grouping across markets (token overlap exists in `pricing.same_product`) so the same
  charger on Amazon and 1688 is one row with two prices.
- Mini App: the existing China screen becomes the generic results screen (it reads the saved answer
  file, which the engine will own).

`/china` and `/amazon` stay as shortcuts to one market.

---

## 5. Where the data lives and what a run touches

- Queue, locks, `last_<chat>.json` (24 h): JSON files like China (`.browser/china_data/`; the engine
  extraction renames the folder with a migration note).
- Browser state: `.browser/market` (signed out, postcodes). No credentials anywhere.
- No Sheets or database writes in P1. 👁 Watch adds the item to the watch list with the exact
  `/dp/<ASIN>` link (the Market watch then re-reads it nightly with the same parser's cousin in
  `market/readers.py`) — **P1 reuses `market/bot` add path**, no new storage.
- No transaction, lock or handle is held across the model calls (CLAUDE.md §3).

---

## 6. Cost: quota, time, and the Amazon-side risk

### 6.1 Max quota

| | `/china` (measured, CHINA_SEARCH §8) | `/amazon` (estimate — to be measured in P1) |
|---|---|---|
| Browsing | ~1.3 M cache-read tokens per site (PDD 2.0 M, 1688 1.75 M), list-price equivalent ~$1.3 per site | **0** — Playwright + parser |
| Model calls | one per site (read) + plan + phrasing | 2: plan (translate to DE/IT, category, questions) and the 🏆 reason. No browsing tools, a small prompt of final numbers. Cheaper model by `--model` as China P1 did (the configured fast model); fixed extraction scripts are not needed because the model does not read pages |
| Estimate | ~$3.7 list-price equivalent for three sites | tens of thousands of tokens at most per run, i.e. small next to China |

Rules kept from China: the model gets final numbers and "do not recalculate"; any answer that fails
validation is rejected and re-asked once, then falls back to a deterministic default (the 🏆 reason
becomes the template sentence). A model failure never changes a number.

### 6.2 Time

Per run, estimated: 4 stores × (1 search + 3 product pages) = 16 page loads × (3–6 s pause + load) ≈
3–5 minutes with the polite pauses, in the queue with one browser job at a time. Measured in P1.

### 6.3 Amazon terms and anti-bot risk (stated plainly)

- Amazon's Conditions of Use disallow automated data collection ("robots, data mining"), and the
  Associates programme (docs/VISION.md, stores note) separately forbids price tracking without agreement. This is a
  **private, low-volume, read-only** family tool, not a product; the risk is a check page or a block of
  the bot's IP/profile, not legal action against a family — but the owner decides (§8 q4).
- Rules in code, not in a prompt: **read-only; never log in; never click add-to-cart/buy; never try
  to pass a check page, CAPTCHA or "continue" screen** (the existing `scrapers/market.blocked_reason`
  list is the detector; a hit marks that store `blocked` for the rest of the run and the day);
  one attempt per URL; 3–6 s between pages; a cap of N searches per day (default 10) and a
  cool-down of 24 h for a store after a block; no retries in a loop; no proxy, stealth plugin or solver.
- The answer says what it could not read ("Amazon DE blocked this run — 2 stores answered").
- No affiliate tags on links, ever (the Associates rules require disclosure and are not worth the exposure).
- Purchases are never made by the bot. The owner orders in the Amazon app/site with his own account to
  the forwarder address.

---

## 7. Phases (one per session, CLAUDE.md §9; each ends with `pytest` green, `ruff` clean, a decision entry, a doc change and a phone demo)

| Phase | Content | **Done means** |
|---|---|---|
| **P0 Discovery** (this document) | Captures, findings table, engine plan, questions | Brief + fixtures + decision 100 + ROADMAP row committed; owner has the questions (§8) |
| **P1 Amazon UK/DE/IT text search** | `amazon/` (`bot`, `parse`, `search`, `pricing`, `trust`, `report`); `prompts/amazon_plan.md`; `jobs/amazon_search.py`; postcode check; card parser + product-page parser against `tests/fixtures/amazon/`; seller trust (§1.1); priced by `market.pricing.quote`; rich answer, 📱 card entry, 👁 Watch with exact link; `/amazon` and a button in 🌍 Market; `listener.py` change as its own additive commit | A real `/amazon usb c charger 65w` and `/amazon baby romper 6-12 months` from **both** phones return ranked results for UK, DE and IT with seller line, delivered AMD total and reason per result; a forced check page degrades to one skipped store; parser tests pass on all 12 EU fixtures including the rejection path (no price → "not read", never a guess); a measured quota/time line is written into §6 |
| **P1b Extract the engine** (needs P1 demo-passed) | §3.2 refactor: `find/`, adapters for China and Amazon; golden files | China output byte-identical on fixtures; both `/china` and `/amazon` live-run from the phone; docs (ARCHITECHTURE.MD, this brief §3) updated |
| **P2 Amazon US** | US search with the fallback of §2.3; if the owner decides US search is unreliable, US by `/dp` links and "paste a link" only; US-specific lines (`Ships from`, inches/lb, no sales tax, Delaware); `FREE delivery … over $35` threshold handled as text, never a number | `/amazon` returns US results (or the stated fallback) on both phones; US dp parser tests on the 4 US fixtures + the 10-29 `amazon_us_dp.html` |
| **P3 Armenian shops** | Discovery table (which shops are readable) → `adapters/vega.py` and the shops that pass; `local` quote with no forwarder/customs; stock/pickup lines | `/find` style query on the phone returns Armenian shop results with ֏ prices and "in stock"; unreadable shops listed as such |
| **P4 Russia (Wildberries, Ozon)** | Owner's-Chrome adapters (China reader path); customs/delivery rules **verified from the sources and recorded in `market/customs.md` with the date**; both direct and via-Russia-warehouse routes | A real query returns WB and Ozon results with both routes and a total; a block page degrades to a "open it in your Chrome" line, never a bypass |
| **P5 Merge `/find`** | `/find`, market chooser in the Mini App, cross-market ranking with trust floor and arrival date, cross-market same-product rows | One query on the phone returns a merged list from at least China, Amazon and one Armenian shop, each row with market, seller line, arrival date and reason; `/china`, `/amazon` still work |

---

## 8. Questions for the owner (they change the build)

1. **US in the default?** US search worked today but redirected to a check page on 2026-10-29. Include
   it by default with automatic fallback to "send me links" (recommended), or search UK/DE/IT only and
   make US a button?
2. **Seller rule.** Show third-party sellers with the trust reason (recommended), or add a
   switch **"Amazon only"** (sold or dispatched by Amazon) — default off, on a button? Do you want
   **Prime** shown at all? (It does not apply to a warehouse parcel.)
3. **How wide.** Default top **3 per store** get a product-page read (seller, weight, exact delivery);
   ≈ 4–5 minutes and 16 page loads. Wider (top 5, ~7 minutes) or narrower (top 2)?
4. **Amazon terms.** Their conditions disallow robots. Accept the risk for a private, low-volume,
   read-only tool with the limits in §6.3 (≤ 10 searches a day, 24 h pause after any check page,
   never logged in)? A block would only affect the bot's browser, not your Amazon account.
5. **A browser window on the PC.** The bot's browser opens visibly (as the nightly market scan does),
   so a window appears while you work. OK, or should P1 try headless first (a stronger chance of
   check pages — then it falls back to visible)?
6. **Language of the query.** You type English; the plan translates for DE/IT and shows the translated
   words in the answer ("searched `caricatore usb c 65w`"). OK, or search only the English words?
7. **Baby and clothes sizes.** Amazon sizes differ (`68`, `6-9 mesi`, `6-12 months`). The plan asks one
   button question (age/size) before searching clothing. OK?
8. **Where results show first.** Chat answer + 📱 card as `/china` (recommended), or chat only until
   the engine is extracted?
9. **Order of work.** P1 → P1b (extract) → P2… as above, or Armenian shops (P3) before the Amazon US step?
10. **Russia, later (P4).** Wildberries/Ozon need your Chrome on the PC (the bot's browser is blocked).
    Same arrangement as China (a Chrome window runs while you may be using the PC)? Confirm before P4.

---

## 9. P0 results

- Fixtures: `tests/fixtures/amazon/` — 16 trimmed pages + `capture_pages.py` (how they were taken) and
  `trim_capture.py` (how they were cut; removes scripts, hidden inputs, CSRF tokens and session ids).
- Findings: §2.1. Headline: **Amazon UK/DE/IT/US search and product pages are readable by the bot's
  browser with no model**; seller is on the product page only; delivery postcode must be verified per
  run; price did not depend on the address in the one ASIN compared.
- Not done in P0 (on purpose): any parser or feature code; no search was repeated more than twice per
  store; no Amazon account was used.
- Open from P0 for P1: re-compare price across addresses on 3 more ASINs; how many cards a scroll
  loads on electronics pages; whether headless Chromium is served the same pages.
