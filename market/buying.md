# Buying — how each store's item reaches a forwarder (data, not code)

Edited by hand, like `stores.md` and `forwarders.md` (docs/briefs/CROSS_BORDER.md §3). Read by
`market/buying.py` from X1 on; only the two tables are read. The owner buys **directly on every
site** (2026-11-17): there is no buy-for-me path and no buyout fee.

**This file holds no number used in a total.** Forwarder prices stay in `market/tariffs.json`.
Customs stays in `market/customs.md`. Every total comes from `market.pricing.quote`.

No account data is stored here: no suite codes, names or addresses. Each forwarder's warehouse
address (and the personal code in it) is shown only in the owner's own forwarder account.
None of the four forwarders publishes its warehouse city (checked 2026-11-18), so the steps say
"from your account". They never print an address.

A row whose `checked` date is older than 90 days is shown with "⚠️ buying steps last checked on
<date>". It is still shown, never hidden.

## Stores

Columns:
- **store** — key from `market/stores.md`.
- **warehouse** — the forwarder origin to deliver to (a `market/tariffs.json` origin). Every
  forwarder × mode with that origin is priced, as now.
- **pay** — the buying step, shown as it is.
- **delivery** — what the site's own delivery to the warehouse means. The number, when there is
  one, comes from the result.
- **watch** — the store-specific thing to check before paying.
- **checked** — the date and how the row was verified.

| store | warehouse | pay | delivery | watch | checked |
|---|---|---|---|---|---|
| pinduoduo | china | Buy in the Pinduoduo app yourself | The listing's delivery to your forwarder's China warehouse: 包邮 = free, a ¥ fee as shown, unknown when not shown | Group price (拼单) needs a group; the single price (单独购买) is what you pay alone — both are shown | 2026-11-18, from /china results (group and single kept apart since decision 090) |
| taobao | china | Buy on Taobao / Tmall yourself (the answer gives a search link; Taobao is not read by the bot) | Same as Pinduoduo: 包邮 = free, otherwise the fee as shown | Coupon prices (券后) need the coupon claimed at checkout | 2026-11-18, from /china results (`taobao_mode: link`) |
| 1688 | china | Buy on 1688 yourself | The listing's "Shipping cost ¥N" to your forwarder's China warehouse, or free over the seller's limit | 1688 is wholesale: the minimum order (起批量, e.g. "1个起批") and quantity price tiers are on the page and shown on each result | 2026-11-18, from /china results (`min_order_text` captured on every 1688 result) |
| amazon_uk | uk | Buy on amazon.co.uk with your card | Amazon's delivery to your forwarder's UK warehouse (E17 4SX), as shown. "FREE on your first order" is a condition, not counted | Seller and "Dispatched by Amazon" line, shown on every result | 2026-11-18, from /amazon P1 (AMAZON_SEARCH §11) |
| amazon_de | germany | Buy on amazon.de with your card | Amazon's delivery to your forwarder's Germany warehouse (82152), as shown. "Kostenlose Lieferung" on a first order is a condition, not counted | Seller and "Dispatched by Amazon" line, shown on every result | 2026-11-18, from /amazon P1 |
| amazon_it | italy | Buy on amazon.it with your card | Amazon's delivery to your forwarder's Italy warehouse (70122), as shown. A first-order free delivery is a condition, not counted | Seller and "Dispatched by Amazon" line, shown on every result | 2026-11-18, from /amazon P1 |

## Forwarder restrictions

Read by X2's restriction-aware route. **unknown** means the forwarder publishes no rule. Then the
answer says "check with <forwarder> before ordering" and never treats the route as allowed or
refused.

Columns:
- **forwarder**
- **item** — `battery`, `liquid`, `magnet` or `aerosol` (the flags `/china` already sets).
- **modes** — the modes the rule applies to (`all` when the site does not split by mode).
- **rule** — `refused`, `limited` (allowed under a condition, in the note) or `unknown`.
- **note** — the condition, as the site states it.
- **source** — page and date.

| forwarder | item | modes | rule | note | source |
|---|---|---|---|---|---|
| globbing | battery | all | limited | Lithium-ion batteries only inside the equipment and up to 100 Wh; loose batteries and power banks are not allowed | am.globbing.com/en/restricted-products, 2026-11-18 |
| globbing | liquid | all | limited | Perfume over 200 ml is not allowed; there is no general rule for other liquids (chemicals, acetone, glue are listed as not allowed) | am.globbing.com/en/restricted-products, 2026-11-18 |
| globbing | magnet | all | refused | "Magnet" and equipment with many magnets are listed under explosive materials | am.globbing.com/en/restricted-products, 2026-11-18 |
| globbing | aerosol | all | refused | "Devices and objects containing pressure" | am.globbing.com/en/restricted-products, 2026-11-18 |
| onex | battery | all | unknown | No prohibited-items page; FAQ has none | onex.am/en/pages/faq, 2026-11-18 |
| onex | liquid | all | unknown | same | onex.am/en/pages/faq, 2026-11-18 |
| onex | magnet | all | unknown | same | onex.am/en/pages/faq, 2026-11-18 |
| onex | aerosol | all | unknown | same | onex.am/en/pages/faq, 2026-11-18 |
| buyforyou | battery | all | unknown | No rules page; terms link is not a page | buyforyou.am, 2026-11-18 |
| buyforyou | liquid | all | unknown | same | buyforyou.am, 2026-11-18 |
| buyforyou | magnet | all | unknown | same | buyforyou.am, 2026-11-18 |
| buyforyou | aerosol | all | unknown | same | buyforyou.am, 2026-11-18 |
| easytrans | battery | all | unknown | The site renders only in a browser; no rule read | easytrans.am, 2026-11-18 |
| easytrans | liquid | all | unknown | same | easytrans.am, 2026-11-18 |
| easytrans | magnet | all | unknown | same | easytrans.am, 2026-11-18 |
| easytrans | aerosol | all | unknown | same | easytrans.am, 2026-11-18 |
