"""CBA exchange rates (api.cba.am SOAP), once per run, cached for the Yerevan day.

A failed fetch falls back to the newest cached day and says so ("rates from 28 Oct");
with no cache at all the report shows store currencies only — never an invented rate.
"""
import json
import os

from market import tariffs

URL = "https://api.cba.am/exchangerates.asmx"
HEADERS = {"Content-Type": "text/xml; charset=utf-8",
           "SOAPAction": "http://www.cba.am/ExchangeRatesLatest"}


def cache_dir(root):
    d = os.path.join(root, ".browser", "market_data", "cba")
    os.makedirs(d, exist_ok=True)
    return d


def fetch_xml():
    import requests
    r = requests.post(URL, data=tariffs.CBA_REQUEST.encode("utf-8"), headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def get(root, today_local, fetch=fetch_xml):
    """{"date", "amd_per", "stale": bool, "note"} or None when nothing is known."""
    d = cache_dir(root)
    path = os.path.join(d, "%s.json" % today_local.isoformat())
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return dict(json.load(f), stale=False, note="")
    try:
        r = tariffs.parse_cba(fetch())
        with open(path, "w", encoding="utf-8") as f:
            json.dump(r, f)
        return dict(r, stale=False, note="")
    except Exception as e:
        cached = sorted(x for x in os.listdir(d) if x.endswith(".json"))
        if not cached:
            return None
        with open(os.path.join(d, cached[-1]), encoding="utf-8") as f:
            r = json.load(f)
        return dict(r, stale=True, note="CBA not reachable (%s)" % str(e)[:60])


def to_amd(amount, currency, rates):
    """AMD for an amount in a currency; None when the amount or the rate is unknown."""
    if amount is None:
        return None
    if currency == "AMD":
        return float(amount)
    if not rates or currency not in rates["amd_per"]:
        return None
    return float(amount) * rates["amd_per"][currency]
