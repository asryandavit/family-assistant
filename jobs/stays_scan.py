"""On-demand accommodation search: /stays <city> <dates> [keywords]

    python jobs/stays_scan.py LCA 04-11.11 sea center

Searches Booking and Airbnb, normalizes to true nightly cost, ranks with
areas.json, writes every result to the Stays tab and sends the top few to
Telegram. Degrades gracefully: if one site is blocked the other still reports,
and a prefilled manual link is always included.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import config, fmt, parse_cmd, parse_stays, score_stays, sheets, telegram
from scrapers import stays as stays_scraper

JOB = "stays_scan"


def run(cfg, q, notify=True):
    sheets.flush_pending(cfg)
    city_name = stays_scraper.city_name_for(cfg, q["city"])
    all_rows, blocked, links = [], [], {}

    for site in ("booking", "airbnb"):
        res = stays_scraper.search(cfg, site, city_name, q)
        links[site] = res["url"]
        if res["status"] in ("blocked", "error"):
            blocked.append(site)
            continue
        parser = parse_stays.parse_booking if site == "booking" else parse_stays.parse_airbnb
        rows = parser(res["html"], q["nights"])
        print("  [%s] parsed %d" % (site, len(rows)))
        all_rows += rows

    if not all_rows:
        msg = ("\u26a0\ufe0f <b>Stays</b> \u2014 nothing retrieved for %s.\n%s"
               % (city_name, fmt.links_line(links)))
        if notify:
            telegram.send_html(cfg, msg)
        sheets.log_run(cfg, JOB, "empty", "blocked: %s" % ",".join(blocked))
        return []

    ranked = score_stays.rank(all_rows, cfg, q["nights"], q["flags"],
                              q.get("budget"), q["city"])
    print("  ranked %d of %d after filters" % (len(ranked), len(all_rows)))

    # Notify first: a scrape that succeeded should reach the phone even if
    # Google is having a bad minute.
    if notify:
        telegram.send_html(cfg, fmt.build_stays(cfg, q, city_name, ranked,
                                                links, blocked))

    run_date = date.today().isoformat()
    ok = sheets.append_rows(cfg, "Stays", [[
        run_date, q["city"], q["checkin"], q["checkout"], q["nights"],
        r["source"], r["name"][:80], r.get("rating"), r.get("price_night"),
        r.get("true_nightly"), r.get("price_total"), r.get("currency"),
        r.get("loc_score"), r.get("loc_why"), r.get("score"), r.get("url"),
    ] for r in ranked])
    if not ok:
        print("  (results queued for the sheet; they will replay next run)")
    sheets.log_run(cfg, JOB, "ok",
                   "%s %s %d results%s" % (q["city"], q["checkin"], len(ranked),
                                           " (blocked: %s)" % ",".join(blocked) if blocked else ""))
    return ranked


def main():
    cfg = config.load()
    text = " ".join(sys.argv[1:])
    q = parse_cmd.parse(text, cfg)
    if "error" in q:
        print(q["error"])
        return
    print("  query:", q)
    try:
        run(cfg, q)
    except Exception as e:
        sheets.log_run(cfg, JOB, "error", str(e)[:300])
        telegram.notify(cfg, "\u26a0\ufe0f SYSTEM: stays scan errored: %s" % e)
        raise


if __name__ == "__main__":
    main()
