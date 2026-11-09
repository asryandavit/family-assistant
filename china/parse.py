"""Strings as the shops show them -> numbers and classes. No model, no guessing:
anything that does not parse is None and is shown as "not read" (CLAUDE.md §2).

Formats seen in P0 (tests/fixtures/china/):
    price   "券后¥189"  "¥109"  "￥109.34"  "首件¥89.9"  "¥|109|.34" (Taobao card)  "109"  "$12.50"
    counts  "全店总售523万+"  "本店已拼1.2万"  "已拼467件"  "5000+人付款"  "全部(2321)"  "2,321"
    weight  "180" (g column)  "100g"  "重量100g"  "0.5kg"  "1.2公斤"  "500克"
"""
import re
from urllib.parse import quote

CNY_RE = re.compile(r"[¥￥]\s*\|?\s*(\d+(?:[.,]\d+)?)(?:\s*\|\s*(\.\d+))?")
USD_RE = re.compile(r"(?:US\s*\$|\$|USD\s*)\s*(\d+(?:\.\d+)?)", re.I)
NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*$")
MAX_PRICE = 1_000_000


def _ok(v):
    return v if v is not None and 0 < v < MAX_PRICE else None


def cny(text):
    """First ¥ amount in a shown price string; a bare number counts as ¥. None otherwise."""
    if text is None:
        return None
    s = str(text).strip()
    m = CNY_RE.search(s)
    if m:
        whole = m.group(1).replace(",", ".")
        if m.group(2):
            whole += m.group(2)
        return _ok(float(whole))
    m = NUM_RE.match(s)
    return _ok(float(m.group(1))) if m else None


def usd(text):
    m = USD_RE.search(str(text or ""))
    return _ok(float(m.group(1))) if m else None


def money(text):
    """(amount, currency) from a shown price: ¥ first, then $, then a bare number as ¥."""
    s = "" if text is None else str(text)
    if CNY_RE.search(s):
        return cny(s), "CNY"
    u = usd(s)
    if u is not None:
        return u, "USD"
    v = cny(s)
    return (v, "CNY") if v is not None else (None, None)


COUNT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(万|千)?")


def count(text):
    """Sales / review counts: 万 = 10,000, 千 = 1,000; '2,321' -> 2321. None if no number."""
    if text is None:
        return None
    s = str(text).replace(",", "").replace("，", "")
    m = COUNT_RE.search(s)
    if not m:
        return None
    return int(round(float(m.group(1)) * {"万": 10000, "千": 1000}.get(m.group(2), 1)))


WEIGHT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|公斤|千克|克|g)(?![a-z])", re.I)


def weight_kg(text, unit_if_bare=None):
    """kg from '100g', '重量100g', '0.5kg', '1.2公斤', '500克'; a bare number only with
    unit_if_bare ('g' for 1688's 'Weight (g)' column). Accepted range 1 g – 100 kg."""
    if text is None:
        return None
    s = str(text).strip()
    m = WEIGHT_RE.search(s)
    if m:
        v, unit = float(m.group(1)), m.group(2).lower()
        kg = v if unit in ("kg", "公斤", "千克") else v / 1000.0
    elif unit_if_bare and NUM_RE.match(s):
        v = float(s)
        kg = v / 1000.0 if unit_if_bare == "g" else v
    else:
        return None
    return round(kg, 3) if 0.001 <= kg <= 100 else None


def dims_cm(l, w, h, weight_g=None):
    """(dims in cm or None, note). 1688 tables are labelled cm but are sometimes mm (P0: a
    180 g charger listed 67.5×33.8×86.5 = 197 litres). With a weight: density 0.02–5 g/cm³
    is accepted; under 0.02 whose mm reading lands in 0.02–5 is read as mm and said so;
    anything else is rejected. Without a weight, a side over 150 cm is rejected."""
    try:
        d = [float(l), float(w), float(h)]
    except (TypeError, ValueError):
        return None, "size not read"
    if min(d) <= 0:
        return None, "size not read"
    vol = d[0] * d[1] * d[2]
    if weight_g:
        dens = weight_g / vol
        if 0.02 <= dens <= 5:
            return tuple(d), ""
        dens_mm = weight_g / (vol / 1000.0)
        if dens < 0.02 and 0.02 <= dens_mm <= 5:
            return tuple(round(x / 10.0, 2) for x in d), "size read as mm (labelled cm)"
        return None, "size does not fit the weight"
    if max(d) > 150:
        return None, "size implausible"
    return tuple(d), ""


# ---------------------------------------------------------------- sellers

OFFICIAL = "official"        # 官方旗舰店
FLAGSHIP = "flagship"        # other 旗舰店: a flagship, but not marked as THE official store
AUTHORISED = "authorised"    # 品牌授权 tag, 专卖店 (single-brand authorised store)
RESELLER = "reseller"        # 专营店 (multi-brand), 直销店 / 直营店 / 经销
FACTORY = "factory"          # 源头工厂, 实力商家, 工厂, Factory direct supply
UNMARKED = "unmarked"

LABEL = {OFFICIAL: "✅ official flagship", FLAGSHIP: "🟡 flagship store, not marked official",
         AUTHORISED: "🟢 brand-authorised", RESELLER: "⚪ reseller", FACTORY: "🏭 factory",
         UNMARKED: "⚪ unmarked seller"}

FACTORY_MARKS = ("源头工厂", "实力商家", "工厂店", "factory direct supply")


def seller_class(shop_name="", marks=(), badges=()):
    """(class, evidence) from text the page showed — shop name, marks, badges — only.
    '旗舰店' alone is NOT official (P0: 品胜官方旗舰店 vs 品胜快充旗舰店)."""
    name = str(shop_name or "")
    tags = [str(x) for x in list(marks or []) + list(badges or []) if x]
    if "官方旗舰店" in name:
        return OFFICIAL, "官方旗舰店"
    for t in tags:
        if "官方旗舰" in t:
            return OFFICIAL, t
    for t in tags + [name]:
        for k in FACTORY_MARKS:
            if k in t.lower():
                return FACTORY, k
    if "旗舰店" in name:
        return FLAGSHIP, "旗舰店"
    for t in tags:
        if "品牌授权" in t:
            return AUTHORISED, t
    if "专卖店" in name:
        return AUTHORISED, "专卖店"
    for k in ("专营店", "直销店", "直营店", "经销"):
        if k in name:
            return RESELLER, k
    if "工厂" in name:
        return FACTORY, "工厂"
    return UNMARKED, ""


# ---------------------------------------------------------------- restrictions

RESTRICT_WORDS = {
    "battery": ["充电宝", "移动电源", "锂电池", "电池", "power bank", "battery"],
    "liquid": ["液体", "精华液", "香水", "精油", "洗发水", "liquid", "perfume"],
    "magnet": ["磁吸", "磁铁", "强磁", "magnetic", "magnet"],
    "aerosol": ["喷雾", "气雾", "aerosol", "spray"],
}
RESTRICT_TEXT = {
    "battery": "battery inside — air forwarders may refuse; check before ordering",
    "liquid": "liquid — air forwarders may refuse; check before ordering",
    "magnet": "magnets — some forwarders refuse strong magnets by air",
    "aerosol": "aerosol — not accepted by air",
}


def restrictions(*texts):
    """Forwarder-sensitive goods named in the given texts: sorted list of flags."""
    t = " ".join(str(x) for x in texts if x).lower()
    return sorted(k for k, words in RESTRICT_WORDS.items() if any(w.lower() in t for w in words))


# ---------------------------------------------------------------- links (built from ids)

ID_RE = re.compile(r"^\d{6,15}$")


def link(site, item_id):
    """Product link from the id only — tool output never carries URLs (P0)."""
    i = str(item_id or "")
    if not ID_RE.match(i):
        return None
    return {"pinduoduo": "https://mobile.yangkeduo.com/goods.html?goods_id=" + i,
            "taobao": "https://item.taobao.com/item.htm?id=" + i,
            "1688": "https://detail.1688.com/offer/%s.html" % i}.get(site)


def search_link(site, query):
    q = quote(query or "")
    return {"pinduoduo": "https://mobile.yangkeduo.com/search_result.html?search_key=" + q,
            "taobao": "https://s.taobao.com/search?q=" + q,
            "1688": "https://s.1688.com/selloffer/offer_search.htm?charset=utf8&keywords=" + q
            }.get(site)
