SITE: 1688 (the account sees the international English/USD version).

1. navigate to https://s.1688.com/selloffer/offer_search.htm?charset=utf8&keywords={query_url}
   Scroll down once (computer scroll), then collect offers with javascript_tool:
   const as=[...document.querySelectorAll('a')].filter(a=>/detail\.1688\.com\/offer\/(\d+)/.test(a.href)); const m={}; for(const a of as){const id=a.href.match(/offer\/(\d+)/)[1]; const tx=a.innerText.replace(/\n+/g,'|'); if(!m[id]||tx.length>m[id].length) m[id]=tx;} window.__a=Object.entries(m); window.__a.length
   then read them in chunks: JSON.stringify(window.__a.slice(0,8).map(([i,t])=>[i,t.slice(0,110)]))
   (repeat with slice(8,16), slice(16,24)). Cards show only an English title and a price.
2. For each chosen id: navigate to https://detail.1688.com/offer/<id>.html and read with
   javascript_tool in chunks: document.body.innerText.slice(0,950), slice(950,1900), ...
   Look for: supplier company name and years (入驻N年), supplier tier (e.g. 四星供应链), badges
   ("Factory direct supply", 源头工厂, 实力商家), attributes (插头标准 plug standard, 是否原装,
   品牌, 输出功率), variants ("Applicable model"), price tiers by quantity, minimum order, and
   the "Product weight and size" table: copy the row of the matching variant into weight_text
   (the Weight (g) number with "g", e.g. "180g") and dims_text ("67.50x33.80x86.50") exactly
   as shown — do not fix units.
   Prices on these pages may be in USD ("$"): copy them with the symbol.
   The shipping cost shown is to the account's Yerevan address, NOT China delivery: put
   domestic_delivery_text only if the page says free shipping (包邮 / Free shipping).
   If the attributes contradict the title (e.g. title 65W, attribute 25W), say so in "why".
3. Reviews (first {reviews} chosen ids): use the rating and the reviews shown on the offer
   page (reviewer names are masked; do not copy them).
4. shop_name = the supplier company name.
