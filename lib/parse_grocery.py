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
# The address the Yerevan City iPhone app claims (apple-app-site-association lists
# "/shop/product-detail/*", singular). Tapped on an iPhone with the app installed it
# opens the app; on the web it only lands on the shop home page, so it is offered
# as an extra link next to the normal one, never instead of it (decision 083).
YC_APP_URL = "https://yerevan-city.am/shop/product-detail/%s"

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
            "name_hy": None,
            "price": price,
            "old_price": old,
            "discount_pct": _discount_pct(price, old),
            "sold_by_weight": by_weight,
            "min_qty": _num(min_qty) if (by_weight and min_qty) else None,
            "unit_price": unit_price,
            "unit": unit,
            "url": PARMA_BASE + html.unescape(href),
            "app_url": None,
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
            "name_hy": (p.get("nameArm") or "").strip() or None,
            "price": price,
            "old_price": old,
            "discount_pct": _discount_pct(price, old),
            "sold_by_weight": by_weight,
            "min_qty": (float(p["minimumWeight"]) / 1000.0  # YC sends grams
                        if (by_weight and p.get("minimumWeight")) else None),
            "unit_price": unit_price,
            "unit": unit,
            "url": YC_PRODUCT_URL % p.get("id"),
            "app_url": YC_APP_URL % p.get("id"),
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

# Latin, Armenian and Cyrillic letters, digits, %
_TOKEN_RE = re.compile(r"[a-z0-9%Ա-ևЀ-ӿ]+")


def _tokens(text):
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if len(t) >= 2]


def _is_latin(tokens):
    return all(t.isascii() for t in tokens)


def _same_word(q, w):
    """Whole-word match, tolerant of a plural on either side (lentil/lentils).
    Not a prefix match: "milk" must not match the brand "Milka"."""
    if q == w:
        return True
    for a, b in ((q, w), (w, q)):
        if b in (a + "s", a + "es"):
            return True
    return False


# ---- word list: Armenian / transliterated words -> what the shops call it

def parse_word_list(md_text):
    """Rows of the Markdown table in plan/meals/grocery-words.md:

        | You can type | Search shops for | Product names to match |
        | ոսպ, vosp, lentil | lentils | lentil |

    -> [{"aliases": [[tokens], ...], "search": "lentils", "match": [[tokens], ...]}]
    Header, separator and malformed rows are skipped.
    """
    rows = []
    for line in (md_text or "").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not cells[0] or set(cells[0]) <= set("-: "):
            continue
        if cells[0].lower().startswith("you can type"):
            continue
        aliases = [_tokens(a) for a in cells[0].split(",") if _tokens(a)]
        match = [_tokens(m) for m in cells[2].split(",") if _tokens(m)]
        search = re.sub(r"[✓✔*]", "", cells[1]).strip()   # drop ✓ marks
        if aliases and match and search:
            rows.append({"aliases": aliases, "search": search, "match": match})
    return rows


def expand_query(query, words=None):
    """Query -> (text to send to the shops, groups to match names against).

    A group is a list of alternative phrases (each a token list); a name must
    satisfy every group. Words found in the word list are replaced by what the
    shops call them ("vosp" -> search "lentils", match "lentil"); other words
    stay as they are. Longest alias wins ("chicken breast" before "chicken").
    """
    qt = _tokens(query)
    aliases = sorted(((a, r) for r in (words or []) for a in r["aliases"]),
                     key=lambda ar: -len(ar[0]))
    groups, search, i = [], [], 0
    while i < len(qt):
        for alias, row in aliases:
            if qt[i:i + len(alias)] == alias:
                groups.append(row["match"])
                search.append(row["search"])
                i += len(alias)
                break
        else:
            groups.append([[qt[i]]])
            search.append(qt[i])
            i += 1
    return (" ".join(search) if search else (query or "").strip()), groups


def _phrase_in(phrase, ws):
    return all(any(_same_word(t, w) for w in ws) for t in phrase)


def _phrase_at(phrase, ws, pos):
    seg = ws[pos:pos + len(phrase)]
    return len(seg) == len(phrase) and all(_same_word(t, w) for t, w in zip(phrase, seg))


def _score_tokens(ws, groups):
    if not all(any(_phrase_in(ph, ws) for ph in g) for g in groups):
        return None
    # descriptors in front of the product type ("Fresh chicken breast") don't
    # make it a weaker match -- unless the descriptor is what was asked for
    pos = 0
    while pos < len(ws) and ws[pos] in DESCRIPTORS and not any(
            _phrase_at(ph, ws, pos) for g in groups for ph in g):
        pos += 1
    for g in groups:
        ph = next((ph for ph in g if _phrase_at(ph, ws, pos)), None)
        if ph is None:
            return 1
        pos += len(ph)
    return 0


def match_score(name, query, words=None, name_hy=None):
    """0 = the name starts with the product asked for (names lead with the
    type: 'Milk "Milkin" 2.5% 950ml'); 1 = everything asked for is somewhere in
    the name; None = not a match.

    Armenian queries are matched against the shop's Armenian name when it has
    one (Yerevan City). Parma's English site has no Armenian names, so words
    that can't be read there are left to the shop's own search.
    """
    _, groups = expand_query(query, words)
    if not groups:
        return 1
    best = None
    for text in (name, name_hy):
        if not text:
            continue
        ws = _tokens(text)
        usable = groups
        if text is name and name_hy is None:
            # English-only name: drop groups it cannot express (Armenian word
            # not in the word list) and trust the shop for those
            usable = [g for g in groups if any(_is_latin(ph) for ph in g)]
            if not usable:
                return 1
        sc = _score_tokens(ws, usable)
        if sc is not None and (best is None or sc < best):
            best = sc
    return best


def matches(name, query, words=None, name_hy=None):
    """True when everything asked for appears in the name as whole words.

    Both shops return loose matches (a "milk" search brings face wash and ice
    cream); this keeps results that actually name what was asked for.
    """
    return match_score(name, query, words, name_hy) is not None


def rank(items, query, sort="relevance", only_available=True, words=None):
    """Filter to real matches and order them; each kept item gets "match"
    (0 = leads with the product, 1 = contains it).

    Names that start with the query come first. Within that, sort="relevance"
    keeps each shop's own order and interleaves the shops; sort="cheap" orders
    by unit price (items without one go last).
    """
    scored = []
    for n, i in enumerate(items):
        sc = match_score(i["name"], query, words, i.get("name_hy"))
        if sc is None or (only_available and not i["available"]):
            continue
        i["match"] = sc
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


# ---------------------------------------------------------------- comparison

def pct_cheaper(low, high):
    """How much cheaper `low` is than `high`, in whole percent (half up)."""
    if not low or not high or low >= high:
        return 0
    return amd((high - low) / high * 100.0)


def compare_shops(ranked):
    """Cheapest unit price per shop among the best matches.

    Uses only items that lead with the product (match 0) when there are any,
    and only one unit (the most common: kg vs l vs pcs never get compared).
    Returns None when fewer than two shops have a comparable item, else
    {"unit", "best": {shop: item}, "cheaper": shop|None, "pct": int}.
    """
    pool = [i for i in ranked if i.get("match") == 0] or list(ranked)
    pool = [i for i in pool if i.get("unit_price")]
    if not pool:
        return None
    units = {}
    for i in pool:
        units[i["unit"]] = units.get(i["unit"], 0) + 1
    unit = max(units, key=lambda u: (units[u], u == "kg"))
    best = {}
    for i in pool:
        if i["unit"] != unit:
            continue
        cur = best.get(i["shop"])
        if cur is None or i["unit_price"] < cur["unit_price"]:
            best[i["shop"]] = i
    if len(best) < 2:
        return None
    lo = min(best.values(), key=lambda i: i["unit_price"])
    hi = max(best.values(), key=lambda i: i["unit_price"])
    cheaper = lo["shop"] if lo["unit_price"] < hi["unit_price"] else None
    return {"unit": unit, "best": best, "cheaper": cheaper,
            "pct": pct_cheaper(lo["unit_price"], hi["unit_price"])}


_BRAND_RE = re.compile(r'["«“]([^"»”]+)["»”]')
_PCT_RE = re.compile(r"(\d+(?:[.,․]\d+)?)\s*%")
_NOISE = {"kg", "gr", "ml", "pcs", "pc", "sh", "gb", "pack", "with", "and", "in", "the"}


def product_key(name, type_words=()):
    """Identity of a product across shops, or None when it can't be told.

    brand (quoted) + package size + fat % + the remaining descriptive words,
    with the product-type words removed (shops name the type differently:
    "Curd" vs "Cottage cheese", "Matzoon" vs "Matsun"). Deliberately strict:
    "Curd Marianna Bifido 9% 180g" and "Curd Marianna 9% 180g" are different.
    """
    b = _BRAND_RE.search(name or "")
    size = size_from_name(name)
    if not b or not size:
        return None
    pct = _PCT_RE.search(name)
    pct = pct.group(1).replace(",", ".").replace("․", ".") if pct else None
    brand = tuple(_tokens(b.group(1)))
    rest = _BRAND_RE.sub(" ", name)
    words = set()
    for t in _tokens(rest):
        if t in _NOISE or t in brand or _SIZE_RE.fullmatch(t) or t.replace(".", "").isdigit():
            continue
        if t.endswith("%") or any(_same_word(t, w) for w in type_words):
            continue
        words.add(t[:-1] if t.endswith("s") and len(t) > 3 else t)
    return brand, (round(size[0], 3), size[1]), pct, frozenset(words)


def same_products(items, query, words=None):
    """Products sold at both shops: [(parma_item, yc_item, diff, pct)], where
    diff = yc price - parma price (negative = Yerevan City cheaper) and pct is
    how much cheaper the cheaper shop is. Cheapest copy per shop is used."""
    _, groups = expand_query(query, words)
    type_words = {t for g in groups for ph in g for t in ph}
    by_key = {}
    for i in items:
        k = product_key(i["name"], type_words)
        if k is None:
            continue
        cur = by_key.setdefault(k, {}).get(i["shop"])
        if cur is None or i["price"] < cur["price"]:
            by_key[k][i["shop"]] = i
    out = []
    for shops in by_key.values():
        if "parma" in shops and "yc" in shops:
            p, y = shops["parma"], shops["yc"]
            diff = y["price"] - p["price"]
            out.append((p, y, diff, pct_cheaper(min(p["price"], y["price"]),
                                                max(p["price"], y["price"]))))
    out.sort(key=lambda t: -abs(t[2]))
    return out
