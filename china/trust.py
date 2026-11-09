"""Trust score for one priced result — all in code (CLAUDE.md §2), from what the page showed.

Owner, 2026-11-09: "the price is not so important — find the best and trustworthy product,
reviews and all important things counted, especially on Pinduoduo." So results are ranked by
this score first and by delivered price only among results of about the same score
(the same BAND), and the 🏆 pick is the top of that order.

Points (each part is shown in the 🏆 reason and in the result's details):

    seller        official 40 · brand-authorised 35 · flagship 25 · reseller 10 · factory 10
                  · unmarked 0                                  (parse.seller_class)
    guarantee     +5 when the page shows a fake-compensation / genuine-goods promise
                  (假一赔十, 正品险, 正品发票, 品牌正品, "compensation for fakes")
    store age     +1 per year shown (8年老店, 入驻5年), at most +5
    certified     +5 when the specs carry a 3C/CCC or CE certificate (electronics, kids)
    sales         3 × log10(sales), at most +15 (10,000 sold ≈ +12)
    reviews       2.5 × log10(review count), at most +10 (2,321 reviews ≈ +8)
    rating        with ≥ 20 reviews: 100% positive (or 5.0/5) +10, 90% 0, below 90% negative
                  (down to −20)
    complaints    per kind the model found in the reviews (allow-list validate.COMPLAINTS):
                  fake, broken, unsafe, wrong_spec, not_as_described −12 · poor_quality −6 ·
                  slow_shipping, packaging, other −2
    spec mismatch −15 when the attributes contradict the title (e.g. title 65W, spec 25W)
    suspicious    −100 (far below the search's median price, pricing.mark_suspicious)
    brand         +10 for a brand on the category's trusted list, −30 for a known look-alike
                  (config_china.json "brands", owner-editable; decision 093). The brand is
                  read from the 品牌 spec, the shop name or the START of the title — never from
                  anywhere in the title, because no-name titles say "适用苹果" (fits Apple)
    variant       reviews read were of the wanted variant +3; only of other variants −5
    photos        reviews with buyer photos/videos: 2 × log10(count), at most +6
"""
import math
import re

from china import parse

SELLER_POINTS = {parse.OFFICIAL: 40, parse.AUTHORISED: 35, parse.FLAGSHIP: 25,
                 parse.RESELLER: 10, parse.FACTORY: 10, parse.UNMARKED: 0}
GUARANTEE_WORDS = ("假一赔", "正品险", "正品发票", "品牌正品", "compensation for fakes", "正品保障")
SERIOUS = ("fake", "broken", "unsafe", "wrong_spec", "not_as_described")
COMPLAINT_POINTS = {**{k: -12 for k in SERIOUS}, "poor_quality": -6,
                    "slow_shipping": -2, "packaging": -2, "other": -2}
COMPLAINT_TEXT = {"fake": "fake", "broken": "broken / stops working", "unsafe": "unsafe (heat, sparks)",
                  "wrong_spec": "real specs lower than stated", "not_as_described": "not as described",
                  "poor_quality": "poor quality", "slow_shipping": "slow shipping",
                  "packaging": "packaging", "other": "other"}
CERT_KEYS = ("3c", "ccc", "ce认证", "ce ", "产品认证")
CERT_CATEGORIES = ("electronics", "kids")
MIN_REVIEWS_FOR_RATING = 20
BAND = 5   # results whose scores fall in the same band of 5 points are ordered by price

VARIANT_POINTS = {"matching": 3, "other": -5}
VARIANT_TEXT = {"matching": "reviews are of this variant", "other": "reviews are of other variants"}

AGE_RE = re.compile(r"(\d{1,2})\s*年(?:老店|店)|入驻\s*(\d{1,2})\s*年")
PCT_RE = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*%")
STARS_RE = re.compile(r"(?<![\d.])([1-5](?:\.\d)?)(?:\s*分|\s*/\s*5|\b)")


def rating(text):
    """Share of positive reviews 0..1 from '好评率98%', '98%好评', '4.8分', '5.0', '4.8/5';
    None when no rating is shown."""
    if not text:
        return None
    s = str(text)
    m = PCT_RE.search(s)
    if m:
        v = float(m.group(1))
        return v / 100.0 if 0 < v <= 100 else None
    m = STARS_RE.search(s)
    if m:
        return float(m.group(1)) / 5.0
    return None


def store_years(marks, badges):
    best = 0
    for t in list(marks or []) + list(badges or []):
        for m in AGE_RE.finditer(str(t)):
            best = max(best, int(m.group(1) or m.group(2)))
    return best


def _certified(specs):
    for k, v in (specs or {}).items():
        t = ("%s %s" % (k, v)).lower()
        if any(c in t for c in CERT_KEYS) and "无" not in str(v) and "否" != str(v).strip():
            return True
    return False


BRACKETS_RE = re.compile(r"^\s*(?:[【\[(（][^】\])）]{0,12}[】\])）]\s*)*")
BRAND_SHOP_WORDS = ("旗舰店", "专卖店", "official")


def _norm(t):
    """Lower-case text without leading bracket tags such as 【官方正品】."""
    return BRACKETS_RE.sub("", str(t or "")).lower()


def _starts_with(text, name):
    """text starts with name, followed by a non-letter (so 'UE' matches 'UE100W' but not
    'UEFA'; Chinese names need no boundary)."""
    t, n = _norm(text), name.lower()
    if not t.startswith(n):
        return False
    nxt = t[len(n):len(n) + 1]
    return not (n.isascii() and nxt.isascii() and nxt.isalpha())


def brand_of(p, names):
    """The first of names (each a list of spellings, e.g. ["绿联", "ugreen"]) that the result
    shows as ITS brand: the 品牌 spec, a brand store's name (旗舰店 / 专卖店 — an accessory
    shop called "苹果配件店" is not Apple), or the start of the title. None if none."""
    specs = p.get("specs") or {}
    spec_brand = next((str(v) for k, v in specs.items()
                       if "品牌" in str(k) or str(k).lower() == "brand"), "")
    shop = str(p.get("shop_name") or "").lower()
    brand_shop = any(w in shop for w in BRAND_SHOP_WORDS)
    for spellings in names or []:
        for n in spellings:
            if (spec_brand and _starts_with(spec_brand, n)) \
                    or (brand_shop and n.lower() in shop) \
                    or _starts_with(p.get("title_cn"), n) or _starts_with(p.get("title_en"), n):
                return next((x for x in spellings if x.isascii()), spellings[0])
    return None


def score(p, category="other", brands=None):
    """(points, parts): parts is a list of (label, points) for the reason text. brands is
    config_china.json "brands": {category: {"trusted": [[spellings]], "lookalike": [[...]]}}."""
    parts = []
    parts.append((parse.LABEL[p["seller"]].split(" ", 1)[1], SELLER_POINTS.get(p["seller"], 0)))
    tags = [str(x) for x in list(p.get("marks") or []) + list(p.get("badges") or [])]
    g = next((t for t in tags if any(w in t.lower() for w in GUARANTEE_WORDS)), None)
    if g:
        parts.append(("guarantee " + g, 5))
    yrs = store_years(p.get("marks"), p.get("badges"))
    if yrs:
        parts.append(("store %d yr" % yrs, min(5, yrs)))
    if category in CERT_CATEGORIES and _certified(p.get("specs")):
        parts.append(("certified (3C/CE)", 5))
    sales = p.get("sales")
    if sales and sales >= 10:
        parts.append(("%s sold" % _n(sales), round(min(15.0, 3 * math.log10(sales)), 1)))
    n = p.get("reviews")
    if n and n >= 10:
        parts.append(("%s reviews" % _n(n), round(min(10.0, 2.5 * math.log10(n)), 1)))
    r = rating(p.get("rating_text"))
    if r is not None and (n or 0) >= MIN_REVIEWS_FOR_RATING:
        parts.append(("%d%% positive" % round(r * 100), round(max(-20.0, min(10.0, (r - 0.9) * 100)), 1)))
    for k in p.get("complaint_types") or []:
        parts.append(("complaints: " + COMPLAINT_TEXT.get(k, k), COMPLAINT_POINTS.get(k, -2)))
    lists = (brands or {}).get(category) or {}
    fake = brand_of(p, lists.get("lookalike"))
    good = None if fake else brand_of(p, lists.get("trusted"))
    if fake:
        parts.append(("look-alike brand " + fake, -30))
    elif good:
        parts.append(("known brand " + good, 10))
    if p.get("reviews_read") and p.get("review_variant") in VARIANT_POINTS:
        parts.append((VARIANT_TEXT[p["review_variant"]], VARIANT_POINTS[p["review_variant"]]))
    photos = p.get("photo_reviews")
    if photos and photos >= 3:
        parts.append(("%s photo reviews" % _n(photos), round(min(6.0, 2 * math.log10(photos)), 1)))
    if p.get("spec_mismatch"):
        parts.append(("specs contradict the title", -15))
    if p.get("suspicious"):
        parts.append(("suspiciously cheap", -100))
    return round(sum(v for _, v in parts), 1), parts


def _n(v):
    if v >= 10000:
        return "%s万" % ("{:.0f}".format(v / 10000.0) if v >= 100000 else "{:.1f}".format(v / 10000.0))
    return "{:,}".format(v)


def reason(p):
    """Words for the 🏆 line, from the parts (positive first, then the warnings)."""
    good = [lbl for lbl, v in p["trust_parts"] if v > 0]
    bad = [lbl for lbl, v in p["trust_parts"] if v < 0]
    if not any(lbl.startswith("complaints") for lbl in bad) and p.get("reviews_read"):
        good.append("no serious complaints in the reviews read")
    s = ", ".join(good) if good else "no trust signals shown"
    if bad:
        s += "; but " + ", ".join(bad)
    return s
