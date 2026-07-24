"""Build the Telegram HTML messages. Layout only -- all numbers arrive computed."""
from datetime import date

from lib.telegram import esc

SYM = {"USD": "$", "EUR": "\u20ac", "AMD": "\u058f", "GBP": "\u00a3"}
BAR = "\u2501" * 12


def _money(v, cur):
    if v in ("", "-", None):
        return ""
    return f"{SYM.get(cur, cur + ' ')}{v:g}" if isinstance(v, (int, float)) else str(v)


def _dm(iso):
    d = date.fromisoformat(iso)
    return d.strftime("%d %b").lstrip("0")


def _mon(ym):
    return date.fromisoformat(ym + "-01").strftime("%b %y")


def _sheet_link(cfg):
    sid = cfg.get("spreadsheet_id", "")
    return f'<a href="https://docs.google.com/spreadsheets/d/{sid}">\U0001f4ca Sheet</a>' if sid else ""


def _trip_line(t):
    cur = t["currency"]
    route = esc(t["route"]) if t["kind"] == "return" else esc(t["out_city"]) + "\u21e2" + esc(t["in_city"])
    wdc = f' <i>(WDC {_money(t["wdc"], cur)})</i>' if t["wdc"] not in ("", "-") else ""
    return (f'\u2022 <b>{route}</b> {_dm(t["out_date"])}\u2192{_dm(t["back_date"])} '
            f'\u00b7 {t["nights"]}n \u00b7 {esc(t["pax"])} \u2014 '
            f'<b>{_money(t["total"], cur)}</b>{wdc} <code>{t["id"]}</code>')


def build_alert(cfg, drops, new_routes, trip_new, trip_drops, insight=""):
    home = cfg["wizz"].get("origin_code", "EVN")
    now = date.today()
    out = [f'\u2708\ufe0f <b>TRAVEL \u00b7 Deals</b>',
           f'<i>{now.strftime("%d %b")}</i>', BAR]

    for d in drops:
        city = d["d"] if d["o"] == home else d["o"]
        back = "" if d["o"] == home else " \u2190"  # inbound leg marker
        tag = " \U0001f53b <b>all-time low</b>" if d["atl"] else ""
        out.append(f'\U0001f4c9 <b>{esc(city)}</b>{back} {_mon(d["month"])}  '
                   f'${d["prev"]:g} \u2192 <b>${d["now"]:g}</b> ({d["pct"]:+g}%){tag}')

    for n in new_routes:
        city = n["d"] if n["o"] == home else n["o"]
        back = "" if n["o"] == home else " \u2190"
        out.append(f'\U0001f195 <b>{esc(city)}</b>{back} '
                   f'from ${n["price"]:g} ({_mon(n["month"])})')

    if trip_new or trip_drops:
        out += ["", "\U0001f9e9 <b>Trips</b>"]
        for t in trip_drops:
            out.append(_trip_line(t) + f'  \U0001f4c9 was ${t["prev_total"]:g}')
        for t in trip_new:
            out.append(_trip_line(t))

    if insight:
        out += ["", f'\U0001f4a1 <i>{esc(insight)}</i>']

    out += [BAR, _sheet_link(cfg)]
    return "\n".join(x for x in out if x is not None)


def build_digest(cfg, trips, cheapest_legs, insight=""):
    now = date.today()
    out = [f'\u2708\ufe0f <b>TRAVEL \u00b7 Weekly digest</b>',
           f'<i>{now.strftime("%d %b")}</i>', BAR]
    if trips:
        out.append("\U0001f9e9 <b>Best current trips</b>")
        out += [_trip_line(t) for t in trips[:8]]
    if cheapest_legs:
        out += ["", "\U0001fab6 <b>Cheapest legs</b>"]
        for f in cheapest_legs[:8]:
            arrow = f'{esc(f["origin"])}\u2192{esc(f["destination"])}'
            out.append(f'\u2022 {arrow} {_dm(f["out_date"])} \u2014 '
                       f'<b>{_money(f["regular"], f["currency"])}</b>')
    if insight:
        out += ["", f'\U0001f4a1 <i>{esc(insight)}</i>']
    out += [BAR, _sheet_link(cfg)]
    return "\n".join(out)


def links_line(links):
    bits = []
    for site, url in (links or {}).items():
        if url:
            bits.append('<a href="%s">%s</a>' % (url, site.capitalize()))
    return " \u00b7 ".join(bits)


def _stay_line(i, r):
    cur = SYM.get(r.get("currency", "USD"), "$")
    src = "\U0001f3e8" if r["source"] == "booking" else "\U0001f3e0"
    true_n = r.get("true_nightly")
    night = r.get("price_night")
    price = "<b>%s%g</b>/n" % (cur, true_n if true_n else night)
    if true_n and night and abs(true_n - night) > 0.5:
        price += " <i>(%s%g + %s)</i>" % (cur, night, esc(r.get("cost_note", "").strip("+ ")))
    total = " \u00b7 %s%g total" % (cur, r["price_total"]) if r.get("price_total") else ""
    rating = " \u00b7 %.1f" % r["rating"] if r.get("rating") else ""
    tags = []
    if r.get("genius"):
        tags.append("genius")
    if r.get("breakfast"):
        tags.append("breakfast")
    if r.get("free_cancel"):
        tags.append("free cxl")
    tags += list(r.get("hard_notes") or [])
    tag_s = " \u00b7 " + esc(", ".join(tags)) if tags else ""
    name = esc(r["name"][:52])
    url = r.get("url")
    title = '<a href="%s">%s</a>' % (url, name) if url else name
    return ("%d. %s %s\n   %s%s%s\n   <i>%s</i>%s"
            % (i, src, title, price, total, rating,
               esc(r.get("loc_why", "")), tag_s))


def build_stays(cfg, q, city_name, ranked, links, blocked=None):
    n = (cfg.get("stays") or {}).get("max_results", 6)
    ci = date.fromisoformat(q["checkin"]); co = date.fromisoformat(q["checkout"])
    who = "2 adults + infant" if q["child_age"] < 2 else "2 adults + child"
    head = ("\U0001f3e8 <b>STAYS \u00b7 %s</b>\n<i>%s\u2013%s \u00b7 %dn \u00b7 %s</i>"
            % (esc(city_name), _dm(q["checkin"]), _dm(q["checkout"]), q["nights"], who))
    if q.get("flags") or q.get("budget"):
        bits = list(q.get("flags") or [])
        if q.get("budget"):
            bits.append("budget %d" % q["budget"])
        head += "\n<i>filters: %s</i>" % esc(", ".join(bits))
    out = [head, BAR]
    if not ranked:
        out.append("Nothing matched the filters. Try loosening them.")
    for i, r in enumerate(ranked[:n], 1):
        out.append(_stay_line(i, r))
    if len(ranked) > n:
        out.append("<i>\u2026and %d more in the sheet</i>" % (len(ranked) - n))
    if blocked:
        out.append("\u26a0\ufe0f <i>%s unavailable this run \u2014 open the link to check manually</i>"
                   % esc(", ".join(b.capitalize() for b in blocked)))
    out += [BAR, links_line(links) + " \u00b7 " + _sheet_link(cfg)]
    return "\n".join(out)


def stay_buttons(trips, limit=4):
    """A row of stay-search buttons per trip; open-jaw offers both cities.

    callback_data must stay under Telegram's 64-byte cap, so it carries only
    the trip id and city -- everything else is looked up from the Trips tab.
    """
    rows = []
    for t in (trips or [])[:limit]:
        if t["kind"] == "openjaw":
            rows.append([
                ("\U0001f3e8 %s" % t["out_city"], "st:%s:%s" % (t["id"], t["out_city"])),
                ("\U0001f3e8 %s" % t["in_city"], "st:%s:%s" % (t["id"], t["in_city"])),
            ])
        else:
            rows.append([("\U0001f3e8 Stays in %s \u00b7 %s"
                          % (t["route"], _dm(t["out_date"])),
                          "st:%s:%s" % (t["id"], t["out_city"]))])
    return rows


# Short codes keep callback_data well under Telegram's 64-byte cap.
FLAG_CODES = [("s", "sea", "\U0001f30a Sea"), ("c", "center", "\U0001f3db Centre"),
              ("q", "quiet", "\U0001f92b Quiet"), ("a", "apt", "\U0001f3e0 Apartment"),
              ("p", "pool", "\U0001f3ca Pool"), ("b", "breakfast", "\U0001f373 Breakfast")]
CODE_TO_FLAG = {c: f for c, f, _ in FLAG_CODES}
DATE_MODES = {"0": "whole trip", "1": "first half", "2": "second half"}


def panel_text(city, ci, co, nights, flags, mode):
    picked = ", ".join(flags) if flags else "none"
    return ("\U0001f3e8 <b>Stays in %s</b>\n"
            "<i>%s \u2192 %s \u00b7 %dn \u00b7 %s</i>\n"
            "Filters: <b>%s</b>\n\n"
            "Tap to toggle, then Search.\n"
            "For other dates: <code>/stays %s %s-%s %s</code>"
            % (esc(city), _dm(ci), _dm(co), nights, DATE_MODES.get(mode, ""),
               esc(picked), esc(city),
               date.fromisoformat(ci).strftime("%d.%m"),
               date.fromisoformat(co).strftime("%d.%m"),
               " ".join(flags)))


def panel_buttons(trip_id, city, codes, mode):
    """codes: set of short flag codes currently selected."""
    def cb(kind, c=None, m=None):
        cs = ",".join(sorted(c if c is not None else codes)) or "-"
        return "%s:%s:%s:%s:%s" % (kind, trip_id, city, cs, m if m else mode)

    rows, row = [], []
    for code, _flag, label in FLAG_CODES:
        on = code in codes
        new = set(codes) ^ {code}
        row.append((("\u2705 " if on else "") + label, cb("o", new)))
        if len(row) == 3:
            rows.append(row); row = []
    if row:
        rows.append(row)

    nxt = {"0": "1", "1": "2", "2": "0"}[mode]
    rows.append([("\U0001f4c5 %s" % DATE_MODES[mode], cb("o", None, nxt)),
                 ("\U0001f50d Search", cb("g"))])
    return rows


def auto_text(rows):
    out = ["\u2699\ufe0f <b>Automation</b>", BAR]
    for r in rows:
        if not r.get("exists"):
            out.append("\u26aa <b>%s</b> \u2014 <i>not registered</i>" % esc(r["label"]))
            continue
        if r.get("running"):
            dot, state = "\U0001f7e1", "running now"
        elif r.get("enabled"):
            dot, state = "\U0001f7e2", "on"
        else:
            dot, state = "\U0001f534", "off"
        line = "%s <b>%s</b> \u2014 %s" % (dot, esc(r["label"]), state)
        if r.get("enabled") and r.get("next_short") not in ("\u2014", None):
            line += "\n    next %s" % esc(r["next_short"])
        if r.get("last_short") not in ("\u2014", None):
            res = r.get("last_result", "")
            ok = res.strip() in ("0", "0x0")
            line += " \u00b7 last %s%s" % (esc(r["last_short"]),
                                            "" if ok else " \u26a0\ufe0f")
        out.append(line)
    out += [BAR, "<i>Off means the schedule won\u2019t fire; commands still work.</i>"]
    return "\n".join(out)


def auto_buttons(rows):
    btns = []
    for r in rows:
        if not r.get("exists") or not r.get("toggle"):
            continue
        key = r["key"]
        # State only -- triggering lives in /menu and the slash commands.
        if r.get("enabled"):
            btns.append([("\u23f8 Pause %s" % r["label"], "sw:%s:0" % key)])
        else:
            btns.append([("\u25b6 Enable %s" % r["label"], "sw:%s:1" % key)])
    btns.append([("\U0001f504 Refresh", "sw:x:v")])
    return btns
