SITE: Pinduoduo (mobile web, logged in).

1. navigate to https://mobile.yangkeduo.com/search_result.html?search_key={query_url}
   If the page is a login page (登录 / 手机号) answer status "login".
2. Read the listings with javascript_tool, in chunks (repeat with slice(8,16), slice(16,24)):
   const L=window.rawData.stores.store.data.ssrListData.list; JSON.stringify(L.slice(0,8).map(i=>[i.goodsID,i.goodsName,i.priceInfo,i.pricePrefixInfo||'',i.salesTip,(i.tagList||[]).map(t=>t.text).join('/')]))
   The listing price is usually the CHEAPEST variant, not the one described — use it only to
   choose which listings to open.
3. For each chosen id: navigate to https://mobile.yangkeduo.com/goods.html?goods_id=<id>, then
   read the page without the buyers' group list:
   const t=document.body.innerText; const i=t.lastIndexOf('去拼单'); t.slice(i>0?i:0, (i>0?i:0)+950)
   (shop name, 品牌授权, guarantees, 商品评价(N), the spec block). Then open the variant picker:
   find the bottom button "发起拼单" (or the price bar) and click it ONCE, then list options and
   read the price of each candidate option with:
   const want=['<exact option text>']; const out=[]; for(const n of want){const el=[...document.querySelectorAll('div,span')].filter(e=>e.innerText&&e.innerText.trim()===n).pop(); if(!el){out.push([n,'no el']);continue;} el.click(); await new Promise(r=>setTimeout(r,800)); const t=document.body.innerText; const i=t.indexOf('已选'); out.push(t.slice(i-25,i+40).replace(/\n+/g,' '));} out
   The option list: const t=document.body.innerText; const i=t.indexOf('已选'); t.slice(i,i+600)
   Do not confirm anything; navigate away to close it.
   PDD web shows only the group price (拼单): price_kind "after_coupon" or "group";
   single_price_text null.
   IF the product page hides the price ("前往APP查看价格", a price like "1??.??", no buy bar
   or no picker): this is NOT a check page — do not stop. Open at most one more product page
   to confirm, then stop opening product pages and answer status "ok" with results built
   from the SEARCH LISTINGS: price_text = the listing's shown price with its prefix (e.g.
   "券后¥109"), price_kind "list", variant null, marks from the listing tags, sales_text
   from salesTip, and why starting "listing price — may be a cheaper variant; the product
   page shows prices only in the PDD app". Put the notice text in "notice". Still do step 4
   (reviews) for the first {reviews} chosen ids — the reviews page is separate from the price.
4. Reviews (first {reviews} chosen ids): navigate to
   https://mobile.yangkeduo.com/goods_comments.html?goods_id=<id> and read
   document.body.innerText.slice(0,950) and, after one scroll, slice(950,1900). The top shows
   the filters with counts — 全部(N) is review_count_text, 图/视频(N) is
   photo_review_count_text — and tag chips with counts
   (质量好(19) ...; negative chips like 质量差 / 不充电 / 发热 count as complaints). If a 差评
   or 追加 (follow-up, written after use) filter is shown, click it once and read its first
   reviews too: they matter most. Reviews show "型号：..." — prefer reviews of the matching
   variant. Do not copy reviewer names. If this page is a login or check page, set
   reviews_read false for that listing and go on.
