A family member in Yerevan sent the photo above to find this item in China (Pinduoduo,
Taobao, 1688). Turn the photo into a search plan. Do not browse. Do not invent prices or
numbers; only say what the photo shows.

Their note with the photo (may be empty; it may add a colour, size or wish): {note}

Answer with ONE JSON object and nothing else:
{"is_product": true,
 "seen": "<one short English line: what the item in the photo is>",
 "query_cn": "<a short Chinese search query, 2–6 words, the way Chinese shoppers search for
              exactly this item; include the brand only if it is readable in the photo, and
              the note's wishes (colour, size, power…)>",
 "query_en": "<a short English name of the item, with the note's wishes>",
 "brand_seen": "<the brand only if it is readable on the item or its box, else null>",
 "category": "electronics|clothes|shoes|home|beauty|kids|other"}

If the photo shows nothing that can be bought (a person, a landscape, a document, a
screenshot of a chat), answer {"is_product": false, "seen": "<what it shows>"}.
