"""The two small `claude -p` calls of /amazon (docs/briefs/AMAZON_SEARCH.md §6.1). No browsing
tools, a cheaper model (config "claude_model"), a reply that fails validation is re-asked ONCE
in the same session and then dropped to a deterministic default - never partially accepted
(CLAUDE.md §2). The model never reads a page and never calculates.

- plan():   description -> per-store queries (German/Italian translation), category, <= 1 question
- reason(): final numbers of the pick -> one sentence; fallback = amazon/trust.reason (words from
            the trust parts), so a model failure costs a plainer sentence, never a wrong number.

The CLI plumbing is china/runner.py's (call / usage / _validated / _prompt): imported, not copied.
No transaction, lock or file handle is held across these calls (CLAUDE.md §3).
"""
import subprocess

from amazon import trust, validate
from china import runner as crunner

call, usage, merge = crunner.call, crunner.usage, crunner.merge


def plan(cfg, acfg, description, run=subprocess.run):
    model = acfg.get("claude_model")
    w = call(cfg, crunner._prompt("amazon_plan.md", description=description), model=model,
             timeout=120, run=run)
    p, w = crunner._validated(cfg, w, validate.plan, model, 120, run)
    return p, usage(w)


def facts_text(pick, runner_up=None):
    """The facts block the reason call sees: final numbers only (AMD, as shown in the answer)."""
    def line(tag, p):
        b = p["best"]
        return ("%s: %s - %s %s; total delivered %s AMD via %s; seller: %s; trust: %s" % (
            tag, (p.get("title") or "")[:90], p["currency"], "%g" % p["price"],
            "{:,.0f}".format(p["total_amd"]), b["forwarder"] + " " + b["mode"],
            (p.get("seller") or {}).get("evidence"), trust.reason(p)))
    out = [line("PICK", pick)]
    if runner_up:
        out.append(line("RUNNER-UP", runner_up))
    return "\n".join(out)


def reason(cfg, acfg, pick, runner_up=None, run=subprocess.run):
    """(sentence, usage). The deterministic sentence on any failure (usage {} then)."""
    fallback = trust.reason(pick)
    facts = facts_text(pick, runner_up)
    model = acfg.get("claude_model")
    try:
        w = call(cfg, crunner._prompt("amazon_reason.md", facts=facts), model=model, timeout=90,
                 run=run)
        s, w = crunner._validated(cfg, w, lambda o: validate.reason(o, facts), model, 90, run)
        return s, usage(w)
    except (ValueError, RuntimeError, subprocess.TimeoutExpired, OSError) as e:
        print("amazon: reason call failed (%s); using the deterministic sentence" % str(e)[:120])
        return fallback, {}
