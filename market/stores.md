# Stores — where items are watched and how each reaches Yerevan

Edited by hand, reviewed like the plan (docs/briefs/MARKET_WATCH.md §3). The code knows
nothing store-specific beyond its page reader: adding a store = a row here + a reader.

Columns (only the table is read, by market/stores.py):

- **key** — short id used in commands and the Sheet.
- **host** — the link's host; a pasted link is matched to its store by this.
- **reader** — page reader in market/readers.py (`amazon`, `vega`, or `none` = no reader yet).
- **origin** — forwarder warehouse country the store delivers to (`local` = Armenian shop).
- **currency** — the store's own currency (prices are kept in it and converted at the CBA rate).
- **modes** — how it reaches Yerevan: forwarder modes (`air`, `sea`, `truck`), `direct`
  (the store delivers to Armenia itself) or `local`. Every forwarder in market/tariffs.json
  with that origin × mode gets its own line.
- **postcode** — the forwarder warehouse set as the delivery address in the bot's browser
  profile (`python scrapers/market.py --setup`), so in-store shipping is quoted to it. Not
  secrets: these are the forwarders' public warehouse codes (owner, 2026-10-29).

| key | name | host | reader | origin | currency | modes | postcode |
|---|---|---|---|---|---|---|---|
| amazon_us | Amazon US | www.amazon.com | amazon | usa | USD | air, sea | 19720 |
| amazon_uk | Amazon UK | www.amazon.co.uk | amazon | uk | GBP | air | E17 4SX |
| amazon_de | Amazon DE | www.amazon.de | amazon | germany | EUR | air, truck | 82152 |
| amazon_it | Amazon IT | www.amazon.it | amazon | italy | EUR | truck | 70122 |
| wildberries | Wildberries | www.wildberries.ru | none | russia | RUB | direct, air, truck | — |
| ozon | Ozon | am.ozon.com | none | russia | RUB | direct, air, truck | — |
| vega | vega.am | vega.am | vega | local | AMD | local | — |

Other warehouses the forwarders have (stores can be added later): Greece 10437 (Athens),
Spain 08016 (Barcelona), Poland, UAE, Korea.

Wildberries and Ozon: the bot's browser was shown a block page on 2026-10-29 (§9 of the
brief), so their reader is `none` until a real product page is captured; their items run
on the owner's price (`/watch price`) with the store fallback. `ozon.ru` links are read at
`am.ozon.com` (where ozon.ru redirects from Armenia).
