"""The "Watch list" Google Sheet: tabs items / offers / history (brief §3).

Uses the platform's checklist writer (lib/sheets_checklist.py: whole-tab rewrite, another
spreadsheet, same service account and retry) — no lib/ change. The Sheet id lives in
config_market.json `watch_sheet_id`; unset -> the Sheet is skipped and the report says so.

items is editable from a phone. Before any change the bot reads it and merges:
    * a row with a known id updates that item's name, links, qty, weight, size, status, notes
      (a value that doesn't parse keeps the old one and is reported, never half-applied)
    * a row without an id but with a name and a link becomes a new item
    * an item missing from the Sheet is kept (to drop one, set its status to removed)
A failed read changes nothing.
"""
from lib import sheets_checklist
from lib.sheets import _retry
from market import state, stores as stores_mod

ITEMS = ["id", "name", "mode", "links", "keywords", "stores", "qty", "weight_kg", "size_cm",
         "max_age", "added_by", "status", "notes"]
OFFERS = ["item_id", "item", "store", "title", "price", "currency", "in_store_shipping",
          "stock", "state", "date_local", "link", "seen_utc"]
HISTORY = ["date_local", "item_id", "item", "best_total_amd", "store", "route", "source"]


def cell(v):
    """Text that can't turn into a formula under USER_ENTERED."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def size_text(size):
    return "x".join("%g" % v for v in size) if size else ""


def item_rows(items, store_rows=None):
    store_rows = store_rows or stores_mod.load()
    rows = [ITEMS]
    for it in items:
        keys = []
        for u in it.get("links", []):
            s = stores_mod.store_for_url(u, store_rows)
            keys.append(s["key"] if s else "?")
        rows.append([it["id"], cell(it["name"]), it.get("mode", "exact"), cell("\n".join(it.get("links", []))),
                     "", ", ".join(keys), it.get("qty", 1),
                     "" if it.get("weight_kg") is None else it["weight_kg"],
                     size_text(it.get("size_cm")), "", cell(it.get("added_by", "")),
                     it.get("status", "active"), cell(it.get("notes", ""))])
    return rows


def merge(items, rows):
    """(merged items, problems) from the items tab's values (header first)."""
    if not rows:
        return items, []
    head = [h.strip().lower() for h in rows[0]]
    if "id" not in head or "name" not in head:
        return items, ["items tab has no id/name header — Sheet edits ignored"]
    out = [dict(it) for it in items]
    by_id = {it["id"]: it for it in out}
    problems = []
    for n, r in enumerate(rows[1:], start=2):
        row = dict(zip(head, [str(c).strip() for c in r] + [""] * (len(head) - len(r))))
        if not any(row.values()):
            continue
        links = stores_mod.find_links(row.get("links", ""))
        it = by_id.get(row.get("id"))
        if it is None:
            if not row.get("name") or not links:
                problems.append("row %d: needs a name and a link" % n)
                continue
            try:
                it = state.new_item(out, row["name"], links, added_by=row.get("added_by") or "Sheet")
            except ValueError as e:
                problems.append("row %d: %s" % (n, e))
                continue
            out.append(it)
            by_id[it["id"]] = it
        if row.get("name"):
            it["name"] = row["name"].lstrip("'")
        if links:
            it["links"] = links
        for key, fn, field in (("qty", state.parse_qty, "qty"), ("weight_kg", state.parse_weight, "weight_kg"),
                               ("size_cm", state.parse_size, "size_cm")):
            v = row.get(key, "")
            if v == "":
                if key != "qty":
                    it[field] = None
                continue
            try:
                new = fn(v)
            except ValueError as e:
                problems.append("row %d %s: %s" % (n, key, e))
                continue
            if field == "weight_kg" and new != it.get("weight_kg"):
                it["size_from"] = "owner"
            it[field] = new
        st = row.get("status", "").lower()
        if st in state.STATUSES:
            it["status"] = st
        elif st:
            problems.append("row %d status: use active, bought or removed" % n)
        it["notes"] = row.get("notes", it.get("notes", "")).lstrip("'")
    return out, problems


def read_items_tab(cfg, sheet_id):
    ss = sheets_checklist._open(cfg, sheet_id)
    try:
        ws = ss.worksheet("items")
    except Exception:
        return []
    return _retry(ws.get_all_values)


def sync_items(cfg, root, sheet_id, write=True):
    """Read the Sheet, merge, save locally, rewrite the items tab. (items, problems)."""
    items = state.load_items(root)
    problems = []
    if sheet_id:
        try:
            items, problems = merge(items, read_items_tab(cfg, sheet_id))
        except Exception as e:
            return items, ["Sheet not read (%s) — local list used" % str(e)[:80]]
        state.save_items(root, items)
        if write:
            sheets_checklist.write_tab(cfg, sheet_id, "items", item_rows(items), bold_rows=(0,))
    return items, problems


def write_run(cfg, sheet_id, items, offers_rows, history):
    sheets_checklist.write_tab(cfg, sheet_id, "items", item_rows(items), bold_rows=(0,))
    sheets_checklist.write_tab(cfg, sheet_id, "offers", [OFFERS] + offers_rows, bold_rows=(0,))
    hist = [HISTORY] + [[h["date_local"], h["item_id"], cell(h["item"]), round(h["best_total_amd"]),
                         h["store"], h["route"], h["source"]] for h in history]
    sheets_checklist.write_tab(cfg, sheet_id, "history", hist, bold_rows=(0,), money_cols=(3,))
