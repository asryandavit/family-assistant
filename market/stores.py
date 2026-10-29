"""market/stores.md -> store rows; a pasted link -> its store."""
import os
import re
from urllib.parse import urlparse

from market import DIR

ALIASES = {"www.ozon.ru": "am.ozon.com", "ozon.ru": "am.ozon.com", "wildberries.ru": "www.wildberries.ru",
           "amazon.com": "www.amazon.com", "amazon.co.uk": "www.amazon.co.uk",
           "amazon.de": "www.amazon.de", "amazon.it": "www.amazon.it", "www.vega.am": "vega.am",
           "global.wildberries.ru": "www.wildberries.ru", "wildberries.am": "www.wildberries.ru"}


def load(path=None):
    """{key: {"key", "name", "host", "reader", "origin", "currency", "modes": [...], "postcode"}}"""
    with open(path or os.path.join(DIR, "stores.md"), encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip().startswith("|")]
    if len(lines) < 3:
        raise ValueError("stores.md: no table")
    head = [h.strip().lower() for h in lines[0].strip("|").split("|")]
    out = {}
    for ln in lines[2:]:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        row = dict(zip(head, cells))
        row["modes"] = [m.strip() for m in row.get("modes", "").split(",") if m.strip()]
        row["postcode"] = "" if row.get("postcode") in ("—", "-") else row.get("postcode", "")
        out[row["key"]] = row
    return out


def host_of(url):
    host = (urlparse(url.strip()).hostname or "").lower()
    return ALIASES.get(host, host)


def store_for_url(url, stores=None):
    stores = stores or load()
    host = host_of(url)
    return next((s for s in stores.values() if s["host"] == host), None)


def canonical(url, store):
    """Exact product link in the form the reader opens (Amazon: /dp/<ASIN>; Ozon on am.ozon.com)."""
    u = url.strip()
    if store["reader"] == "amazon":
        m = re.search(r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})", u)
        if m:
            return "https://%s/dp/%s" % (store["host"], m.group(1))
    p = urlparse(u)
    return "https://%s%s" % (store["host"], p.path or "/")


URL_RE = re.compile(r"https?://\S+")


def find_links(text):
    return [u.rstrip(").,;") for u in URL_RE.findall(text or "")]
