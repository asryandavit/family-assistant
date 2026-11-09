SITE: 1688 — PHOTO SEARCH (以图搜货; the account sees the international English/USD version).
The family sent a photo of the item. You search 1688 with that photo; you never type.

1. navigate to https://s.1688.com/selloffer/offer_search.htm?charset=utf8&keywords={query_url}
   Take ONE screenshot and click the "Image Search" button (camera icon, right of the orange
   Search button). A panel opens with a hidden file input.
   Use find with the query "image file input" to get its ref, then call file_upload with that
   ref and paths ["{image_path}"]. Never click the file input itself (it opens a file dialog).
   Wait 3 s, take ONE screenshot: a preview of the photo with a "Search for" button appears —
   click it. Wait 4 s. The page is now air.1688.com/kapp/1688-search/pc-image-search/.
   If the upload is refused, or no result page appears, answer status "error" with the reason
   in "notice" (do not fall back to a word search — the bot does that itself).
   Read the result cards with javascript_tool (they are not links; the offer id is the last
   number of data-renderkey):
   window.__a=[...document.querySelectorAll('[class*=searchOfferWrapper]')].map(d=>[(d.getAttribute('data-renderkey')||'').split('_').pop(), d.innerText.replace(/\n+/g,'|')]); window.__a.length
   then in chunks: JSON.stringify(window.__a.slice(0,8).map(([i,t])=>[i,t.slice(0,110)]))
   (repeat with slice(8,16), slice(16,24)). Cards show an English title, ¥ price and
   "Repurchase Rate". Results are VISUALLY SIMILAR, not always the same item: choose only
   listings of the SAME KIND of item as the photo (and the description below); skip anything
   else (a dock or a cable when the photo is a charger). search_ids = every id you read.
