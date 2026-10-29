"""Weekly forwarder tariff refresh (Sunday) -> market/tariffs.json, changes reported.

    python jobs/market_tariffs.py                 fetch, write, print the changes
    python jobs/market_tariffs.py --send          ...and tell the owner (Telegram, silent)
    python jobs/market_tariffs.py --fixtures tests/fixtures/market
                                                  offline: parse the captured pages instead

Sources (docs/briefs/MARKET_WATCH.md §9): Onex /en/tariff JSON, Globbing's home page
(shippingConditions), BuyForYou's home page (calculateShipping constants), EasyTrans
address/all-available-simple. Read-only GETs, one per source. A source that fails to load or
parse keeps last week's routes, marked with the date they were last read, and the owner is
told — a broken page never empties the table (CLAUDE.md §5).
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import requests  # noqa: E402

from lib import config, sheets, telegram, ui  # noqa: E402
from market import DIR, tariffs  # noqa: E402

JOB = "market_tariffs"
OUT = os.path.join(DIR, "tariffs.json")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}

SOURCES = {
    "onex": ("https://onex.am/en/tariff", tariffs.parse_onex, "onex_tariff_en.json"),
    "globbing": ("https://am.globbing.com/en", tariffs.parse_globbing, "globbing_home_en.html"),
    "buyforyou": ("https://www.buyforyou.am/", tariffs.parse_buyforyou, "buyforyou_home_hy.html"),
    "easytrans": ("https://api.easytrans.am/address/all-available-simple", tariffs.parse_easytrans,
                  "easytrans_address_all-available-simple.json"),
}


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch(url):
    r = requests.get(url, headers=UA, timeout=45)
    r.raise_for_status()
    r.encoding = r.encoding if r.encoding and r.encoding.lower() != "iso-8859-1" else "utf-8"
    return r.text


def load(path=OUT):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"routes": [], "sources": {}}


def refresh(previous, getter, when=None):
    """(table, report). getter(name, url, fixture) -> text. Pure apart from getter."""
    when = when or now_utc()
    prev_routes = previous.get("routes") or []
    routes, sources, failed = [], {}, []
    for name, (url, parse, fixture) in SOURCES.items():
        try:
            got = parse(getter(name, url, fixture))
            for r in got:
                r["read_utc"] = when
            routes += got
            sources[name] = {"url": url, "ok": True, "read_utc": when, "routes": len(got)}
        except Exception as e:                      # keep last week's routes for this one
            old = [r for r in prev_routes if r["forwarder"] == name]
            routes += old
            last = (previous.get("sources") or {}).get(name, {}).get("read_utc")
            sources[name] = {"url": url, "ok": False, "error": str(e)[:200],
                             "read_utc": last, "routes": len(old)}
            failed.append((name, str(e)[:120], last))
    table = {"refreshed_utc": when, "sources": sources, "routes": routes}
    changes = tariffs.diff(prev_routes, routes) if prev_routes else []
    return table, {"changes": changes, "failed": failed, "first": not prev_routes}


def report_text(table, rep):
    head = ui.header("\U0001f30d", "Market · tariffs", ui.day_label())
    body = []
    n = {k: v["routes"] for k, v in table["sources"].items()}
    body.append("Routes: " + " · ".join("%s %d" % (k.capitalize(), v) for k, v in n.items()))
    if rep["first"]:
        body.append("First read — no earlier table to compare.")
    elif rep["changes"]:
        body.append("<b>Changed since last week</b>")
        body += ["• " + telegram.esc(c) for c in rep["changes"][:30]]
    else:
        body.append("No change since last week.")
    for name, err, last in rep["failed"]:
        body.append("⚠️ %s not read (%s) — keeping the tariffs read %s"
                    % (name.capitalize(), telegram.esc(err), (last or "never")[:10]))
    return ui.page(head, body)


def main():
    ap = argparse.ArgumentParser(description="Refresh forwarder tariffs (weekly).")
    ap.add_argument("--send", action="store_true", help="tell the owner (silent message)")
    ap.add_argument("--fixtures", help="parse captured pages from this folder instead of fetching")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    cfg = config.load()

    def getter(name, url, fixture):
        if a.fixtures:
            with open(os.path.join(a.fixtures, fixture), encoding="utf-8") as f:
                return f.read()
        return fetch(url)

    try:
        table, rep = refresh(load(a.out), getter)
        text = report_text(table, rep)
        if a.send:                                   # notify before persisting (CLAUDE.md §5)
            telegram.send_html(cfg, text, silent=True)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(table, f, ensure_ascii=False, indent=1)
        sheets.log_run(cfg, JOB, "partial" if rep["failed"] else "ok",
                       "%d routes, %d changes" % (len(table["routes"]), len(rep["changes"])))
    except Exception as e:
        sheets.log_run(cfg, JOB, "error", str(e)[:300])
        if a.send:
            telegram.notify(cfg, "⚠️ SYSTEM: market tariffs errored: %s" % e)
        raise
    print(text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", ""))
    print("\n  wrote %s (%d routes)" % (os.path.relpath(a.out, ROOT), len(table["routes"])))


if __name__ == "__main__":
    main()
