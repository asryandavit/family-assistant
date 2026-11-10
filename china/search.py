"""One queued /china job, start to finish (run by jobs/china_search.py, one at a time).

    search   plan (if not planned yet) -> vague? ask 1–2 questions with buttons and stop
             -> each site (progress message after each) -> price in code -> one answer
             (rich, plain fallback) to the asking chat -> save /china last (after sending)
    reviews  one listing's reviews (💬 button) -> a short reply

Order of failure handling (CLAUDE.md §5): a site that fails is named in the answer and the
others still answer; the message is sent before anything is saved.
"""
import json
import os
import time
from datetime import UTC, datetime, timezone

from china import data_dir, photo, pricing, report, runner, taobao, validate
from market import rates as rates_mod

SITES = ("pinduoduo", "taobao", "1688")


def load_cfg(root):
    with open(os.path.join(root, "config_china.json"), encoding="utf-8") as f:
        return json.load(f)


def app_url():
    """The Mini App's China screen (machine.json miniapp_public_url), or None when the Mini App
    is not set up on this machine — then the answers simply have no 📱 button."""
    try:
        from miniapp import public_url
        u = public_url()
    except (OSError, ValueError):
        return None
    return u + "?screen=china" if u else None


def load_routes(root):
    with open(os.path.join(root, "market", "tariffs.json"), encoding="utf-8") as f:
        t = json.load(f)
    return t["routes"], (t.get("refreshed_utc") or "")[:10]


# ------------------------------------------------------------------ files

def _path(root, name):
    return os.path.join(data_dir(root), name)


def write_json(root, name, obj):
    tmp = _path(root, name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, default=str)
    os.replace(tmp, _path(root, name))


def read_json(root, name, default=None):
    try:
        with open(_path(root, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_last(root, chat_id, payload):
    write_json(root, "last_%s.json" % chat_id, dict(payload, saved=time.time()))


def load_last(root, chat_id, keep_hours=24):
    d = read_json(root, "last_%s.json" % chat_id)
    if not d or time.time() - d.get("saved", 0) > keep_hours * 3600:
        return None
    return d


# ------------------------------------------------------------------ sites

def read_site(cfg, ccfg, site, description, query_cn, log=print):
    """Validated answer dict for one site (status ok/login/check/error) + usage."""
    if site == "taobao" and ccfg.get("taobao_mode", "link") == "link":
        return {"site": "taobao", "status": "link", "notice": None, "category": "other",
                "brand_guidance": None, "search_ids": [], "results": []}, {}
    if site == "taobao":
        t = taobao.read(query_cn, max_pages=ccfg.get("reviews_top", 3), log=log)
        if t["status"] != "ok":
            return {"site": "taobao", "status": t["status"], "notice": t["notice"], "category": "other",
                    "brand_guidance": None, "search_ids": [], "results": []}, {}
        return runner.taobao_text(cfg, ccfg, description, query_cn, t["cards"], t["pages"])
    return runner.site(cfg, ccfg, site, description, query_cn)


def assemble(answers, ccfg, routes, rates, today):
    """answers: validated site answers in site order -> (sites, pick, reason, groups, category,
    brand_guidance) for report.build()."""
    cats = [a.get("category") or "other" for a in answers if a["status"] == "ok"]
    category = max(set(cats), key=cats.count) if cats else "other"
    guidance = next((a.get("brand_guidance") for a in answers
                     if a["status"] == "ok" and a.get("brand_guidance")), None)
    per_site = [[pricing.price_result(r, routes, rates, today, ccfg) for r in a["results"]]
                for a in answers]
    everything = [p for ps in per_site for p in ps]
    pricing.mark_suspicious(everything, ccfg.get("suspicious_ratio", 0.25))
    pricing.apply_trust(everything, category, ccfg.get("brands"))
    sites, all_ranked = [], []
    for a, priced in zip(answers, per_site):
        ranked = pricing.rank(priced, ccfg.get("top_per_site", 5))
        sites.append({"site": a["site"], "status": a["status"], "notice": a.get("notice"),
                      "ranked": ranked})
        all_ranked.extend(ranked)
    pick, reason = pricing.best_pick(all_ranked)
    groups = pricing.same_product(all_ranked)
    return sites, pick, reason, groups, category, guidance


# ------------------------------------------------------------------ jobs

def question_buttons(job_id, qi, q):
    return [[(o, "cn:q:%s:%d:%d" % (job_id, qi, oi)) for oi, o in enumerate(q["options"])][:4],
            [("➡️ Skip — search as is", "cn:q:%s:%d:-1" % (job_id, qi))]]


def ask_question(tg, cfg, root, pend, qi):
    q = pend["plan"]["questions"][qi]
    tg.send_html(cfg, "🇨🇳 <b>China search</b> · %s\n%s" % (report.esc(pend["description"]),
                                                            report.esc(q["q"])),
                 silent=True, buttons=question_buttons(pend["job"], qi, q), chat_id=pend["chat_id"])


def run_search(job, cfg, root, tg, today, log=print, read=read_site, plan_fn=runner.plan,
               rates_get=rates_mod.get):
    ccfg = load_cfg(root)
    chat = job["chat_id"]
    desc = job["description"]
    plan = job.get("plan")
    if not plan:
        try:
            plan, _ = plan_fn(cfg, ccfg, desc)
        except Exception as e:
            log("plan failed: %s" % e)
            tg.send_html(cfg, "⚠️ China search: I could not understand the request this time "
                              "(%s). Try again with a few more words." % report.esc(str(e)[:80]),
                         silent=True, chat_id=chat)
            return "plan_failed"
        if plan["vague"] and not job.get("answers") and not job.get("no_questions"):
            pend = {"job": job["job"], "chat_id": chat, "description": desc, "plan": plan,
                    "sites": job.get("sites") or list(SITES), "answers": []}
            write_json(root, "pending_%s.json" % job["job"], pend)
            ask_question(tg, cfg, root, pend, 0)
            return "asked"
    sites = [s for s in (job.get("sites") or ccfg.get("sites") or SITES) if s in SITES]
    full = desc + ("; " + "; ".join(job["answers"]) if job.get("answers") else "")
    answers, usage = [], {}
    for i, s in enumerate(sites, start=1):
        try:
            a, u = read(cfg, ccfg, s, full, plan["query_cn"], log=log)
        except Exception as e:                    # a site never takes the others down
            a, u = runner.error(s, str(e)[:160]), {}
        answers.append(a)
        usage[s] = u
        log("%s: %s %s" % (s, a["status"], u))
        if a["status"] != "link":            # a link-only site takes no time: no progress line
            tg.send_html(cfg, report.progress(s, i, len(sites), a["status"]), silent=True, chat_id=chat)
    routes, tariffs_date = load_routes(root)
    rates = rates_get(root, today)
    sites_out, pick, reason, groups, category, guidance = assemble(answers, ccfg, routes, rates, today)
    rich, plain, btns = report.build(job["job"], full, sites_out, pick, reason, groups, rates,
                                     tariffs_date, category if plan else "other", guidance,
                                     search_query=plan.get("query_cn"), app_url=app_url())
    if not report.fits(rich):
        kind = "plain"
        tg.send_html(cfg, plain, silent=True, buttons=btns, chat_id=chat)
    else:
        kind, _ = tg.send_rich(cfg, rich, plain, silent=True, buttons=btns, chat_id=chat)
    log("answer sent as %s; usage %s" % (kind, usage))
    save_last(root, chat, {"job": job["job"], "description": full, "query_cn": plan["query_cn"],
                           "sites": sites_out, "category": category, "rich": rich, "plain": plain,
                           "buttons": btns, "usage": usage,
                           "sent_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return kind


# ------------------------------------------------------------------ photo search

PDD_PHOTO_NOTE = ("searched by the words read from your photo — Pinduoduo searches by photo "
                  "only in its app")
TAOBAO_PHOTO_TIP = "📷 in the Taobao app, tap the camera in the search bar to search by this photo"


def bot_token(cfg):
    return os.environ.get(cfg["telegram"]["bot_token_env"], "")


def _photo_path(job, cfg, root, download, log):
    """A kept photo (🔁 on a photo answer) or a fresh download for this job."""
    if job.get("photo_of"):
        p = photo.find(root, job["photo_of"])
        if p:
            return p, False
        raise ValueError("the photo was already deleted")
    dest = photo.path_for(root, job["job"], job.get("ext") or "jpg")
    download(bot_token(cfg), job["file_id"], dest)
    log(f"photo {job['job']} downloaded ({os.path.getsize(dest) // 1024} KB)")
    return dest, True


def run_photo(job, cfg, root, tg, today, log=print, plan_fn=runner.photo_plan, read=None,
              read_photo=runner.site_photo, rates_get=rates_mod.get, download=photo.download):
    """Photo search: photo -> plan (what it is, Chinese words) -> 1688 by photo, Pinduoduo by
    the words (its photo search is app-only), Taobao a link + app tip -> the same answer as
    a text search. The photo is deleted when the answer is out, unless photo_keep_minutes."""
    read = read or read_site
    ccfg = load_cfg(root)
    chat = job["chat_id"]
    note = job.get("note") or ""
    keep = ccfg.get("photo_keep_minutes", 0)
    path, mine = None, False
    try:
        try:
            path, mine = _photo_path(job, cfg, root, download, log)
        except ValueError as e:
            log(f"photo {job['job']}: {e}")
            why = report.esc(str(e)[:80])
            tg.send_html(cfg, f"⚠️ China photo search: I could not get the photo ({why}). Send it "
                              "again.", silent=True, chat_id=chat)
            return "photo_failed"
        plan = job.get("plan")
        if not plan:
            try:
                plan, _ = plan_fn(cfg, ccfg, path, note)
            except Exception as e:  # noqa: BLE001 — any failure is told to the asker, never silent
                log(f"photo plan failed: {e}")
                why = report.esc(str(e)[:80])
                tg.send_html(cfg, f"⚠️ China photo search: I could not read the photo this time "
                                  f"({why}). Try again, or add a caption like "
                                  "<code>/china red, size 42</code>.", silent=True, chat_id=chat)
                return "plan_failed"
            if not plan.get("is_product"):
                seen = f" ({report.esc(plan['seen'])})" if plan.get("seen") else ""
                tg.send_html(cfg, f"🤔 I don't see something to buy in this photo{seen}. Send a "
                                  "photo of the item itself (or its box or label).",
                             silent=True, chat_id=chat)
                return "not_product"
        sites = [x for x in (job.get("sites") or ccfg.get("sites") or SITES) if x in SITES]
        full = plan["query_en"] + ("; " + note if note else "")
        answers, usage = [], {}
        for i, s in enumerate(sites, start=1):
            try:
                if s == "1688":
                    a, u = read_photo(cfg, ccfg, full, plan["query_cn"], path)
                    if a["status"] == "error":       # photo search broke: search by its words
                        why = (a.get("notice") or "error")[:60]
                        log(f"1688 photo search failed ({why}); searching by words")
                        a, u = read(cfg, ccfg, s, full, plan["query_cn"], log=log)
                        a = dict(a, notice=f"photo search failed ({why}) — searched by the words "
                                           "from your photo")
                elif s == "pinduoduo":
                    a, u = read(cfg, ccfg, s, full, plan["query_cn"], log=log)
                    if a["status"] == "ok":
                        a = dict(a, notice=PDD_PHOTO_NOTE + (" · " + a["notice"] if a.get("notice") else ""))
                else:
                    a, u = read(cfg, ccfg, s, full, plan["query_cn"], log=log)
                    if a["status"] == "link":
                        a = dict(a, notice=TAOBAO_PHOTO_TIP)
            except Exception as e:  # noqa: BLE001 — a site never takes the others down
                a, u = runner.error(s, str(e)[:160]), {}
            answers.append(a)
            usage[s] = u
            log(f"{s}: {a['status']} {u}")
            if a["status"] != "link":
                tg.send_html(cfg, report.progress(s, i, len(sites), a["status"]), silent=True, chat_id=chat)
        routes, tariffs_date = load_routes(root)
        rates = rates_get(root, today)
        sites_out, pick, reason, groups, category, guidance = assemble(answers, ccfg, routes, rates, today)
        seen = f"📷 {plan.get('seen') or plan['query_en']} · searched as {plan['query_cn']}"
        rich, plain, btns = report.build(job["job"], full, sites_out, pick, reason, groups, rates,
                                         tariffs_date, plan.get("category") or category, guidance,
                                         search_query=plan["query_cn"], photo_line=seen,
                                         app_url=app_url())
        if not report.fits(rich):
            kind = "plain"
            tg.send_html(cfg, plain, silent=True, buttons=btns, chat_id=chat)
        else:
            kind, _ = tg.send_rich(cfg, rich, plain, silent=True, buttons=btns, chat_id=chat)
        log(f"photo answer sent as {kind}; usage {usage}")
        save_last(root, chat, {"job": job["job"], "kind": "photo", "description": full,
                               "query_cn": plan["query_cn"], "plan": plan,
                               "photo_of": job.get("photo_of") or job["job"],
                               "user_id": job.get("user_id"), "role": job.get("role"),
                               "sites": sites_out, "category": category, "rich": rich,
                               "plain": plain, "buttons": btns, "usage": usage,
                               "sent_utc": datetime.now(UTC).isoformat(timespec="seconds")})
        return kind
    finally:
        if mine and not keep:
            photo.remove(path)


def find_result(root, chat_id, job_id, n):
    last = load_last(root, chat_id, 24)
    if not last or last.get("job") != job_id:
        return None, None
    k = 0
    for s in last["sites"]:
        for p in s.get("ranked") or []:
            k += 1
            if k == n:
                return p, last
    return None, last


REVIEW_STEPS = {
    "pinduoduo": "Navigate to https://mobile.yangkeduo.com/goods_comments.html?goods_id={item_id} and "
                 "read document.body.innerText.slice(0,950), then scroll once and read slice(950,1900).",
    "1688": "Navigate to https://detail.1688.com/offer/{item_id}.html and read the whole page with "
            "ONE get_page_text call (javascript_tool is refused on detail.1688.com); use the rating "
            "and the reviews shown there.",
}


def run_reviews(job, cfg, root, tg, call=runner.call, log=print):
    chat = job["chat_id"]
    p, _ = find_result(root, chat, job["for_job"], job["n"])
    if not p:
        tg.send_html(cfg, "That result is older than 24 h — run /china again.", silent=True, chat_id=chat)
        return "gone"
    if p["site"] not in REVIEW_STEPS:
        tg.send_html(cfg, "💬 Reviews for Taobao items are not read automatically yet — open "
                          '<a href="%s">the listing</a>.' % report.attr(p["link"]),
                     silent=True, chat_id=chat)
        return "unsupported"
    ccfg = load_cfg(root)
    steps = REVIEW_STEPS[p["site"]].replace("{item_id}", p["id"])
    prompt = runner._prompt("china_reviews.md", site_steps=steps, item_id=p["id"])
    try:
        w = call(cfg, prompt, chrome=True, model=ccfg.get("claude_model"), timeout=300)
        r = validate.extract_json(w.get("result"))
        if r.get("status") != "ok":
            raise ValueError("status %s" % r.get("status"))
        liked = validate._list(r.get("liked"), "liked", 3, 160)
        bad = validate._list(r.get("complaints"), "complaints", 3, 160)
        count = validate._str(r.get("review_count_text"), "review_count_text", 80)
        size = validate._str(r.get("size_advice"), "size_advice", 200)
    except Exception as e:
        log("reviews failed: %s" % e)
        tg.send_html(cfg, "⚠️ Could not read the reviews this time (%s)." % report.esc(str(e)[:80]),
                     silent=True, chat_id=chat)
        return "error"
    from china import parse
    n = parse.count(count)
    lines = ["💬 <b>Reviews · %d. %s</b>%s" % (job["n"], report.esc(report.short(p["title_en"], 60)),
                                               " · %s reviews" % "{:,}".format(n) if n else "")]
    lines += ["👍 " + report.esc(x) for x in liked] or ["👍 —"]
    lines += ["👎 " + report.esc(x) for x in bad] or ["👎 no complaints found"]
    if size:
        lines.append("📏 " + report.esc(size))
    tg.send_html(cfg, "\n".join(lines), silent=True, chat_id=chat)
    return "ok"
