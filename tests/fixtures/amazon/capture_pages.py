"""Capture Amazon UK/DE/IT/US search pages and the first result's product page for one
electronics and one baby query, with the bot's own browser (scrapers/market.py Session:
logged out, delivery postcodes from market/stores.md, read-only, 3-6 s between pages).
Used for the P0 discovery (docs/briefs/AMAZON_SEARCH.md §2); cut down with trim_capture.py.

    python scrapers/market.py --setup                  # once: postcodes + currency
    python tests/fixtures/amazon/capture_pages.py <out_dir>
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
from scrapers.market import Session  # noqa: E402

HOST = {"us": "www.amazon.com", "uk": "www.amazon.co.uk", "de": "www.amazon.de", "it": "www.amazon.it"}
QUERIES = {
    "elec": {"us": "usb c charger 65w", "uk": "usb c charger 65w", "de": "usb c ladegerät 65w",
             "it": "caricatore usb c 65w"},
    "baby": {"us": "baby romper 6-12 months", "uk": "baby romper 6-12 months",
             "de": "baby strampler 68", "it": "tutina neonato 6-9 mesi"},
}


def main(out):
    os.makedirs(out, exist_ok=True)
    summary = {}
    with Session() as s:
        for q, per in QUERIES.items():
            for c, term in per.items():
                r = s.read("https://%s/s?k=%s" % (HOST[c], term.replace(" ", "+")), wait_selector="[data-asin]")
                pages = [("%s_%s_search" % (c, q), r)]
                asins = re.findall(r'data-asin="([A-Z0-9]{10})"', r["html"])
                if asins:
                    pages.append(("%s_%s_dp" % (c, q), s.read("https://%s/dp/%s" % (HOST[c], asins[0]))))
                for name, p in pages:
                    with open(os.path.join(out, name + ".html"), "w", encoding="utf-8") as f:
                        f.write(p["html"])
                    summary[name] = {"status": p["status"], "final_url": p["final_url"], "detail": p["detail"]}
                    print(name, summary[name], flush=True)
    with open(os.path.join(out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
