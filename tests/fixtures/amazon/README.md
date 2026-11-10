# Amazon search captures (P0, 2026-11-10)

Real pages from the bot's own browser (`.browser/market`, logged out, delivery postcodes set
to the forwarder warehouses, currency = the store's own). 4 stores x 2 queries x
(search page + first result's product page) = 16 files, named `<store>_<query>_<kind>.html`
(`elec` = USB-C charger 65 W, `baby` = baby romper / strampler / tutina).

Cut with `trim_capture.py` (full pages are 1-3 MB): search = the first 8 result cards
(6 organic + up to 2 sponsored) and the "Deliver to" block; product page = title, price block,
reviews summary, badge, buy box (seller, "dispatches from", delivery date) and "Deliver to".
Scripts, styles, hidden inputs, forms, CSRF tokens and session ids are removed; there are no
cookies and no account data (the profile is signed out). Captured with `capture_pages.py`.
Findings: `docs/briefs/AMAZON_SEARCH.md` section 2. Parsers (P1) are written against these files only.
