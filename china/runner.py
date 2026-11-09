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
# Photo search on 1688 (decision 095) adds ONLY file_upload (a local file into the page's
# image-search input). upload_image (screenshots) and form_input stay denied.
UPLOAD = "mcp__claude-in-chrome__file_upload"
CHROME_TOOLS_PHOTO = CHROME_TOOLS + "," + UPLOAD
DENIED_PHOTO = ",".join(t for t in DENIED.split(",") if t != UPLOAD)
MEDIA = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
         "bmp": "image/bmp"}


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


def call(cfg, prompt, chrome=False, model=None, timeout=600, resume=None, run=subprocess.run,
         upload=False):
    """The CLI's JSON wrapper: {"result", "session_id", "usage", "duration_ms", ...}.
    upload=True (photo search only) adds file_upload to the Chrome allow-list."""
    cmd = [cfg.get("claude_cmd", "claude"), "-p", "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    if resume:
        cmd += ["--resume", resume]
    if chrome and upload:
        cmd += ["--chrome", "--allowedTools", CHROME_TOOLS_PHOTO, "--disallowedTools", DENIED_PHOTO]
    elif chrome:
        cmd += ["--chrome", "--allowedTools", CHROME_TOOLS, "--disallowedTools", DENIED]
    else:
        cmd += ["--disallowedTools", DENIED + "," + CHROME_TOOLS]
    p = run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
            timeout=timeout, env=_env())
    if p.returncode != 0:
        raise RuntimeError("claude failed: %s" % (p.stderr or p.stdout or "")[:300])
    w = json.loads(p.stdout)
    if run is subprocess.run:           # real replies only — tests' fake replies must not
        keep_raw(w)                     # rotate the real ones out (found 2026-11-09)
    return w


def keep_raw(wrapper):
    """Save the model's raw reply (CLAUDE.md §8: capture the real payload), last 30 kept."""
    try:
        from china import data_dir
        d = os.path.join(data_dir(), "raw")
        os.makedirs(d, exist_ok=True)
        import time as _t
        with open(os.path.join(d, "%d.json" % _t.time_ns()), "w", encoding="utf-8") as f:
            json.dump({"result": wrapper.get("result"), "session_id": wrapper.get("session_id"),
                       "stop_reason": wrapper.get("stop_reason"), "num_turns": wrapper.get("num_turns")},
                      f, ensure_ascii=False)
        for old in sorted(os.listdir(d))[:-30]:
            os.remove(os.path.join(d, old))
    except Exception:
        pass


def usage(wrapper):
    u = wrapper.get("usage") or {}
    return {"ms": wrapper.get("duration_ms"), "turns": wrapper.get("num_turns"),
            "cache_read": u.get("cache_read_input_tokens"), "cache_new": u.get("cache_creation_input_tokens"),
            "out": u.get("output_tokens"), "list_usd": round(wrapper.get("total_cost_usd") or 0, 2),
            "repaired": wrapper.get("repaired") or ""}


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
    print("china: reply rejected (%s); asking once to repair" % why[:160])
    w2 = call(cfg, fix, chrome=False, model=model, timeout=min(timeout, 180), resume=sid, run=run)
    return check(validate.extract_json(w2.get("result"))), merge(wrapper, w2, why)


def merge(w1, w2, why=""):
    """Usage of a run and its repair together (the repair alone would hide the real cost)."""
    u1, u2 = w1.get("usage") or {}, w2.get("usage") or {}
    keys = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
    return dict(w2, usage={k: (u1.get(k) or 0) + (u2.get(k) or 0) for k in keys},
                duration_ms=(w1.get("duration_ms") or 0) + (w2.get("duration_ms") or 0),
                num_turns=(w1.get("num_turns") or 0) + (w2.get("num_turns") or 0),
                total_cost_usd=(w1.get("total_cost_usd") or 0) + (w2.get("total_cost_usd") or 0),
                repaired=why[:160])


def plan(cfg, ccfg, description, run=subprocess.run):
    w = call(cfg, _prompt("china_plan.md", description=description), model=ccfg.get("claude_model"),
             timeout=120, run=run)
    p, w = _validated(cfg, w, validate.plan, ccfg.get("claude_model"), 120, run)
    return p, usage(w)


def call_image(cfg, image_path, text, model=None, timeout=180, run=subprocess.run):
    """One `claude -p` turn that SEES a photo: the image goes in as a base64 block on stdin
    (--input-format stream-json; nothing on the command line), with every tool off
    (--tools ""). Returns a wrapper shaped like call()'s (result, session_id, usage...)."""
    import base64
    ext = os.path.splitext(image_path)[1].lstrip(".").lower()
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    msg = {"type": "user", "message": {"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": MEDIA.get(ext, "image/jpeg"),
                                     "data": b64}},
        {"type": "text", "text": text}]}}
    cmd = [cfg.get("claude_cmd", "claude"), "-p", "--tools", "", "--input-format", "stream-json",
           "--output-format", "stream-json", "--verbose"]
    if model:
        cmd += ["--model", model]
    p = run(cmd, input=json.dumps(msg) + "\n", capture_output=True, text=True, encoding="utf-8",
            timeout=timeout, env=_env())
    if p.returncode != 0:
        raise RuntimeError(f"claude failed: {(p.stderr or '')[:300]}")
    w = stream_result(p.stdout)
    if run is subprocess.run:
        keep_raw(w)
    return w


def stream_result(stdout):
    """The final {"type": "result"} event of a stream-json run, or RuntimeError."""
    res = None
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "result":
            res = ev
    if not res:
        raise RuntimeError("claude gave no result")
    if res.get("is_error"):
        raise RuntimeError(f"claude error: {str(res.get('result'))[:200]}")
    return res


def photo_plan(cfg, ccfg, image_path, note, run=subprocess.run):
    """Photo (+ the caption's note) -> validated photo plan (validate.photo_plan) + usage."""
    w = call_image(cfg, image_path, _prompt("china_photo_plan.md", note=note or "(none)"),
                   model=ccfg.get("claude_model"), timeout=180, run=run)
    p, w = _validated(cfg, w, validate.photo_plan, ccfg.get("claude_model"), 180, run)
    return p, usage(w)


def photo_body(query_url, reviews, image_path):
    """The 1688 photo-search steps: upload the photo, read the result cards, then the same
    product-page and review steps as the text search (china_1688.md from step 2)."""
    text = _prompt("china_1688.md", query_url=query_url, reviews=reviews)
    i = text.find("\n2. ")
    if i < 0:
        raise ValueError("china_1688.md lost its step 2")
    return _prompt("china_1688_photo.md", image_path=image_path) + "\n" + text[i + 1:]


def site_photo(cfg, ccfg, description, query_cn, image_path, run=subprocess.run):
    """1688 image search (以图搜货) with the photo -> the same validated answer as site()."""
    rules = _prompt("china_rules.md", site="1688", top=ccfg.get("top_per_site", 5),
                    reviews=ccfg.get("reviews_top", 3), description=description, query_cn=query_cn)
    body = photo_body(quote(query_cn), ccfg.get("reviews_top", 3), os.path.abspath(image_path))
    timeout = ccfg.get("site_timeout_s", 480)
    try:
        w = call(cfg, rules + "\n\n" + body, chrome=True, model=ccfg.get("claude_model"),
                 timeout=timeout, run=run, upload=True)
        a, w = _validated(cfg, w, lambda o: validate.answer(o, "1688"), ccfg.get("claude_model"),
                          timeout, run)
        return a, usage(w)
    except subprocess.TimeoutExpired:
        return error("1688", f"took longer than {timeout} s"), {}
    except (ValueError, RuntimeError, json.JSONDecodeError) as e:
        return error("1688", str(e)[:200]), {}


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
