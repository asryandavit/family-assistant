"""Telegram message for /flights.

Separate module rather than an addition to fmt.py, so nothing the daily scan
depends on is touched. Shared helpers are imported from fmt.
"""
from datetime import date

from lib import places
from lib.fmt import BAR, _dm, _sheet_link
from lib.telegram import esc

BOOK = ("https://www.wizzair.com/en-gb/booking/select-flight"
        "/{f}/{t}/{d1}/{d2}/{a}/{c}/{i}/null")


def book_url(cfg, o):
    fl = cfg.get("flights", {})
    a, c, i = fl.get("adults", 2), 0, fl.get("infants", 1)
    home = cfg["wizz"].get("origin_code", "EVN")
    if o["kind"] == "return":
        return BOOK.format(f=home, t=o["out_city"], d1=o["out_date"],
                           d2=o["back_date"], a=a, c=c, i=i)
    # open jaw books as two one-ways; link the outbound leg
    return BOOK.format(f=home, t=o["out_city"], d1=o["out_date"],
                       d2="null", a=a, c=c, i=i)


def _line(cfg, n, o):
    icon = "\U0001f501" if o["kind"] == "return" else "\U0001f500"
    if o["kind"] == "return":
        route = esc(places.label(cfg, o["out_city"]))
    else:
        route = (esc(places.label(cfg, o["out_city"])) + "→"
                 + esc(places.label(cfg, o["in_city"])))
    head = ('%d. %s <b><a href="%s">%s</a></b>  <b>$%g</b>'
            % (n, icon, book_url(cfg, o), route, o["total"]))
    body = ("   %s \u2192 %s \u00b7 %dn \u00b7 %s"
            % (_dm(o["out_date"]), _dm(o["back_date"]), o["nights"],
               esc(o["pax"])))
    parts = ["$%g out" % o["out_price"], "$%g back" % o["in_price"]]
    if o.get("ground"):
        parts.append("$%g ground" % o["ground"])
    if o.get("infant_fee"):
        parts.append("$%g infant" % o["infant_fee"])
    detail = "   <i>%s</i>" % esc(" + ".join(parts))
    out = [head, body, detail]
    if o.get("link"):
        out.append("   <i>\U0001f686 %s</i>" % esc(o["link"]))
    return "\n".join(out)


def build(cfg, q, city_name, options, limit=6, note=""):
    n_min, n_max = q["nights"]
    nights = "%d" % n_min if n_min == n_max else "%d\u2013%d" % (n_min, n_max)
    head = ("\u2708\ufe0f <b>FLIGHTS \u00b7 %s</b>\n"
            "<i>%s\u2013%s \u00b7 %s nights \u00b7 2 adults + infant</i>"
            % (esc(city_name), _dm(q["window_from"]), _dm(q["window_to"]), nights))
    out = [head, BAR]
    if not options:
        out.append("No combination fits that window.")
        out.append("<i>Wizz flies most routes 2\u20133 times a week, so a short "
                   "window often has no valid pair. Try a wider one.</i>")
    for i, o in enumerate(options[:limit], 1):
        out.append(_line(cfg, i, o))
    if len(options) > limit:
        out.append("<i>\u2026and %d more</i>" % (len(options) - limit))
    if note:
        out.append("\n<i>%s</i>" % esc(note))
    out += [BAR, "<i>Totals are seats + infant fee. Bags extra.</i>",
            _sheet_link(cfg)]
    return "\n".join(out)
