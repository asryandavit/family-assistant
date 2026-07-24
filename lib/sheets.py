"""Google Sheets writes that survive Google having a bad minute.

Three things learned the hard way:
  * 5xx/429 from the Sheets API are transient -- retry with exponential backoff
    instead of discarding an entire scrape.
  * Opening the spreadsheet on every call costs extra round-trips and invites
    rate limiting, so the client and spreadsheet handle are cached.
  * If a write still fails, rows are queued to disk and replayed on the next
    successful run. Nothing collected is ever silently lost.

log_run() never raises: an error path must not fail inside the error path.
"""
import json
import os
import random
import time

import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TRANSIENT = {429, 500, 502, 503, 504}
MAX_TRIES = 5

# A fully populated first row fixes the table width, so Google's append
# auto-detection can't split data into blocks when a column is sparse.
HEADERS = {
    "Flights": ["run_date", "origin", "destination", "out_date", "out_time",
                "back_date", "type", "regular", "wdc", "currency", "src"],
    "Trips": ["run_date", "trip_id", "kind", "route", "out_date", "back_date",
              "nights", "pax", "total", "wdc_total", "currency"],
    "Stays": ["run_date", "city", "checkin", "checkout", "nights", "source",
              "name", "rating", "price_night", "true_nightly", "price_total",
              "currency", "loc_score", "loc_why", "score", "url"],
    "Runs": ["timestamp", "job", "status", "note"],
    "Training": ["date", "session", "exercise", "sets_reps", "notes"],
    "Meals": ["date", "meal", "dish", "ingredients", "notes"],
}

_cache = {}


def _status(e):
    r = getattr(e, "response", None)
    return getattr(r, "status_code", None)


def _retry(fn, *args, **kwargs):
    delay, last = 2.0, None
    for attempt in range(MAX_TRIES):
        try:
            return fn(*args, **kwargs)
        except APIError as e:
            if _status(e) not in TRANSIENT:
                raise
            last = e
            if attempt < MAX_TRIES - 1:
                wait = delay + random.uniform(0, 1)
                print("  sheets: %s, retrying in %.0fs" % (_status(e), wait))
                time.sleep(wait)
                delay = min(delay * 2, 30)
    raise last


def _spreadsheet(cfg):
    key = cfg["spreadsheet_id"]
    if key not in _cache:
        path = os.path.join(cfg["_root"], cfg["service_account_file"])
        creds = Credentials.from_service_account_file(path, scopes=SCOPES)
        client = gspread.authorize(creds)
        _cache[key] = _retry(client.open_by_key, key)
    return _cache[key]


def _sheet(cfg, tab):
    ss = _spreadsheet(cfg)
    try:
        return ss.worksheet(tab)
    except gspread.WorksheetNotFound:
        ws = _retry(ss.add_worksheet, title=tab, rows=2000, cols=24)
        _cache.pop(cfg["spreadsheet_id"], None)  # refresh cached metadata
        return ws


# ---------- offline queue ----------

def _queue_path(cfg):
    d = os.path.join(cfg["_root"], ".browser")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "pending_sheets.jsonl")


def _enqueue(cfg, tab, rows):
    try:
        with open(_queue_path(cfg), "a", encoding="utf-8") as f:
            f.write(json.dumps({"tab": tab, "rows": rows}, ensure_ascii=False) + "\n")
        print("  sheets: queued %d rows for %s (will retry next run)" % (len(rows), tab))
    except OSError as e:
        print("  sheets: could not queue rows: %s" % e)


def flush_pending(cfg):
    """Replay anything queued by an earlier failed write."""
    path = _queue_path(cfg)
    if not os.path.exists(path):
        return 0
    try:
        with open(path, encoding="utf-8") as f:
            items = [json.loads(x) for x in f if x.strip()]
    except (OSError, ValueError):
        return 0
    done = 0
    for it in items:
        if _append(cfg, it["tab"], it["rows"]):
            done += len(it["rows"])
        else:
            return done  # still failing: keep the file for next time
    try:
        os.remove(path)
        print("  sheets: replayed %d queued rows" % done)
    except OSError:
        pass
    return done


# ---------- public API ----------

def _append(cfg, tab, rows):
    try:
        ws = _sheet(cfg, tab)
        if not _retry(ws.acell, "A1").value and tab in HEADERS:
            _retry(ws.update, values=[HEADERS[tab]], range_name="A1")
        _retry(ws.append_rows, rows, value_input_option="USER_ENTERED",
               table_range="A1")
        return True
    except Exception as e:
        print("  sheets: write failed (%s)" % str(e)[:120])
        return False


def append_rows(cfg, tab, rows):
    """Append rows anchored to column A. Returns True on success.

    On failure the rows are queued to disk rather than lost, and False is
    returned so callers can carry on (a Telegram alert still goes out).
    """
    if not rows:
        return True
    if not _append(cfg, tab, rows):
        _enqueue(cfg, tab, rows)
        return False
    return True


def read_all(cfg, tab):
    """All rows of a tab minus the header. Empty list if unavailable."""
    try:
        ws = _sheet(cfg, tab)
        values = _retry(ws.get_all_values)
    except Exception as e:
        print("  sheets: read failed (%s)" % str(e)[:120])
        return []
    if not values:
        return []
    first = values[0][0] if values[0] else ""
    return values[1:] if first in ("run_date", "timestamp", "date") else values


def log_run(cfg, job, status, note=""):
    """Best-effort run log. Never raises -- error paths depend on it."""
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        append_rows(cfg, "Runs", [[ts, job, status, note]])
    except Exception as e:
        print("  sheets: log_run suppressed (%s)" % str(e)[:100])
