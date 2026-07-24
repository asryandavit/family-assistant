"""Turn raw SmartSearchCheapFlightsV2 JSON into clean fare rows.

Deterministic on purpose: prices and dates are parsed in Python, never by the
model, so what lands in the sheet is exactly what Wizz returned.

Wizz prices each departure market in its LOCAL currency (EVN->x in USD, but
BUD->EVN in HUF, PRG->EVN in CZK...). Every price is normalized to USD here so
movement thresholds and trip totals are comparable; the original quote is kept
in the `src` field. Rows whose currency can't be converted keep the original
code and are excluded from trip pairing by the assembler.

Empty values are written as "-" rather than blanks, so no column is ever fully
empty -- an empty interior column makes Google's append auto-detection treat the
data as two separate tables and write new rows in the wrong place.
"""
from datetime import date

from lib import fx

BLANK = "-"


def _amount(node, *keys):
    for k in keys:
        v = (node or {}).get(k)
        if isinstance(v, dict) and isinstance(v.get("amount"), (int, float)):
            return float(v["amount"]), v.get("currencyCode") or ""
    return None, ""


def _leg(flight):
    if not isinstance(flight, dict):
        return None
    reg, cur = _amount(flight, "regularPrice", "regularOriginalPrice")
    wdc, _ = _amount(flight, "wdcPrice", "wdcOriginalPrice")
    std = flight.get("std") or ""
    return {
        "from": flight.get("departureStation") or "",
        "to": flight.get("arrivalStation") or "",
        "date": std[:10],
        "time": std[11:16],
        "regular": reg,
        "wdc": wdc,
        "currency": cur or "USD",
    }


def _normalize(reg, wdc, cur):
    """Returns (regular, wdc, currency, src) with USD normalization."""
    cur = (cur or "USD").upper()
    if cur == "USD":
        return reg, wdc, "USD", BLANK
    reg_usd = fx.to_usd(reg, cur)
    if reg_usd is None:  # unknown currency: keep original, mark it
        return reg, wdc, cur, BLANK
    wdc_usd = fx.to_usd(wdc, cur) if wdc is not None else None
    return reg_usd, wdc_usd, "USD", f"{reg:g} {cur}"


def parse(captured):
    """captured: list of {'url':..., 'data':...}. Returns deduped fare rows."""
    best = {}
    for resp in captured or []:
        data = resp.get("data") or {}
        for item in data.get("items", []) or []:
            ob = _leg(item.get("outboundFlight"))
            rb = _leg(item.get("returnFlight"))
            if not ob or not ob["to"] or ob["regular"] is None:
                continue

            is_return = bool(item.get("isReturnFlight")) and rb and rb["regular"] is not None
            reg = ob["regular"] + (rb["regular"] if is_return else 0)
            wdc = None
            if ob["wdc"] is not None:
                wdc = ob["wdc"] + ((rb["wdc"] or 0) if is_return else 0)

            reg, wdc, cur, src = _normalize(reg, wdc, ob["currency"])

            # origin must be in the key: inbound fares all share destination EVN
            key = (ob["from"], ob["to"], ob["date"], bool(is_return))
            row = {
                "origin": ob["from"],
                "destination": ob["to"],
                "out_date": ob["date"],
                "out_time": ob["time"] or BLANK,
                "back_date": rb["date"] if is_return else BLANK,
                "type": "return" if is_return else "oneway",
                "regular": reg,
                "wdc": wdc if wdc is not None else BLANK,
                "currency": cur,
                "src": src,
            }
            if key not in best or row["regular"] < best[key]["regular"]:
                best[key] = row

    return sorted(best.values(), key=lambda r: r["regular"])


def to_sheet_rows(rows, run_date=None):
    run = run_date or date.today().isoformat()
    return [[
        run, r["origin"], r["destination"], r["out_date"], r["out_time"],
        r["back_date"], r["type"], r["regular"], r["wdc"], r["currency"],
        r["src"],
    ] for r in rows]
