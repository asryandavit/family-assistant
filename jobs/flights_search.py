"""On-demand flight search: /flights <dest> <window> [nights] [noopen]

    python jobs/flights_search.py BUD 01-30.11 7
    python jobs/flights_search.py VCE 01-30.11 8-11
    python jobs/flights_search.py LCA 18-21.09 2-3 noopen

Uses the booking-page farechart endpoint, which respects dates on a specific
route -- unlike the fare finder the daily scan uses. Writes results to the
FlightSearch tab and sends a ranked message to Telegram.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import config, flights, fmt_flights, parse_booking, sheets, telegram
from scrapers import stays as _stays_helper   # city_name_for
from scrapers import wizz_booking

JOB = "flights_search"


def run(cfg, q, notify=True):
    sheets.flush_pending(cfg)
    dest = q["dest"]
    code = dest.upper() if (len(dest) == 3 and dest.isalpha()) else dest
    city = _stays_helper.city_name_for(cfg, code) if len(code) == 3 else dest

    reqs = flights.plan_requests(cfg, code, q["window_from"], q["window_to"],
                                 q["include_openjaw"])
    print("  %d booking page(s) to load" % len(reqs))

    res = wizz_booking.fetch(cfg, reqs)
    if res["status"] != "ok":
        msg = ("\u26a0\ufe0f <b>Flights</b> \u2014 %s while searching %s."
               % (res["status"], telegram.esc(city)))
        if notify:
            telegram.send_html(cfg, msg)
        sheets.log_run(cfg, JOB, res["status"], res.get("detail", "")[:120])
        return []

    rows = parse_booking.parse(res["payloads"])
    print("  %d price-date row(s)" % len(rows))

    options = flights.assemble(cfg, rows, code, q["window_from"],
                               q["window_to"], q["nights"])
    print("  %d option(s) after gates" % len(options))

    if notify:
        telegram.send_html(cfg, fmt_flights.build(cfg, q, city, options))

    run_date = date.today().isoformat()
    ok = sheets.append_rows(cfg, "FlightSearch", [[
        run_date, code, q["window_from"], q["window_to"], o["kind"], o["route"],
        o["out_date"], o["back_date"], o["nights"], o["pax"],
        o["out_price"], o["in_price"], o["ground"], o["total"], o["link"],
    ] for o in options[:25]])
    if not ok:
        print("  (queued for the sheet; will replay next run)")

    sheets.log_run(cfg, JOB, "ok", "%s %s..%s %d option(s)"
                   % (code, q["window_from"], q["window_to"], len(options)))
    return options


def main():
    cfg = config.load()
    q = flights.parse_command(" ".join(sys.argv[1:]), cfg)
    if "error" in q:
        print(q["error"].replace("<code>", "").replace("</code>", ""))
        return
    print("  query:", q)
    try:
        opts = run(cfg, q)
        if opts:
            print("\n  %-9s %-11s %-11s %3s %8s  %s"
                  % ("KIND", "OUT", "BACK", "N", "TOTAL", "GROUND LINK"))
            for o in opts[:15]:
                print("  %-9s %-11s %-11s %3d %8s  %s"
                      % (o["kind"], o["out_date"], o["back_date"], o["nights"],
                         "$%.2f" % o["total"], o["link"]))
    except Exception as e:
        sheets.log_run(cfg, JOB, "error", str(e)[:300])
        telegram.notify(cfg, "\u26a0\ufe0f SYSTEM: flight search errored: %s" % e)
        raise


if __name__ == "__main__":
    main()
