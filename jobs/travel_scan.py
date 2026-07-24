import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import claude, config, fmt, movement, parse_wizz, sheets, trips
from lib import telegram
from scrapers import wizz_fare_finder

JOB = "travel_scan"


def _insight(cfg, payload):
    """Optional one-line comment from Claude. Any failure -> no insight."""
    try:
        out = claude.run(cfg, "prompts/travel_analysis.md", data=payload)
        line = (out or {}).get("insight", "")
        return line if isinstance(line, str) and len(line) < 300 else ""
    except Exception as e:
        print("  insight skipped:", str(e)[:120])
        return ""


def main():
    force_digest = "--digest" in sys.argv
    cfg = config.load()
    today = date.today().isoformat()
    alerts_cfg = cfg.get("alerts", {})
    sheets.flush_pending(cfg)

    try:
        result = wizz_fare_finder.scrape(cfg)

        if result["status"] == "blocked":
            sheets.log_run(cfg, JOB, "blocked", result.get("detail", ""))
            telegram.notify(cfg, "\u26a0\ufe0f SYSTEM: travel scan blocked by a verification page. Skipped.")
            return
        if result["status"] == "discovery":
            sheets.log_run(cfg, JOB, "discovery", result.get("hint", ""))
            return

        fares = parse_wizz.parse(result["raw"])
        print(f"  parsed {len(fares)} unique fares")
        if not fares:
            sheets.log_run(cfg, JOB, "empty", "no fares parsed")
            telegram.notify(cfg, "\u26a0\ufe0f SYSTEM: travel scan parsed 0 fares.")
            return

        # --- movement: read history BEFORE appending today's rows ---
        hist = movement.load_history(sheets.read_all(cfg, "Flights"))
        has_prior = any(any(rd < today for rd in runs) for runs in hist.values())
        movement.merge_today(hist, fares, today)
        drops, new_routes, _ = movement.analyze(hist, today, alerts_cfg)
        if not has_prior:  # first run ever: establish baseline quietly
            drops, new_routes = [], []

        sheets.append_rows(cfg, "Flights", parse_wizz.to_sheet_rows(fares, today))
        print(f"  wrote {len(fares)} rows to Flights")

        # --- trips: assemble, compare against Trips history, then append ---
        trips_today = trips.assemble(fares, cfg)
        trip_hist_rows = sheets.read_all(cfg, "Trips")
        trip_new, trip_drops = trips.analyze(trip_hist_rows, trips_today, today, alerts_cfg)
        sheets.append_rows(cfg, "Trips", trips.to_sheet_rows(trips_today, today))
        print(f"  wrote {len(trips_today)} trips ({len(trip_new)} new-cheap, {len(trip_drops)} dropped)")

        if not has_prior:
            trip_new, trip_drops = [], []
        notable = bool(drops or new_routes or trip_new or trip_drops)
        is_digest_day = date.today().weekday() == alerts_cfg.get("digest_weekday", 6)

        if force_digest or not has_prior:
            note = "" if has_prior else "Baseline established - movement alerts start from the next run"
            telegram.send_html(cfg, fmt.build_digest(cfg, trips_today, fares, note),
                               buttons=fmt.stay_buttons(trips_today))
            sheets.log_run(cfg, JOB, "ok", "digest sent (baseline)" if not has_prior else "digest sent (forced)")
        elif notable:
            payload = {"today": today, "drops": drops, "new_routes": new_routes,
                       "trips_new": trip_new, "trip_drops": trip_drops,
                       "date_windows": cfg.get("watchlist", {}).get("date_windows", []),
                       "passenger_rule": cfg.get("passengers", {})}
            line = _insight(cfg, payload)
            telegram.send_html(cfg, fmt.build_alert(cfg, drops, new_routes,
                                                    trip_new, trip_drops, line),
                               buttons=fmt.stay_buttons(trip_drops + trip_new))
            sheets.log_run(cfg, JOB, "ok", f"alert: {len(drops)}d/{len(new_routes)}n/"
                                           f"{len(trip_new)+len(trip_drops)}t")
        elif is_digest_day:
            telegram.send_html(cfg, fmt.build_digest(cfg, trips_today, fares),
                               silent=True, buttons=fmt.stay_buttons(trips_today))
            sheets.log_run(cfg, JOB, "ok", "digest sent")
        else:
            sheets.log_run(cfg, JOB, "ok", "quiet - no notable changes")
            print("  quiet day: nothing notable, no message sent")

    except Exception as e:
        sheets.log_run(cfg, JOB, "error", str(e)[:300])
        telegram.notify(cfg, f"\u26a0\ufe0f SYSTEM: travel scan errored: {e}")
        raise


if __name__ == "__main__":
    main()
