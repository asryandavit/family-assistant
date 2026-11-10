"""Amazon pages -> offers, written ONLY against real captures (tests/fixtures/amazon/*.html,
CLAUDE.md §8). No model reads a page. A field the page does not show is None - "not read" -
never a guess: no price means no total.

Common offer shape (docs/briefs/AMAZON_SEARCH.md §3.2; the P1b engine reads the same keys):

    {market, site, id, url, title, price, currency, price_kind, list_price,
     delivery_fee, delivery_text, delivery_eta,
     seller: {name, class, evidence}, fulfilment, rating, reviews, sales_text, badges[], sponsored,
     weight_kg, dims_cm, restrictions[], category, notes[]}

seller.class: amazon | dispatched_by_amazon | third_party | unread (docs brief §1.1).
"""
import html as htmllib
import re
from urllib.parse import quote_plus

from market import readers

MARKET = "amazon"
HOSTS = {"uk": "www.amazon.co.uk", "de": "www.amazon.de", "it": "www.amazon.it",
         "us": "www.amazon.com"}
CURRENCY = {"uk": "GBP", "de": "EUR", "it": "EUR", "us": "USD"}
NAME = {"uk": "Amazon UK", "de": "Amazon DE", "it": "Amazon IT", "us": "Amazon US"}
FLAG = {"uk": "🇬🇧", "de": "🇩🇪", "it": "🇮🇹", "us": "🇺🇸"}

AMAZON, DISPATCHED, THIRD, UNREAD = "amazon", "dispatched_by_amazon", "third_party", "unread"

# same as china/parse.py: sanity ranges so a mis-parse can never become a price
MAX_PRICE = 20000.0

ABBR = {"jan": "january", "feb": "february", "mar": "march", "apr": "april", "jun": "june",
        "jul": "july", "aug": "august", "sep": "september", "sept": "september",
        "oct": "october", "nov": "november", "dec": "december"}


# ------------------------------------------------------------------ small helpers

def text(fragment):
    """Visible text of an HTML fragment (tags removed, entities decoded, spaces folded)."""
    t = htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))
    return re.sub(r"[\s‌‎‏]+", " ", t).strip()


def count(s):
    """'2K' / '2.9K' / '14.4K' / '1.2M' / '2,061' / '(150)' / '150 ratings' -> int, or None."""
    m = re.search(r"(\d[\d.,]*)\s*([KkMm])?\b", str(s or ""))
    if not m:
        return None
    num, suffix = m.group(1), (m.group(2) or "").lower()
    if suffix:
        try:
            v = float(num.replace(",", "."))
        except ValueError:
            return None
        return int(round(v * (1000 if suffix == "k" else 1000000)))
    digits = re.sub(r"[.,]", "", num)
    return int(digits) if digits.isdigit() else None


def money(s, expect_currency=None):
    """(amount, currency) from a price string; (None, currency) when it is not a usable
    price for expect_currency - never a number in the wrong currency."""
    amount, cur = readers.parse_money(s)
    if amount is None or not 0 < amount <= MAX_PRICE:
        return None, cur
    if expect_currency and cur and cur != expect_currency:
        return None, cur
    return amount, cur


def stars(s):
    m = re.search(r"(\d(?:[.,]\d)?)\s*out of 5", str(s or ""))
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return v if 0 <= v <= 5 else None


def eta(s, today):
    """(earliest, latest) dates from 'Fri 13 Nov' / 'Friday, 13 November' / '17 - 19 November' /
    'Tomorrow, 11 Nov'; None when no date is shown. Abbreviated months are spelled out first
    (market.readers.parse_delivery knows full names only)."""
    if not s:
        return None
    t = re.sub(r"\b([A-Za-z]{3,4})\b", lambda m: ABBR.get(m.group(1).lower(), m.group(1)), s)
    try:
        return readers.parse_delivery(t, today)
    except (StopIteration, ValueError):
        return None


def delivery(s, currency=None):
    """(fee, note) from a delivery line. fee 0.0 = free; a number = shown fee; None = unknown,
    with a note that says why. 'FREE delivery ... on your first order' is a condition, not a
    fee (same rule as market/readers.py): unknown, not zero."""
    t = " ".join((s or "").split())
    if not t:
        return None, "delivery not shown"
    low = t.lower()
    if low.startswith("free"):
        if re.search(r"first (?:eligible )?order|over [£€$]|orders? (?:shipped by amazon )?over|"
                     r"eligible orders", low):
            return None, "free on a first/eligible order only - real cost unknown"
        return 0.0, "free delivery"
    m = re.search(r"([£€$]\s?[\d.,]+)\s+delivery", t)
    if m:
        amount, _ = money(m.group(1), currency)
        if amount is not None:
            return amount, "delivery %s" % m.group(1).replace(" ", "")
    return None, "delivery fee not read"


# ------------------------------------------------------------------ delivery location

def deliver_to(html):
    """The 'Deliver to' line the page shows ('London E174SX', '70122'), or ''."""
    m = re.search(r'id="glow-ingress-line2"[^>]*>(.*?)</span>', html or "", re.S)
    if m:
        return text(m.group(1))
    m = re.search(r'id="glow-ingress-block"[^>]*>(.*?)</div>', html or "", re.S)
    return re.sub(r"^\s*Deliver to\s*", "", text(m.group(1))) if m else ""


def postcode_ok(line, postcode):
    """True when the page's Deliver-to line holds the warehouse postcode (spaces ignored)."""
    if not line or not postcode:
        return False
    return postcode.replace(" ", "").lower() in line.replace(" ", "").lower()


# ------------------------------------------------------------------ search cards

CARD_SPLIT = re.compile(r'(?=<div[^>]+data-component-type="s-search-result")')
BADGES = (("Amazon's Choice", "amazons_choice"), ("Best Seller", "best_seller"),
          ("Limited time deal", "deal"), ("Amazon Exclusive", "exclusive"),
          ("New on Amazon", "new"), ("Small Business", "small_business"),
          ("Climate Pledge Friendly", "climate"))
BOUGHT_RE = re.compile(r"(\d[\d.,]*[KkMm]?\+?)\s+bought in past month", re.I)


def _price_of(card, strike, currency):
    if strike:
        pat = r'<span class="a-price a-text-price"[^>]*data-a-strike="true"[^>]*>\s*<span class="a-offscreen">([^<]*)<'
    else:
        pat = r'<span class="a-price"[^>]*>\s*<span class="a-offscreen">([^<]*)<'
    m = re.search(pat, card)
    return money(m.group(1), currency) if m else (None, None)


def _title(card):
    """'Brand Title'. Some cards carry two <h2>: a short brand heading (no aria-label) and the
    title (with one, 'Sponsored Ad – ' prefix on sponsored cards); the brand is added in front
    unless the title already starts with it (captured 2026-11-10: it_baby Gerber, uk_baby Lilcutie)."""
    main = None
    for m in re.finditer(r'<h2\b[^>]*\baria-label="([^"]+)"', card):     # the attribute survives a cut-off card
        main = htmllib.unescape(m.group(1)).strip()
        break
    heads = re.findall(r"<h2\b([^>]*)>(.*?)</h2>", card, re.S)
    brand = next((text(b) for a, b in heads if "aria-label=" not in a and text(b)), None)
    if main is None:
        main = max((text(b) for _, b in heads), key=len, default="") or None
    if main is None:
        return None
    main = re.sub(r"^Sponsored Ad\s*[–-]\s*", "", main)
    if brand and not main.lower().startswith(brand.lower()):
        return "%s %s" % (brand, main)
    return main


def parse_card(card, site, today):
    """One search-result chunk -> offer dict, or None when it has no ASIN (not a product)."""
    m = re.search(r'data-asin="([A-Z0-9]{10})"', card[:600])
    if not m:
        return None
    asin = m.group(1)
    currency = CURRENCY[site]
    notes = []
    price, shown_cur = _price_of(card, False, currency)
    if price is None:
        raw = re.search(r'<span class="a-price"[^>]*>\s*<span class="a-offscreen">([^<]*)<', card)
        if raw and shown_cur and shown_cur != currency:
            notes.append("price shown in %s, expected %s - not used" % (shown_cur, currency))
        else:
            notes.append("price not read")
    list_price, _ = _price_of(card, True, currency)
    if list_price is not None and price is not None and list_price <= price:
        list_price = None
    txt = text(card)
    kind = "list"
    vm = re.search(r"You pay\s+([£€$][\d.,]+)\s+with voucher", txt)
    if vm:
        kind = "voucher_available"
        notes.append("voucher: you pay %s - price shown is before the voucher" % vm.group(1))
    rating = stars(txt)
    reviews = None
    cm = re.search(r'alf-customer-ratings-count-component.*?aria-label="([\d.,]+)\s*ratings?"', card, re.S)
    if cm:
        reviews = count(cm.group(1))
    else:
        cm = re.search(r'aria-label="([\d.,]+)\s*ratings?"', card)
        if cm:
            reviews = count(cm.group(1))
        else:
            cm = re.search(r'alf-customer-ratings-count-component.*?aria-hidden="true"[^>]*>\(([^)]*)\)', card, re.S)
            reviews = count(cm.group(1)) if cm else None
    bm = BOUGHT_RE.search(txt)
    sales_text = bm.group(0) if bm else None
    badges = [key for phrase, key in BADGES if phrase.lower() in txt.lower()]
    sponsored = "puis-sponsored-label-text" in card or "AdHolder" in card[:600]
    dm = re.search(r'udm-primary-delivery-message[^>]*>(.*?)</div>\s*</div>', card, re.S)
    dtext = text(dm.group(1)) if dm else ""
    fee, fee_note = delivery(dtext, currency)
    link = "https://%s/dp/%s" % (HOSTS[site], asin)
    return {
        "market": MARKET, "site": site, "id": asin, "url": link, "title": _title(card),
        "price": price, "currency": currency, "price_kind": kind, "list_price": list_price,
        "delivery_fee": fee, "delivery_text": dtext, "delivery_note": fee_note,
        "delivery_eta": eta(dtext, today),
        "seller": {"name": None, "class": UNREAD, "evidence": "product page not read"},
        "fulfilment": None, "rating": rating, "reviews": reviews, "sales_text": sales_text,
        "sales": count(bm.group(1)) if bm else None, "badges": badges, "sponsored": sponsored,
        "weight_kg": None, "dims_cm": None, "restrictions": [], "category": None, "notes": notes,
    }


def parse_cards(html, site, today, limit=None):
    """Offers from a search page in page order (sponsored kept and marked). Duplicate ASINs
    (a sponsored repeat of an organic card) keep the first."""
    out, seen = [], set()
    for chunk in CARD_SPLIT.split(html or "")[1:]:
        o = parse_card(chunk[:30000], site, today)
        if o and o["id"] not in seen:
            seen.add(o["id"])
            out.append(o)
        if limit and len(out) >= limit:
            break
    return out


# ------------------------------------------------------------------ product page

def _feature(html, id_):
    """(label, value) of one buy-box row ('Sold by', 'TOPADRE Tech EU'), or (None, None)."""
    i = html.find('id="%s"' % id_)
    if i < 0:
        return None, None
    seg = html[i + 20:i + 6000]
    end = re.search(r'<div id="\w+_feature_div"', seg)
    if end:
        seg = seg[:end.start()]
    lab = re.search(r'a-color-tertiary">(.*?)</span>', seg, re.S)
    val = re.search(r'offer-display-feature-text-message">(.*?)</(?:a|span)>', seg, re.S)
    return (text(lab.group(1)) if lab else None, text(val.group(1)) if val else None)


AMAZON_NAME_RE = re.compile(r"amazon(?:\.[a-z.]+|\s+(?:eu|uk|italia|export|services)\b.*)?$")


def is_amazon(name, names):
    """The seller is Amazon itself (config list, or an 'Amazon EU ...' style name); used-goods
    'Amazon Warehouse' is a reseller of returns and does not count."""
    n = " ".join((name or "").lower().split())
    return n in set(names) or bool(AMAZON_NAME_RE.match(n) and "warehouse" not in n)


def seller_of(merchant, fulfiller, names):
    """seller dict from the two buy-box rows: merchant = ('Sold by'|'Shipper / Seller', name),
    fulfiller = ('Dispatches from'|'Ships from', name) or (None, None)."""
    (mlab, mname), (flab, fname) = merchant, fulfiller
    if not mname:
        return {"name": None, "class": UNREAD, "evidence": "seller not shown on the page"}
    if mlab and mlab.lower().startswith("shipper"):
        cls = AMAZON if is_amazon(mname, names) else THIRD
        return {"name": mname, "class": cls,
                "evidence": "%s %s" % (mlab, mname)}
    if is_amazon(mname, names):
        return {"name": mname, "class": AMAZON, "evidence": "%s %s" % (mlab or "Sold by", mname)}
    if fname and is_amazon(fname, names):
        return {"name": mname, "class": DISPATCHED,
                "evidence": "%s %s · %s %s" % (mlab or "Sold by", mname, flab, fname)}
    ev = "%s %s" % (mlab or "Sold by", mname)
    if fname:
        ev += " · %s %s" % (flab, fname)
    else:
        ev += " · dispatch not shown"
    return {"name": mname, "class": THIRD, "evidence": ev}


UNAVAILABLE = ("currently unavailable", "out of stock", "temporarily out of stock", "no featured offers")


def out_of_stock(html):
    """True only when the page's availability message or its out-of-stock block says so. The
    words 'Currently unavailable.' also sit in script strings of in-stock pages (captured
    2026-11-10), so a text search over the page is wrong."""
    if 'id="outOfStock"' in html:
        return True
    i = html.find('id="availability"')
    if i < 0:
        return False
    m = re.search(r'primary-availability-message[^>]*>(.*?)</span>', html[i:i + 3000], re.S)
    return bool(m) and text(m.group(1)).lower().startswith(UNAVAILABLE)


def _product_delivery(html, currency):
    """(line, fee, note, date text) from the page's first delivery message. Amazon writes it as
    data attributes (data-csa-c-delivery-price / -time / -condition, captured 2026-11-10), so the
    fee and the date are read from fields, not cut out of prose."""
    tag = re.search(r'<span[^>]*data-csa-c-content-id="DEXUnifiedCXPDM"[^>]*>', html)
    if not tag:
        dm = re.search(r'id="deliveryBlockMessage"[^>]*>(.*?)(?:<div id="cip|$)', html, re.S)
        line = re.split(r"\s+(?:Order within|Details|Deliver to)\b", text(dm.group(1)) if dm else "")[0]
        fee, note = delivery(line.strip(" ."), currency)
        return line.strip(" ."), fee, note, line
    a = {k: htmllib.unescape(v) for k, v in re.findall(r'data-csa-c-([\w-]+)="([^"]*)"', tag.group(0))}
    price, when, cond = a.get("delivery-price", ""), a.get("delivery-time", ""), a.get("delivery-condition", "")
    line = " ".join(x for x in (price + " delivery" if price else "", when, cond) if x)
    fee, note = delivery(line, currency)
    return line, fee, note, when


def parse_product(html, site, today, names=()):
    """Product page -> the fields only a /dp/ page gives. price None = not read. Weight and
    size come from the details tables via market.readers (verified on full pages in
    tests/fixtures/market/amazon_*_dp.html); the trimmed Amazon fixtures do not carry them."""
    currency = CURRENCY[site]
    notes = []
    price = None
    seg = ""
    i = html.find('id="corePrice_feature_div"')
    if i >= 0:
        seg = html[i:i + 4000]
        end = seg.find('id="averageCustomerReviews_feature_div"')
        seg = seg[:end] if end > 0 else seg
    pm = re.search(r'apex-pricetopay-value[^>]*>\s*<span class="a-offscreen">([^<]*)<', seg)
    if pm:
        price, _ = money(pm.group(1), currency)
    if price is None:
        notes.append("price not read")
    lm = re.search(r'a-text-price"[^>]*data-a-strike="true"[^>]*>\s*<span class="a-offscreen">([^<]*)<', seg)
    list_price = money(lm.group(1), currency)[0] if lm else None
    if list_price is not None and price is not None and list_price <= price:
        list_price = None
    title = re.search(r'id="productTitle"[^>]*>(.*?)</span>', html, re.S)
    rm = re.search(r'id="acrPopover"[^>]*title="([^"]*)"', html)
    cm = re.search(r'id="acrCustomerReviewText"[^>]*aria-label="([\d.,]+)\s*Reviews?"', html)
    dline, fee, fee_note, when = _product_delivery(html, currency)
    merchant = _feature(html, "merchantInfoFeature_feature_div")
    fulfiller = _feature(html, "fulfillerInfoFeature_feature_div")
    weight = dims = None
    try:
        details = readers.parse_amazon(html, today)
        weight, dims = details.get("weight_kg"), details.get("dims_cm")
    except Exception:  # noqa: BLE001 - a details parse fault must not lose the seller line
        pass
    stock = out_of_stock(html)
    return {
        "title": text(title.group(1)) if title else None, "price": price, "currency": currency,
        "list_price": list_price, "rating": stars(rm.group(1)) if rm else None,
        "reviews": count(cm.group(1)) if cm else None,
        "delivery_text": dline, "delivery_fee": fee, "delivery_note": fee_note,
        "delivery_eta": eta(when, today),
        "seller": seller_of(merchant, fulfiller, names),
        "fulfilment": fulfiller[1] if fulfiller[1] else None,
        "weight_kg": weight, "dims_cm": dims, "in_stock": not stock, "deliver_to": deliver_to(html),
        "notes": notes,
    }


# ------------------------------------------------------------------ query helpers

SPEC_RE = re.compile(r"^\d+(?:[.,]\d+)?\s?(?:w|kw|gb|tb|mah|ml|l|cm|mm|v|a)$", re.I)


def spec_tokens(description):
    """Number+unit tokens typed by the person ('65w', '20000mah', '500 ml') - found by code in
    their own words; titles must carry them. Tokens are lower-case without spaces."""
    t = re.sub(r"(\d)\s+(w|kw|gb|tb|mah|ml|l|cm|mm|v|a)\b", r"\1\2", description or "", flags=re.I)
    return sorted({w.lower().replace(",", ".") for w in re.findall(r"[\w.,]+", t) if SPEC_RE.match(w)})


def has_tokens(title, tokens):
    t = re.sub(r"(\d)\s+(w|kw|gb|tb|mah|ml|l|cm|mm|v|a)\b", r"\1\2", (title or "").lower())
    return all(tok in t for tok in tokens)


def search_url(site, query):
    return "https://%s/s?k=%s" % (HOSTS[site], quote_plus(query))


def product_url(site, asin):
    return "https://%s/dp/%s" % (HOSTS[site], asin)


ASIN_RE = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})")


def asin_of(url):
    m = ASIN_RE.search(url or "")
    return m.group(1) if m else None
