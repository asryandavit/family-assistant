# Customs — the rule in use (an estimate, always labelled as one)

`rule: default`  ← the switch read by jobs/market_watch.py (`default` or `eaeu_2026`)

## default — what the forwarders' own calculators apply (P0, 2026-10-29)

- Duty-free up to **€200 per parcel** and up to 31 kg (Onex) / 30 kg (Globbing).
- Above €200: **15% of the part over €200** (BuyForYou's calculator uses 16.2%).
- Over the weight limit: Onex — 15% of the whole value + €2 per kg over 31;
  Globbing — the larger of the value duty and €2 per kg over 30.
- Globbing applies no customs on its Russia routes (`customs_method` 0).

Value = item price × qty + the store's delivery to the warehouse, at the CBA rate.
One item = one parcel. Items within 10% of €200 are flagged in the report.

## eaeu_2026 — the EAEU rule from 2026-07-01 (switch, unconfirmed)

5% of the full value, at least €1 per kg, plus 20% VAT on the part over €200.
Not used unless the switch above says `eaeu_2026`.
