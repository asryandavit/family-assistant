"""The model's JSON answer for one site -> a clean dict, or ValueError (CLAUDE.md §2: model
output that fails validation is rejected whole and re-asked once, never partially accepted).

Contract (prompts/china_rules.md shows it to the model):

{"site": "pinduoduo|taobao|1688", "status": "ok|login|check|error", "notice": str|null,
 "category": "electronics|clothes|shoes|home|beauty|kids|other",
 "brand_guidance": str|null,
 "search_ids": [id, ...],                   every listing id the search page showed (allow-list)
 "results": [{
    "id": str, "title_cn": str, "title_en": str,
    "shop_name": str|null, "marks": [str], "badges": [str],
    "variant": str|null,                      the option matching the description
    "price_text": str|null,                   that variant's price exactly as shown
    "price_kind": "after_coupon|list|group|first_item|tier|single|unknown",
    "list_price_text": str|null, "single_price_text": str|null,
    "domestic_delivery_text": str|null,       "包邮", "运费¥8", ... as shown
    "weight_text": str|null, "dims_text": str|null,
    "sales_text": str|null, "review_count_text": str|null, "min_order_text": str|null,
    "specs": {str: str}, "material": str|null, "size_advice": str|null,
    "liked": [str], "complaints": [str], "reviews_read": bool,
    "rating_text": str|null,                  positive rate / score as shown
    "complaint_types": [COMPLAINTS],          kinds the reviews read report (allow-list)
    "spec_mismatch": bool,                    attributes contradict the title
    "likely_over_1kg": bool, "over_1kg_reason": str|null,
    "restrict": ["battery|liquid|magnet|aerosol"],
    "why": str|null}]}
"""
import re

SITES = ("pinduoduo", "taobao", "1688")
STATUSES = ("ok", "login", "check", "error")
CATEGORIES = ("electronics", "clothes", "shoes", "home", "beauty", "kids", "other")
PRICE_KINDS = ("after_coupon", "list", "group", "first_item", "tier", "single", "unknown")
RESTRICT = ("battery", "liquid", "magnet", "aerosol")
COMPLAINTS = ("fake", "broken", "unsafe", "wrong_spec", "not_as_described", "poor_quality",
              "slow_shipping", "packaging", "other")
ID_RE = re.compile(r"^\d{6,15}$")
URL_RE = re.compile(r"https?://|www\.", re.I)

MAX_RESULTS = 8
SHORT, MID, LONG = 80, 200, 400


def _str(v, field, limit, required=False, allow_url=False, prose=False):
    """Text field. Data fields (ids, prices, counts, names) over the limit are rejected;
    prose fields (English descriptions written by the model) are trimmed with '…' — a
    long sentence is not a wrong value (live run 2026-11-09: 'why' at 202 of 200)."""
    if v is None:
        if required:
            raise ValueError("%s missing" % field)
        return None
    if not isinstance(v, str):
        raise ValueError("%s is not text" % field)
    v = " ".join(v.split())
    if required and not v:
        raise ValueError("%s empty" % field)
    if len(v) > limit:
        if not prose:
            raise ValueError("%s too long (%d > %d)" % (field, len(v), limit))
        v = v[: limit - 1].rstrip() + "…"
    if not allow_url and URL_RE.search(v):
        raise ValueError("%s contains a link" % field)   # links are built in code only
    return v or None


def _list(v, field, limit_items, limit_len, allowed=None, prose=False):
    if v is None:
        return []
    if not isinstance(v, list) or len(v) > limit_items:
        raise ValueError("%s must be a list of at most %d" % (field, limit_items))
    out = []
    for x in v:
        s = _str(x, field, limit_len, required=True, prose=prose)
        if allowed and s not in allowed:
            raise ValueError("%s: %r not allowed" % (field, s))
        out.append(s)
    return out


def _unique(xs):
    out = []
    for x in xs:
        if x not in out:
            out.append(x)
    return out


def _bool(v, field):
    if v is None:
        return False
    if not isinstance(v, bool):
        raise ValueError("%s is not true/false" % field)
    return v


def _id(v, field):
    s = str(v).strip() if isinstance(v, (str, int)) and not isinstance(v, bool) else ""
    if not ID_RE.match(s):
        raise ValueError("%s is not an item id: %r" % (field, v))
    return s


def result(r, search_ids, site):
    if not isinstance(r, dict):
        raise ValueError("result is not an object")
    rid = _id(r.get("id"), "id")
    if rid not in search_ids:
        raise ValueError("id %s was not on the search page" % rid)
    specs = r.get("specs") or {}
    if not isinstance(specs, dict) or len(specs) > 12:
        raise ValueError("specs must be an object of at most 12 entries")
    kind = r.get("price_kind") or "unknown"
    if kind not in PRICE_KINDS:
        raise ValueError("price_kind %r not allowed" % kind)
    return {
        "site": site, "id": rid,
        "title_cn": _str(r.get("title_cn"), "title_cn", LONG, required=True),
        "title_en": _str(r.get("title_en"), "title_en", MID, required=True, prose=True),
        "shop_name": _str(r.get("shop_name"), "shop_name", SHORT),
        "marks": _list(r.get("marks"), "marks", 12, 40),
        "badges": _list(r.get("badges"), "badges", 12, 60),
        "variant": _str(r.get("variant"), "variant", MID),
        "price_text": _str(r.get("price_text"), "price_text", SHORT),
        "price_kind": kind,
        "list_price_text": _str(r.get("list_price_text"), "list_price_text", SHORT),
        "single_price_text": _str(r.get("single_price_text"), "single_price_text", SHORT),
        "domestic_delivery_text": _str(r.get("domestic_delivery_text"), "domestic_delivery_text", SHORT),
        "weight_text": _str(r.get("weight_text"), "weight_text", SHORT),
        "dims_text": _str(r.get("dims_text"), "dims_text", SHORT),
        "sales_text": _str(r.get("sales_text"), "sales_text", SHORT),
        "review_count_text": _str(r.get("review_count_text"), "review_count_text", SHORT),
        "min_order_text": _str(r.get("min_order_text"), "min_order_text", SHORT),
        "specs": {_str(k, "specs key", 40, required=True): _str(v, "specs value", SHORT, required=True)
                  for k, v in specs.items()},
        "material": _str(r.get("material"), "material", MID, prose=True),
        "size_advice": _str(r.get("size_advice"), "size_advice", MID, prose=True),
        "liked": _list(r.get("liked"), "liked", 3, 160, prose=True),
        "complaints": _list(r.get("complaints"), "complaints", 3, 160, prose=True),
        "reviews_read": _bool(r.get("reviews_read"), "reviews_read"),
        "rating_text": _str(r.get("rating_text"), "rating_text", SHORT),
        "complaint_types": _unique(_list(r.get("complaint_types"), "complaint_types", len(COMPLAINTS),
                                         20, allowed=COMPLAINTS)),
        "spec_mismatch": _bool(r.get("spec_mismatch"), "spec_mismatch"),
        "likely_over_1kg": _bool(r.get("likely_over_1kg"), "likely_over_1kg"),
        "over_1kg_reason": _str(r.get("over_1kg_reason"), "over_1kg_reason", MID, prose=True),
        "restrict": _list(r.get("restrict"), "restrict", 4, 10, allowed=RESTRICT),
        "why": _str(r.get("why"), "why", MID, prose=True),
    }


def answer(obj, expect_site):
    """Validated site answer. Raises ValueError with a human sentence on any defect."""
    if not isinstance(obj, dict):
        raise ValueError("answer is not a JSON object")
    site = obj.get("site")
    if site != expect_site:
        raise ValueError("answer is for %r, expected %r" % (site, expect_site))
    status = obj.get("status")
    if status not in STATUSES:
        raise ValueError("status %r not allowed" % status)
    cat = obj.get("category") or "other"
    if cat not in CATEGORIES:
        raise ValueError("category %r not allowed" % cat)
    raw_ids = obj.get("search_ids") or []
    if not isinstance(raw_ids, list) or len(raw_ids) > 80:
        raise ValueError("search_ids must be a list of at most 80")
    search_ids = [_id(x, "search_ids") for x in raw_ids]
    raw = obj.get("results") or []
    if not isinstance(raw, list) or len(raw) > MAX_RESULTS:
        raise ValueError("results must be a list of at most %d" % MAX_RESULTS)
    if status == "ok" and not raw and search_ids:
        raise ValueError("status ok with search ids but no results")
    results = [result(r, set(search_ids), site) for r in raw]
    if len({r["id"] for r in results}) != len(results):
        raise ValueError("the same id appears twice in results")
    return {"site": site, "status": status, "category": cat,
            "notice": _str(obj.get("notice"), "notice", LONG, prose=True),
            "brand_guidance": _str(obj.get("brand_guidance"), "brand_guidance", LONG, prose=True),
            "search_ids": search_ids, "results": results}


def plan(obj):
    """The plan call's answer (prompts/china_plan.md) -> clean dict, or ValueError."""
    if not isinstance(obj, dict):
        raise ValueError("plan is not a JSON object")
    q = _str(obj.get("query_cn"), "query_cn", 40, required=True)
    cat = obj.get("category") or "other"
    if cat not in CATEGORIES:
        raise ValueError("category %r not allowed" % cat)
    vague = _bool(obj.get("vague"), "vague")
    qs = obj.get("questions") or []
    if not isinstance(qs, list) or len(qs) > 2:
        raise ValueError("questions must be a list of at most 2")
    out_q = []
    for x in qs:
        if not isinstance(x, dict):
            raise ValueError("question is not an object")
        opts = _list(x.get("options"), "options", 4, 24)
        if len(opts) < 2:
            raise ValueError("a question needs 2–4 options")
        out_q.append({"q": _str(x.get("q"), "question", 80, required=True), "options": opts})
    if vague and not out_q:
        raise ValueError("vague without questions")
    return {"query_cn": q, "query_en": _str(obj.get("query_en"), "query_en", 80),
            "category": cat, "vague": vague and bool(out_q), "questions": out_q if vague else []}


def _balanced(s, start):
    """The JSON object starting at s[start] ('{'), parsed; ValueError if unbalanced/invalid."""
    import json
    depth, in_str, esc = 0, False, False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return json.loads(s[start:i + 1])
    raise ValueError("unfinished JSON object in the reply")


def extract_json(text):
    """The answer object in a model reply: a ```json fence first, else the first '{' that
    starts a valid JSON object (a stray '{' in the prose before it is skipped)."""
    s = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, re.S)
    if m:
        try:
            return _balanced(m.group(1), 0)
        except ValueError:
            pass
    last = ValueError("no JSON object in the reply")
    pos = s.find("{")
    while pos >= 0:
        try:
            obj = _balanced(s, pos)
            if isinstance(obj, dict):
                return obj
        except ValueError as e:
            last = e
        pos = s.find("{", pos + 1)
    raise last
