"""Working days and estimated arrival dates (docs/briefs/MARKET_WATCH.md §3a).

A route's time is kept exactly as the forwarder states it:
    {"min": 5, "max": 10, "unit": "working" | "calendar" | "months", "from": "arrival" | "dispatch"}
Working days are Monday–Friday that are not in market/holidays.md. Months are counted as
calendar days (1 month = 30.44 days, rounded) because the forwarders publish sea times as
"≈ 3,5 months". Dates are Yerevan dates (lib.ui.YEREVAN), never date.today().
"""
import os
import re
from datetime import date, timedelta

from market import DIR

DAYS_PER_MONTH = 30.44
HOLIDAY_RE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) · ")

_holidays = None


def load_holidays(path=None):
    out = set()
    with open(path or os.path.join(DIR, "holidays.md"), encoding="utf-8") as f:
        for line in f:
            m = HOLIDAY_RE.match(line.strip())
            if m:
                out.add(date.fromisoformat(m.group(1)))
    return frozenset(out)


def holidays():
    global _holidays
    if _holidays is None:
        _holidays = load_holidays()
    return _holidays


def is_working(d, hol=None):
    return d.weekday() < 5 and d not in (holidays() if hol is None else hol)


def add_working_days(start, n, hol=None):
    """The date n working days after start (start itself is not counted)."""
    d = start
    left = int(n)
    while left > 0:
        d += timedelta(days=1)
        if is_working(d, hol):
            left -= 1
    return d


def add_days(start, n, unit, hol=None):
    if unit == "working":
        return add_working_days(start, n, hol)
    if unit == "calendar":
        return start + timedelta(days=int(n))
    if unit == "months":
        return start + timedelta(days=round(n * DAYS_PER_MONTH))
    raise ValueError("unknown day unit: %r" % unit)


def arrival(today, days, store_arrival=None, wait_days=None, hol=None):
    """{"earliest", "latest", "notes"} or None when the route has no published time.

    store_arrival: the date the store delivers to the warehouse (from the product page);
    None -> counted from today and noted. wait_days: the forwarder's wait until dispatch
    (working days) for routes counted from dispatch; None -> "after dispatch" noted.
    """
    if not days or days.get("min") is None:
        return None
    notes = []
    start = today
    if store_arrival and store_arrival > today:
        start = store_arrival
    elif store_arrival is None:
        notes.append("store time unknown")
    if days.get("from") == "dispatch":
        if wait_days is None:
            notes.append("after dispatch")
        else:
            start = add_working_days(start, wait_days, hol)
    lo = add_days(start, days["min"], days["unit"], hol)
    hi = add_days(start, days.get("max") or days["min"], days["unit"], hol)
    return {"earliest": lo, "latest": hi, "notes": notes}


UNIT_LABEL = {"working": "wd", "calendar": "days", "months": "months"}


def range_text(days):
    """'5–10 wd', '45 wd', '~3.5 months'."""
    if not days or days.get("min") is None:
        return "time not published"
    lo, hi = days["min"], days.get("max") or days["min"]
    fmt = (lambda x: ("%g" % x))
    span = fmt(lo) if lo == hi else "%s–%s" % (fmt(lo), fmt(hi))
    if days.get("up_to"):
        span = "≤" + fmt(hi)
    if days["unit"] == "months":
        return "~%s months" % span
    return "%s %s" % (span, UNIT_LABEL[days["unit"]])


def date_text(a):
    """'~Mon 9 – Mon 16 Nov' (month shown once when both dates share it)."""
    if not a:
        return ""
    lo, hi = a["earliest"], a["latest"]

    def day(d):
        return "%s %d" % (d.strftime("%a"), d.day)
    if lo == hi:
        text = "~%s %s" % (day(lo), lo.strftime("%b"))
    elif (lo.year, lo.month) == (hi.year, hi.month):
        text = "~%s – %s %s" % (day(lo), day(hi), hi.strftime("%b"))
    else:
        text = "~%s %s – %s %s" % (day(lo), lo.strftime("%b"), day(hi), hi.strftime("%b"))
    if a["notes"]:
        text += " (%s)" % ", ".join(a["notes"])
    return text
