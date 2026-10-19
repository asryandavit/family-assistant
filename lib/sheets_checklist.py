"""Rewrite one tab of a checklist spreadsheet (the family's Shopping list Sheet).

Additive next to lib/sheets.py (which stays the append-only travel log): same
service account and the same retry on transient errors, but a different
spreadsheet per call and whole-tab rewrites instead of appends.

A rewrite clears the tab's values, formatting and checkboxes, writes the new rows
(USER_ENTERED, so =HYPERLINK(...) formulas become links and False becomes an
unticked box), then puts real checkboxes (data validation BOOLEAN) on the given
rows -- verified against the live Sheet on 2026-10-19. The file, its tabs and
its sharing are never touched otherwise.
"""
import os

import gspread
from google.oauth2.service_account import Credentials

from lib.sheets import SCOPES, _retry

_cache = {}


def sheet_url(sheet_id):
    return "https://docs.google.com/spreadsheets/d/%s/edit" % sheet_id


def link(url, text):
    """=HYPERLINK formula; quotes in the text are doubled as Sheets requires."""
    return '=HYPERLINK("%s","%s")' % (str(url).replace('"', "%22"), str(text).replace('"', '""'))


def _open(cfg, sheet_id):
    if sheet_id not in _cache:
        path = os.path.join(cfg["_root"], cfg["service_account_file"])
        creds = Credentials.from_service_account_file(path, scopes=SCOPES)
        _cache[sheet_id] = _retry(gspread.authorize(creds).open_by_key, sheet_id)
    return _cache[sheet_id]


def _tab(ss, title, rows, cols):
    try:
        ws = ss.worksheet(title)
    except gspread.WorksheetNotFound:
        return _retry(ss.add_worksheet, title=title, rows=max(rows, 50), cols=max(cols, 8))
    if ws.row_count < rows or ws.col_count < cols:
        _retry(ws.resize, rows=max(rows, ws.row_count), cols=max(cols, ws.col_count))
    return ws


def _grid(ws, r0=0, r1=None, c0=0, c1=None):
    g = {"sheetId": ws.id, "startRowIndex": r0, "startColumnIndex": c0}
    if r1 is not None:
        g["endRowIndex"] = r1
    if c1 is not None:
        g["endColumnIndex"] = c1
    return g


def requests_for(ws, n_rows, n_cols, checkbox_rows=(), bold_rows=(), money_cols=()):
    """The batchUpdate requests for one rewrite (pure; tested offline)."""
    whole = _grid(ws)
    reqs = [
        {"repeatCell": {"range": whole, "cell": {"userEnteredFormat": {}},
                        "fields": "userEnteredFormat"}},
        {"setDataValidation": {"range": whole}},          # no rule = remove checkboxes
    ]
    for r in checkbox_rows:
        reqs.append({"setDataValidation": {"range": _grid(ws, r, r + 1, 0, 1),
                                           "rule": {"condition": {"type": "BOOLEAN"},
                                                    "strict": True}}})
    for r in bold_rows:
        reqs.append({"repeatCell": {"range": _grid(ws, r, r + 1, 0, n_cols),
                                    "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                                    "fields": "userEnteredFormat.textFormat.bold"}})
    for c in money_cols:
        reqs.append({"repeatCell": {"range": _grid(ws, 0, n_rows, c, c + 1),
                                    "cell": {"userEnteredFormat": {"numberFormat": {
                                        "type": "NUMBER", "pattern": "#,##0"}}},
                                    "fields": "userEnteredFormat.numberFormat"}})
    reqs.append({"autoResizeDimensions": {"dimensions": {
        "sheetId": ws.id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": n_cols}}})
    return reqs


def write_tab(cfg, sheet_id, title, rows, checkbox_rows=(), bold_rows=(), money_cols=()):
    """Replace everything on tab `title` with `rows` (list of lists). Raises on
    failure -- the caller decides who hears about it."""
    n_cols = max(len(r) for r in rows) if rows else 1
    rows = [list(r) + [""] * (n_cols - len(r)) for r in rows]
    ss = _open(cfg, sheet_id)
    ws = _tab(ss, title, len(rows) + 10, n_cols)
    _retry(ws.clear)
    _retry(ws.update, values=rows, range_name="A1", value_input_option="USER_ENTERED")
    _retry(ss.batch_update, {"requests": requests_for(ws, len(rows), n_cols, checkbox_rows,
                                                      bold_rows, money_cols)})
    return ws
