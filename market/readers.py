"""Product-page parsers, one per store family, written against real captures
(tests/fixtures/market/amazon_*_dp.html, vega_product.html; CLAUDE.md §8).

parse(store, html, today) -> offer dict, or {"status": "gone"} for a removed product.
An offer always says what it could not read: price None means "not read", never a guess.

    {"status": "ok", "title", "price", "currency", "shipping" (store currency; None = unknown),
     "shipping_note", "delivery": (earliest, latest) dates or None, "in_stock": True/False/None,
     "stock_text", "weight_kg", "dims_cm", "size_source", "deliver_to"}

Wildberries and Ozon: no real product page could be captured on 2026-10-29 (both showed the
bot a block page), so their price parsers are not written — PARSERS has no entry, and
parse() returns status "no_parser". Block pages are recognised in scrapers/market.py.
"""
import html as htmllib
import json
import re
from datetime import date

MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"])}
SYMBOLS = {"$": "USD", "£": "GBP", "€": "EUR", "֏": "AMD", "₽": "RUB", "¥": "CNY"}
OUT_OF_STOCK = ("currently unavailable", "out of stock", "temporarily out of stock",
                "non disponibile", "derzeit nicht verfügbar", "nicht auf lager")


def _text(fragment):
    return re.sub(r"[\s‌‎‏]+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))).strip()


def parse_money(s):
    """'$1,234.56' / '€144.95' / '144,95 €' / '16 900 ֏' -> (amount, currency) or (None, None)."""
    if not s:
        return None, None
    s = s.replace("\xa0", " ").strip()
    cur = next((code for sym, code in SYMBOLS.items() if sym in s), None)
    num = re.sub(r"[^\d.,]", "", s)
    if not num or not re.search(r"\d", num):
        return None, cur
    if "," in num and "." in num:
        dec = "," if num.rfind(",") > num.rfind(".") else "."
        num = num.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in num:
        head, _, tail = num.rpartition(",")
        num = (head.replace(",", "") + "." + tail) if len(tail) == 2 else num.replace(",", "")
    elif num.count(".") > 1 or (num.count(".") == 1 and len(num.rpartition(".")[2]) == 3):
        num = num.replace(".", "")
    try:
        return float(num), cur
    except ValueError:
        return None, cur


def parse_delivery(text, today):
    """'November 4 - 6' / '21 - 24 November' / 'Tuesday, 3 November' / 'October 30 - November 2'
    -> (earliest, latest) on or after today (the year rolls over in December), or None."""
    if not text:
        return None
    seq = []                                   # ("m", month) / ("d", day) in reading order
    for tok in re.findall(r"[a-z]+|\d+", text.lower()):
        if tok.isdigit() and 1 <= int(tok) <= 31:
            seq.append(("d", int(tok)))
        elif tok in MONTHS:
            seq.append(("m", MONTHS[tok]))
    if not any(k == "d" for k, _ in seq) or not any(k == "m" for k, _ in seq):
        return None
    # US style "November 4 - 6": a day takes the last month before it.
    # UK/EU style "21 - 24 November": a day takes the next month after it.
    month_first = seq[0][0] == "m"
    out = []
    for i, (kind, v) in enumerate(seq):
        if kind != "d":
            continue
        side = seq[:i][::-1] if month_first else seq[i + 1:]
        m = next((mv for k, mv in side if k == "m"), None)
        if m is None:
            m = next(mv for k, mv in (seq[i + 1:] if month_first else seq[:i][::-1]) if k == "m")
        d = _future(today, m, v)
        if d:
            out.append(d)
    return (min(out), max(out)) if out else None


def _future(today, month, day):
    y = today.year
    try:
        d = date(y, month, day)
    except ValueError:
        return None
    if d < today and (today - d).days > 60:       # "2 January" read in December
        d = date(y + 1, month, day)
    return d


def parse_weight_kg(s):
    """'4.55 Kilograms' / '0.25 kg' / '2.2 Pounds' / '12.8 ounces' / '450 g' -> kg or None."""
    if not s:
        return None
    m = re.search(r"([\d.,]+)\s*(kilograms?|kg|pounds?|lbs?|ounces?|oz|grams?|g)\b", s, re.I)
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    unit = m.group(2).lower()
    if unit.startswith(("pound", "lb")):
        v *= 0.45359237
    elif unit.startswith(("ounce", "oz")):
        v *= 0.028349523125
    elif unit in ("g", "gram", "grams"):
        v /= 1000
    return round(v, 3)


def parse_dims_cm(s):
    """'12D x 35W x 45H centimetres' / '14 x 10 x 5 inches; 2 Pounds' -> (L, W, H) cm or None.
    Two-dimension values ('10.75"W x 4.5"H') are not a box size -> None."""
    if not s:
        return None
    m = re.search(r"([\d.,]+)\s*[a-z\"]*\s*x\s*([\d.,]+)\s*[a-z\"]*\s*x\s*([\d.,]+)\s*[a-z\"]*\s*"
                  r"(centimet(?:re|er)s?|cm|millimet(?:re|er)s?|mm|inch(?:es)?|in|\")?", s, re.I)
    if not m:
        return None
    vals = [float(x.replace(",", ".")) for x in m.group(1, 2, 3)]
    unit = (m.group(4) or "").lower()
    if not unit:
        unit = "inch" if '"' in s or "inch" in s.lower() else "cm" if "cm" in s.lower() or "centi" in s.lower() else ""
    if unit.startswith(("inch", "in", '"')):
        vals = [v * 2.54 for v in vals]
    elif unit.startswith(("milli", "mm")):
        vals = [v / 10 for v in vals]
    elif not unit.startswith(("centi", "cm")):
        return None
    return tuple(round(v, 1) for v in vals)


# -------------------------------------------------------------------- Amazon

def _element(html, id_, span=12000):
    m = re.search(r'\bid="%s"' % re.escape(id_), html)
    return html[m.start():m.start() + span] if m else ""


def _detail_rows(html):
    """{label: value} from the product details tables (th/td rows and bullet lists)."""
    rows = {}
    for th, td in re.findall(r"<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>", html, re.S):
        rows.setdefault(_text(th), _text(td))
    for lab, val in re.findall(r'<span class="a-text-bold">(.*?)</span>\s*<span[^>]*>(.*?)</span>', html, re.S):
        rows.setdefault(_text(lab).rstrip(" :‏‎"), _text(val))
    return rows


def _amazon_price(html):
    """The price to pay: the priceToPay span (its a-offscreen, else symbol + whole + fraction).
    Never the first a-offscreen in the block — that can be a per-unit price ($9.00 / count)."""
    for id_ in ("corePriceDisplay_desktop_feature_div", "corePrice_feature_div"):
        seg = _element(html, id_)
        for m in re.finditer(r'<span class="a-price[^"]*(?:priceToPay|apex-pricetopay-value)[^"]*"[^>]*>', seg):
            inner = seg[m.end():m.end() + 800]
            off = re.match(r'\s*<span class="a-offscreen">([^<]*)<', inner)
            if off and off.group(1).strip():
                return parse_money(off.group(1))
            sym = re.search(r'a-price-symbol">([^<]*)<', inner)
            whole = re.search(r'a-price-whole">([\d.,\s]*)<', inner)
            frac = re.search(r'a-price-fraction">(\d+)<', inner)
            if whole:
                raw = "%s%s.%s" % (sym.group(1) if sym else "", re.sub(r"[^\d]", "", whole.group(1)),
                                   frac.group(1) if frac else "00")
                return parse_money(raw)
    return None, None


def parse_amazon(html, today):
    title_tag = re.search(r"<title>(.*?)</title>", html, re.S)
    if title_tag and "page not found" in title_tag.group(1).lower():
        return {"status": "gone"}
    title = _text(re.search(r'id="productTitle"[^>]*>(.*?)</span>', html, re.S).group(1)) \
        if 'id="productTitle"' in html else None

    price, currency = _amazon_price(html)

    shipping = None
    note = ""
    delivery = None
    tag = re.search(r'<span[^>]*data-csa-c-content-id="DEXUnifiedCXPDM"[^>]*>', html)
    if tag:
        attrs = dict(re.findall(r'data-csa-c-([\w-]+)="([^"]*)"', tag.group(0)))
        p = htmllib.unescape(attrs.get("delivery-price", ""))
        cond = htmllib.unescape(attrs.get("delivery-condition", "")).strip()
        if p.upper() == "FREE":
            if "first order" in cond.lower():
                note = "free on a first order only — real cost unknown"
            else:
                shipping = 0.0
        else:
            amt, cur = parse_money(p)
            if amt is not None and (cur in (None, currency)):
                shipping = amt
        if cond and not note:
            note = cond
        delivery = parse_delivery(attrs.get("delivery-time", ""), today)

    avail = _element(html, "availability", 2500)
    first = re.search(r"<span[^>]*>(.*?)</span>", avail, re.S)
    stock_text = _text(first.group(1)) if first else ""
    low = stock_text.lower()
    if any(p in low for p in OUT_OF_STOCK) or 'id="outOfStock"' in html:
        in_stock = False
    elif stock_text or price:
        in_stock = True
    else:
        in_stock = None

    rows = _detail_rows(html)
    weight = dims = None
    source = ""
    for label in ("Package Dimensions", "Package dimensions", "Package Weight", "Package weight"):
        if label in rows:
            dims = dims or parse_dims_cm(rows[label]) if "imension" in label else dims
            weight = weight or (parse_weight_kg(rows[label]) if "eight" in label or ";" in rows[label] else None)
            source = "package"
    if dims is None:
        for label, v in rows.items():
            if "imension" in label:
                dims = parse_dims_cm(v)
                if dims:
                    source = source or "product"
                    break
    if weight is None:
        for label, v in rows.items():
            if "eight" in label:
                weight = parse_weight_kg(v)
                if weight:
                    source = source or "product"
                    break

    deliver_to = _text(_element(html, "glow-ingress-block", 600).split("</div>")[0])
    deliver_to = re.sub(r'^id="glow-ingress-block"[^>]*>\s*', "", deliver_to).strip()
    return {"status": "ok", "title": title, "price": price, "currency": currency,
            "shipping": shipping, "shipping_note": note, "delivery": delivery,
            "in_stock": in_stock, "stock_text": stock_text[:80], "weight_kg": weight,
            "dims_cm": dims, "size_source": source, "deliver_to": deliver_to}


# ---------------------------------------------------------------------- vega

def parse_vega(html, today=None):
    product = None
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product" and data.get("offers"):
            product = data
            break
    if not product:
        return {"status": "ok", "title": None, "price": None, "currency": "AMD", "shipping": None,
                "shipping_note": "", "delivery": None, "in_stock": None, "stock_text": "",
                "weight_kg": None, "dims_cm": None, "size_source": "", "deliver_to": ""}
    offer = product["offers"]
    if isinstance(offer, list):
        offer = offer[0]
    try:
        price = float(offer.get("price"))
    except (TypeError, ValueError):
        price = None
    avail = (offer.get("availability") or "").rsplit("/", 1)[-1]
    in_stock = True if avail == "InStock" else False if avail in ("OutOfStock", "SoldOut") else None
    return {"status": "ok", "title": product.get("name"), "price": price,
            "currency": offer.get("priceCurrency") or "AMD", "shipping": 0.0,
            "shipping_note": "local shop", "delivery": None, "in_stock": in_stock,
            "stock_text": avail, "weight_kg": None, "dims_cm": None, "size_source": "",
            "deliver_to": ""}


PARSERS = {"amazon": parse_amazon, "vega": parse_vega}


def parse(family, html, today):
    fn = PARSERS.get(family)
    if not fn:
        return {"status": "no_parser"}
    return fn(html, today)
