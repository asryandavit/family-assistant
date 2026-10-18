"""Parse grocery search results from Parma (HTML) and Yerevan City (JSON).

Deterministic: every number is a value the shop returned, or arithmetic on one.
Written against payloads captured in tests/fixtures/grocery/ (CLAUDE.md §8).

Every item comes out in one shape, whichever shop it came from:

    shop          "parma" | "yc"
    id            shop's product id (str)
    name          English name
    price         current price in AMD for one purchase unit: the package, or
                  1 kg when sold_by_weight
    old_price     pre-discount price (same basis as price), or None
    discount_pct  e.g. 17.9, or None
    sold_by_weight  True when priced per kg (bought by weight)
    min_qty       smallest amount you can order, in kg, for weight items
    unit_price    AMD per `unit` (kg / l / pcs), for comparing packages
    unit          "kg" | "l" | "pcs" | None
    url, image, category, available

Shop semantics, as observed:
  Parma  - `data-price` is the price; a `discount_item` block holds the old one.
           Weight items (class c_gramm) show the price of the MINIMUM amount
           (e.g. 0.5 kg); the per-kg price is in `unitCoefficientText`.
  YC     - `price` is the original price, `discountedPrice` the sale price
           (0 = no sale). `productPricePerUnit` is per kg (G) or per litre (ML),
           already computed from the current price. `isKilogram` = priced per kg.
"""
import html
import re
from decimal import ROUND_HALF_UP, Decimal

PARMA_BASE = "https://parma.am"
YC_PRODUCT_URL = "https://yerevan-city.am/shop/product-details/%s"

_SIZE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|gr|g|ml|l)\b", re.I)
_UNIT_TEXT_RE = re.compile(r"1\s*(kg|l|pcs)\s*/\s*([\d.,]+)", re.I)


def amd(x):
    """Round an AMD amount to a whole dram, half up (banker's rounding would
    turn 0.5 into 0)."""
    if x is None:
        return None
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _num(s):
    return float(str(s).replace(",", "").strip())


def size_from_name(name):
    """Package size from a product name -> (quantity, "kg" | "l") or None.

    Takes the LAST size in the name ("12pcs 350g" -> 0.35 kg). Grams and
    millilitres are converted to kg and litres.
    """
    hits = _SIZE_RE.findall(name or "")
    if not hits:
        return None
    qty, unit = hits[-1]
    q = _num(qty.replace(",", "."))
    unit = unit.lower()
    if q <= 0:
        return None
    if unit in ("g", "gr"):
        return q / 1000.0, "kg"
    if unit == "ml":
        return q / 1000.0, "l"
    return q, unit


def unit_price_from_name(price, name):
    """Price per kg/l derived from the size in the name, or (None, None)."""
    s = size_from_name(name)
    if not s or price is None:
        return None, None
    qty, unit = s
    return round(price / qty, 2), unit


def _discount_pct(price, old):
    if not old or not price or old <= price:
        return None
    return round((old - price) / old * 100.0, 1)


# --------------------------------------------------------------------- Parma

def _between(text, pattern, flags=re.S):
    m = re.search(pattern, text, flags)
    return m.group(1) if m else None


def parse_parma(page_html):
    """One Parma search/listing page -> list of items."""
    items = []
    for card in page_html.split('<div class="product_item ')[1:]:
        # a card is followed by the next card or the end of the section; the
        # first ~6k chars always contain everything we need
        card = card[:6000]
        cls = card[:card.find('"')]
        href = _between(card, r'href="(/en/product/product\?slug=[^"]+)"')
        name = _between(card, r'class="item_name"><span>(.*?)</span>')
        price = _between(card, r'class="product_price" data-price="([\d.]+)"')
        if not (href and name and price):
            continue
        name = html.unescape(name).strip()
        price = _num(price)
        old = _between(card, r'discount_item">\s*<div class="full-price">\s*<span>([\d.,]+)</span>')
        old = _num(old) if old else None
        pid = _between(card, r'data-id="(\d+)"') or href.rsplit("_", 1)[-1]
        image = _between(card, r'<img src="([^"]+)"[^>]*class="product-image')
        unit_text = _between(card, r'unitCoefficientText">(.*?)</span>')
        min_qty = _between(card, r'data-min="([\d.]+)"')

        unit_price, unit = None, None
        if unit_text:
            m = _UNIT_TEXT_RE.search(html.unescape(unit_text))
            if m:
                unit, unit_price = m.group(1).lower(), _num(m.group(2))

        by_weight = "c_gramm" in cls
        if by_weight and unit == "kg" and unit_price:
            # shown price is for the minimum amount; normalise to per kg
            q = _num(min_qty) if min_qty else None
            if old and q:
                old = round(old / q, 2)
            price = unit_price
        if unit_price is None:
            unit_price, unit = unit_price_from_name(price, name)

        items.append({
            "shop": "parma",
            "id": str(pid),
            "name": name,
            "price": price,
            "old_price": old,
            "discount_pct": _discount_pct(price, old),
            "sold_by_weight": by_weight,
            "min_qty": _num(min_qty) if (by_weight and min_qty) else None,
            "unit_price": unit_price,
            "unit": unit,
            "url": PARMA_BASE + html.unescape(href),
            "image": image,
            "category": None,
            "available": True,
        })
    return items


def parma_page_range(page_html):
    """('61', '73') style range from the pager, or None."""
    m = re.search(r"<span>(\d+)\s*-\s*(\d+)</span>", page_html)
    return (int(m.group(1)), int(m.group(2))) if m else None


# --------------------------------------------------------- Yerevan City (YC)

def parse_yc(payload):
    """Yerevan City Product/Search JSON -> list of items."""
    data = (payload or {}).get("data") or {}
    items = []
    for p in data.get("products") or []:
        name = (p.get("nameEn") or p.get("name") or "").strip()
        if not name or p.get("price") is None:
            continue
        orig = float(p["price"])
        sale = float(p.get("discountedPrice") or 0)
        price = sale if 0 < sale < orig else orig
        old = orig if price < orig else None
        by_weight = bool(p.get("isKilogram"))

        unit_price, unit = None, None
        wm = (p.get("weightMeasure") or "").upper()
        if by_weight:
            unit_price, unit = price, "kg"
        elif p.get("productPricePerUnit") and wm in ("G", "ML"):
            unit_price = float(p["productPricePerUnit"])
            unit = "kg" if wm == "G" else "l"
        else:
            unit_price, unit = unit_price_from_name(price, name)

        items.append({
            "shop": "yc",
            "id": str(p.get("id")),
            "name": name,
            "price": price,
            "old_price": old,
            "discount_pct": _discount_pct(price, old),
            "sold_by_weight": by_weight,
            "min_qty": (float(p["minimumWeight"]) / 1000.0  # YC sends grams
                        if (by_weight and p.get("minimumWeight")) else None),
            "unit_price": unit_price,
            "unit": unit,
            "url": YC_PRODUCT_URL % p.get("id"),
            "image": p.get("photo"),
            "category": p.get("categoryName"),
            "available": bool(p.get("isOnline", True)),
        })
    return items


def yc_counts(payload):
    """(item_count, page_count) reported by YC."""
    data = (payload or {}).get("data") or {}
    return data.get("itemCount") or 0, data.get("pageCount") or 0


# ------------------------------------------------------------------ ranking

# Words that can precede the product type without changing what it is.
DESCRIPTORS = {"fresh", "frozen", "chilled", "boneless", "skinless", "organic", "natural",
               "whole", "large", "small", "baby", "young", "premium", "extra", "virgin",
               "lactose", "free", "low", "fat", "light", "local", "armenian", "farm"}


def _tokens(text):
    return [t for t in re.findall(r"[a-z0-9%]+", (text or "").lower()) if len(t) >= 2]


def _same_word(q, w):
    """Whole-word match, tolerant of a plural on either side (lentil/lentils).
    Not a prefix match: "milk" must not match the brand "Milka"."""
    if q == w:
        return True
    for a, b in ((q, w), (w, q)):
        if b in (a + "s", a + "es"):
            return True
    return False


def match_score(name, query):
    """0 = the name starts with the query (names lead with the product type:
    'Milk "Milkin" 2.5% 950ml'); 1 = every query word is somewhere in the
    name; None = not a match."""
    qs, ws = _tokens(query), _tokens(name)
    if not qs:
        return 1
    if not all(any(_same_word(q, w) for w in ws) for q in qs):
        return None
    # "Fresh chicken breast", "Frozen chicken breast fillet": descriptors in
    # front of the product type don't make it a weaker match
    rest = ws
    while rest and rest[0] in DESCRIPTORS and not any(_same_word(q, rest[0]) for q in qs):
        rest = rest[1:]
    lead = rest[:len(qs)]
    if len(lead) == len(qs) and all(_same_word(q, w) for q, w in zip(qs, lead)):
        return 0
    return 1


def matches(name, query):
    """True when every query word appears in the name as a whole word.

    Both shops return loose matches (a "milk" search brings face wash and ice
    cream); this keeps results that actually name what was asked for.
    """
    return match_score(name, query) is not None


def rank(items, query, sort="relevance", only_available=True):
    """Filter to real matches and order them.

    Names that start with the query come first. Within that, sort="relevance"
    keeps each shop's own order and interleaves the shops; sort="cheap" orders
    by unit price (items without one go last).
    """
    scored = []
    for n, i in enumerate(items):
        sc = match_score(i["name"], query)
        if sc is None or (only_available and not i["available"]):
            continue
        scored.append((sc, n, i))
    if sort == "cheap":
        scored.sort(key=lambda t: (t[0], t[2]["unit_price"] is None,
                                   t[2]["unit_price"] or 0, t[2]["price"]))
        return [i for _, _, i in scored]
    out = []
    for tier in sorted({sc for sc, _, _ in scored}):
        lanes = {}
        for sc, _, i in scored:
            if sc == tier:
                lanes.setdefault(i["shop"], []).append(i)
        lanes = list(lanes.values())
        while any(lanes):
            for lane in lanes:
                if lane:
                    out.append(lane.pop(0))
    return out
