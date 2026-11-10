"""The model's two small answers -> clean values, or ValueError (CLAUDE.md §2: output that fails
validation is rejected whole and re-asked once, then a deterministic default is used).

plan   (prompts/amazon_plan.md): per-store queries, category, at most ONE question
reason (prompts/amazon_reason.md): one sentence; every number in it must be one the facts held
"""
import re

from china import validate as cv

CATEGORIES = ("electronics", "clothes", "baby", "home", "beauty", "toys", "other")
STORES = ("uk", "de", "it", "us")
QUERY_RE = re.compile(r"^[\w][\w\s\-+.,/&'°%\"]{1,78}$", re.U)
extract_json = cv.extract_json
NUM_RE = re.compile(r"\d[\d.,]*\d|\d")


def _query(v, field):
    s = cv._str(v, field, 80, required=True)
    if cv.URL_RE.search(s) or not QUERY_RE.match(s):
        raise ValueError("%s is not a plain search phrase" % field)
    return s


def plan(obj):
    if not isinstance(obj, dict):
        raise ValueError("plan is not a JSON object")
    en = _query(obj.get("query_en"), "query_en")
    qs = obj.get("queries")
    if not isinstance(qs, dict):
        raise ValueError("queries must be an object")
    queries = {}
    for k in STORES:
        if qs.get(k) is None and k == "us":
            queries[k] = en
            continue
        queries[k] = _query(qs.get(k), "queries.%s" % k)
    cat = obj.get("category") or "other"
    if cat not in CATEGORIES:
        raise ValueError("category %r not allowed" % cat)
    vague = cv._bool(obj.get("vague"), "vague")
    questions = obj.get("questions") or []
    if not isinstance(questions, list) or len(questions) > 1:
        raise ValueError("at most one question")
    out_q = []
    for x in questions:
        if not isinstance(x, dict):
            raise ValueError("question is not an object")
        opts = cv._list(x.get("options"), "options", 4, 24)
        if len(opts) < 2:
            raise ValueError("a question needs 2–4 options")
        out_q.append({"q": cv._str(x.get("q"), "question", 80, required=True), "options": opts})
    if vague and not out_q:
        raise ValueError("vague without a question")
    return {"query_en": en, "queries": queries, "category": cat,
            "vague": vague and bool(out_q), "questions": out_q if vague else []}


def _digits(tok):
    return re.sub(r"[.,]", "", tok)


def numbers(text):
    """Number tokens of a text as digit strings ('1,234' -> '1234')."""
    return {_digits(t) for t in NUM_RE.findall(text or "")}


def reason(obj, facts):
    """One sentence whose numbers all occur in `facts` (the text the model was given)."""
    if not isinstance(obj, dict):
        raise ValueError("reason is not a JSON object")
    s = cv._str(obj.get("reason"), "reason", 240, required=True)
    if cv.URL_RE.search(s):
        raise ValueError("reason holds a link")
    extra = numbers(s) - numbers(facts)
    if extra:
        raise ValueError("reason holds numbers not in the facts: %s" % ", ".join(sorted(extra)))
    return s
