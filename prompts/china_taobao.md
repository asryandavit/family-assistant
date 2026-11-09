SITE: Taobao / Tmall. You do NOT browse: the bot's own browser already read the pages and the
text is below. Fill the same JSON from this text only. Never invent anything that is not in
the text; use null when it is not there.

- search_ids: exactly the ids listed under SEARCH CARDS.
- Cards are "title|chips|¥|109|.34|券后价|N人付款|province|city|...|shop name" — the price is
  split ("¥|109|.34" = "¥109.34"): copy it as "¥109.34" into price_text; the label after it
  (券后价 / 补贴价 / 首单价) decides price_kind (券后价 = after_coupon, 首单价 = first_item).
- The chip like "Apple/苹果" is the COMPATIBLE device, not the maker — never the brand.
- The shop name is the last field. 官方旗舰店 = the brand's official store; another
  "...旗舰店" is a flagship but not the official one; 专卖店 = authorised specialty store.
- Product pages (PRODUCT PAGE <id>) give shop rating, guarantees, variants (颜色分类 ...),
  the shown price and, if present, specs and reviews. A page that says 访问异常 shows no
  details: use the card for that id and say so in "why".
- Choose up to {top} results among the ids that have a product page first, then cards.
