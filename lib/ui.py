"""Message template and the Home screen (docs/TELEGRAM_UX.md). Layout only.

    header()  one-line title (+ optional grey subtitle)
    fold()    long content in an expandable blockquote -- tap to open
    page()    header, divider, body, folded part, footer
    home() / section()  the Home message and its six sections, each returning
              (text, inline_buttons) so the listener can send or edit in place
"""
import json
import os
from datetime import datetime, timedelta, timezone

from lib.telegram import esc

BAR = "━" * 12      # same divider as lib.fmt.BAR (kept separate: fmt imports ui)

# Armenia has had no daylight saving since 2012, so a fixed offset is exact and
# needs no tz database (this Windows Python has none).
YEREVAN = timezone(timedelta(hours=4), "Asia/Yerevan")

KEY_HOME = "\U0001f3e0 Home"
KEY_PRICE = "\U0001f50d Price check"
BOTTOM_KEYBOARD = [[KEY_HOME, KEY_PRICE]]

# The reply prompt for Price check. Telegram hands back the prompt's plain text
# in reply_to_message, so the listener recognises the answer by this phrase.
PRICE_PROMPT_MARK = "Which product?"
PRICE_PROMPT = ("\U0001f50d <b>%s</b>\n<i>Type it below, in English or Armenian: "
                "lentils, ոսպ, olive oil parma</i>" % PRICE_PROMPT_MARK)
PRICE_PLACEHOLDER = "lentils, ոսպ, olive oil"

HOME_BACK = ("⬅️ Home", "ui:home")
SECTIONS = ("today", "meals", "training", "shop", "travel", "system")


def now_local():
    return datetime.now(YEREVAN)


def day_label(dt=None):
    dt = dt or now_local()
    return "%s %d %s" % (dt.strftime("%a"), dt.day, dt.strftime("%b"))


def header(icon, title, context=None, subtitle=None):
    h = "%s <b>%s</b>" % (icon, esc(title))
    if context:
        h += " · <i>%s</i>" % esc(context)
    if subtitle:
        h += "\n<i>%s</i>" % esc(subtitle)
    return h


def fold(lines, title=None):
    """Lines folded into an expandable blockquote ('' when there are none).
    Lines may contain HTML (links, bold); they are not escaped here."""
    lines = [ln for ln in (lines or []) if ln is not None]
    while lines and not lines[0]:
        lines.pop(0)                       # blank separators only between items
    while lines and not lines[-1]:
        lines.pop()
    if not lines:
        return ""
    head = "<b>%s</b>\n" % title if title else ""
    return "<blockquote expandable>" + head + "\n".join(lines) + "</blockquote>"


def page(head, body=(), folded="", footer=None):
    out = [head, BAR] + [ln for ln in body if ln is not None]
    if folded:
        out.append(folded)
    if footer:
        out += [BAR, footer]
    return "\n".join(out)


def plan_links(root):
    """Drive links to the plan docs from config_coach.json ({} if missing)."""
    try:
        with open(os.path.join(root, "config_coach.json"), encoding="utf-8") as f:
            return json.load(f).get("plan_links") or {}
    except (OSError, ValueError):
        return {}


BASKET_BUTTON = "\U0001f9fa Basket"


def checklist_url(root):
    """The shared Shopping list Sheet (config_coach.json shopping_sheet_id), or None."""
    try:
        with open(os.path.join(root, "config_coach.json"), encoding="utf-8") as f:
            sid = json.load(f).get("shopping_sheet_id")
    except (OSError, ValueError):
        return None
    return "https://docs.google.com/spreadsheets/d/%s/edit" % sid if sid else None


def _links(links, pairs):
    """Rows of link buttons for the pairs whose link exists, two per row."""
    btns = [(label, links[key]) for label, key in pairs if links.get(key)]
    return [btns[i:i + 2] for i in range(0, len(btns), 2)]


# --------------------------------------------------------------------- Home

def home(root, running=None, travel_next=None):
    body = ["\U0001f4c5 Plan: this week's menu and everyone's training are under "
            "<b>Today</b>, <b>Meals</b> and <b>Training</b>",
            "\U0001f6d2 Prices: tap <b>%s</b> below and type a product" % esc(KEY_PRICE)]
    if travel_next:
        body.append("✈️ Next flight scan: %s" % esc(travel_next))
    if running:
        body.append("⏳ Running now: <b>%s</b> · /cancel to stop" % esc(running))
    text = page(header("\U0001f3e0", "Family assistant", day_label()), body)
    buttons = [[("\U0001f4c5 Today", "ui:today"), ("\U0001f37d Meals", "ui:meals")],
               [("\U0001f3c3 Training", "ui:training"), ("\U0001f6d2 Shopping", "ui:shop")],
               [("✈️ Travel", "ui:travel"), ("⚙️ System", "ui:system")]]
    return text, buttons


def section(name, root):
    """(text, buttons) for a Home section, or None for an unknown name."""
    links = plan_links(root)
    if name == "today":
        text = page(header("\U0001f4c5", "Today", day_label()),
                    ["Breakfast is one of the anchors: eggs, hercules or katnashor.",
                     "Lunch and dinner come from this week's menu; training times are in the "
                     "daily rhythm.",
                     "<i>Until the daily plan is sent here each morning, open it in Drive:</i>"])
        rows = _links(links, [("\U0001f4c5 Daily rhythm", "rhythm"), ("\U0001f37d This week's menu", "week")])
    elif name == "meals":
        text = page(header("\U0001f37d", "Meals"),
                    ["Breakfast anchors: eggs · hercules · katnashor",
                     "Batch cooking: Sunday ~90 min, Wednesday ~45 min",
                     "Dinner light, by 19:00 · portions, not calories"])
        rows = _links(links, [("\U0001f4c5 Week menu", "week"), ("\U0001f372 Dish list", "dishes"),
                              ("\U0001f4d6 Food rules", "food"), ("\U0001f4cb Shopping list", "shopping")])
    elif name == "training":
        text = page(header("\U0001f3c3", "Training"),
                    ["Davit: strength Mon / Wed / Fri at 18:15, desk break every 30 min",
                     "Karine: short sessions in nap time, foundations first",
                     "Everyone: a daily walk and 5–10 min of mobility"])
        rows = _links(links, [("\U0001f468 Davit", "davit"), ("\U0001f469 Karine", "karine"),
                              ("\U0001f476 Son", "son"), ("\U0001f4da Exercises", "exercises"),
                              ("\U0001f6e1 Safety rules", "safety")])
    elif name == "shop":
        text = page(header("\U0001f6d2", "Shopping"),
                    ["Prices from \U0001f7e2 Parma and \U0001f534 Yerevan City, cheapest per kg/l "
                     "first, with a comparison and product links.",
                     "English or Armenian works: lentils, ոսպ, katnashor.",
                     "\U0001f9fa <b>Basket</b> prices this week's list at both shops (~2 min), fills "
                     "the shared checklist and sends the list to both of you."])
        rows = ([[(KEY_PRICE, "ui:price"), (BASKET_BUTTON, "cmd:basket")]]
                + _links(dict(links, checklist=checklist_url(root)),
                         [("\U0001f4cb Checklist", "checklist"), ("\U0001f4c4 Shopping plan", "shopping")]))
    elif name == "travel":
        text = page(header("✈️", "Travel"),
                    ["Daily scan at 08:00; deals arrive by themselves.",
                     "Flights: <code>/flights BUD 01-30.11 7</code>",
                     "Stays: <code>/stays LCA 04-11.11 sea</code>"])
        rows = [[("✈️ Scan now", "cmd:scan"), ("\U0001f4ca Digest", "cmd:digest")],
                [("⚙️ Automation", "cmd:auto")]]
    elif name == "system":
        text = page(header("⚙️", "System"),
                    ["Bot health, scheduled jobs, and stopping a running job."])
        rows = [[("\U0001f4f6 Status", "cmd:status"), ("⛔ Cancel job", "cmd:cancel")],
                [("⚙️ Automation", "cmd:auto"), ("❓ Help", "ui:help")]]
    else:
        return None
    return text, rows + [[HOME_BACK]]
