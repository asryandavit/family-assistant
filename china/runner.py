"""`claude -p` calls for /china (docs/briefs/CHINA_SEARCH.md §4).

- plan():  description -> Chinese query, category, 1–2 questions if vague. No browser.
- site():  one `claude -p --chrome` run per site (Pinduoduo, 1688) in the owner's Chrome.
- taobao_text(): Taobao page text (read by china/taobao.py) -> the same JSON. No browser.

Runs on the owner's Max subscription: ANTHROPIC_API_KEY is removed from the child env.
The Chrome run gets an allow-list of read tools; typing/upload tools are disallowed.
A reply that fails validation is re-asked ONCE in the same session (--resume, no browsing),
then the site is "error" — never partially accepted (CLAUDE.md §2).
No transaction, lock or file handle is held across these calls (CLAUDE.md §3).
"""
import json
import os
import subprocess
from urllib.parse import quote

from china import ROOT, validate

CHROME_TOOLS = ",".join("mcp__claude-in-chrome__" + t for t in (
    "list_connected_browsers", "select_browser", "tabs_context_mcp", "tabs_create_mcp",
    "tabs_close_mcp", "navigate", "get_page_text", "javascript_tool", "find", "computer"))
DENIED = ",".join(["Bash", "Edit", "Write", "WebFetch", "WebSearch",
                   "mcp__claude-in-chrome__form_input", "mcp__claude-in-chrome__file_upload",
                   "mcp__claude-in-chrome__upload_image"])


def _env():
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    return env


def _prompt(name, **kw):
    with open(os.path.join(ROOT, "prompts", name), encoding="utf-8") as f:
        text = f.read()
    for k, v in kw.items():
        text = text.replace("{%s}" % k, str(v))
    return text


def call(cfg, prompt, chrome=False, model=None, timeout=600, resume=None, run=subprocess.run):
    """The CLI's JSON wrapper: {"result", "session_id", "usage", "duration_ms", ...}."""
    cmd = [cfg.get("claude_cmd", "claude"), "-p", "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    if resume:
        cmd += ["--resume", resume]
    if chrome:
        cmd += ["--chrome", "--allowedTools", CHROME_TOOLS, "--disallowedTools", DENIED]
    else:
        cmd += ["--disallowedTools", DENIED + "," + CHROME_TOOLS]
    p = run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
            timeout=timeout, env=_env())
    if p.returncode != 0:
        raise RuntimeError("claude failed: %s" % (p.stderr or p.stdout or "")[:300])
    return json.loads(p.stdout)


def usage(wrapper):
    u = wrapper.get("usage") or {}
    return {"ms": wrapper.get("duration_ms"), "turns": wrapper.get("num_turns"),
            "cache_read": u.get("cache_read_input_tokens"), "cache_new": u.get("cache_creation_input_tokens"),
            "out": u.get("output_tokens"), "list_usd": round(wrapper.get("total_cost_usd") or 0, 2)}


def _validated(cfg, wrapper, check, model, timeout, run):
    """check(obj) on the reply; one repair re-ask in the same session; ValueError after."""
    try:
        return check(validate.extract_json(wrapper.get("result"))), wrapper
    except ValueError as e:
        why = str(e)
    sid = wrapper.get("session_id")
    if not sid:
        raise ValueError(why)
    fix = ("Your JSON answer was rejected: %s. Do not browse again. Reply with the corrected "
           "JSON object only, using only what you already read." % why)
    w2 = call(cfg, fix, chrome=False, model=model, timeout=min(timeout, 180), resume=sid, run=run)
    return check(validate.extract_json(w2.get("result"))), w2


def plan(cfg, ccfg, description, run=subprocess.run):
    w = call(cfg, _prompt("china_plan.md", description=description), model=ccfg.get("claude_model"),
             timeout=120, run=run)
    p, w = _validated(cfg, w, validate.plan, ccfg.get("claude_model"), 120, run)
    return p, usage(w)


def site(cfg, ccfg, site_key, description, query_cn, run=subprocess.run):
    """Validated answer for Pinduoduo or 1688 (or an "error" answer with the reason)."""
    rules = _prompt("china_rules.md", site=site_key, top=ccfg.get("top_per_site", 5),
                    reviews=ccfg.get("reviews_top", 3), description=description, query_cn=query_cn)
    body = _prompt("china_%s.md" % site_key, query_url=quote(query_cn),
                   reviews=ccfg.get("reviews_top", 3))
    timeout = ccfg.get("site_timeout_s", 480)
    try:
        w = call(cfg, rules + "\n\n" + body, chrome=True, model=ccfg.get("claude_model"),
                 timeout=timeout, run=run)
        a, w = _validated(cfg, w, lambda o: validate.answer(o, site_key), ccfg.get("claude_model"),
                          timeout, run)
        return a, usage(w)
    except subprocess.TimeoutExpired:
        return error(site_key, "took longer than %d s" % timeout), {}
    except (ValueError, RuntimeError, json.JSONDecodeError) as e:
        return error(site_key, str(e)[:200]), {}


def taobao_text(cfg, ccfg, description, query_cn, cards, pages, run=subprocess.run):
    """cards: [(id, card text)]; pages: {id: page text}. Same contract, no browser."""
    rules = _prompt("china_rules.md", site="taobao", top=ccfg.get("top_per_site", 5),
                    reviews=ccfg.get("reviews_top", 3), description=description, query_cn=query_cn)
    body = _prompt("china_taobao.md", top=ccfg.get("top_per_site", 5))
    data = "SEARCH CARDS:\n" + "\n".join("%s\t%s" % (i, t[:300]) for i, t in cards)
    for i, t in pages.items():
        data += "\n\nPRODUCT PAGE %s:\n%s" % (i, t[:3500])
    # the browsing instructions in the rules do not apply: say so first
    prompt = ("IMPORTANT: for this request you have no browser; ignore SETUP and every "
              "navigation step below.\n\n" + rules + "\n\n" + body + "\n\n" + data)
    try:
        w = call(cfg, prompt, model=ccfg.get("claude_model"), timeout=300, run=run)
        a, w = _validated(cfg, w, lambda o: validate.answer(o, "taobao"), ccfg.get("claude_model"),
                          300, run)
        return a, usage(w)
    except subprocess.TimeoutExpired:
        return error("taobao", "took longer than 300 s"), {}
    except (ValueError, RuntimeError, json.JSONDecodeError) as e:
        return error("taobao", str(e)[:200]), {}


def error(site_key, why):
    return {"site": site_key, "status": "error", "category": "other", "notice": why,
            "brand_guidance": None, "search_ids": [], "results": []}
