"""Find where listing data lives inside the saved discovery HTML.

Works entirely offline on .browser/stays_*.html -- no re-scraping.

Extracts every embedded JSON blob, then recursively hunts for the objects that
carry property/listing fields, and reports the exact key path so the parser can
be written against real structure instead of guesses.
"""
import json
import os
import re
import sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".browser")

# Field names that mark a real listing record on each site
BOOKING_MARKERS = {"basicPropertyData", "displayName", "reviewScore",
                   "priceDisplayInfoIrene", "blocks", "matchingUnitConfigurations"}
AIRBNB_MARKERS = {"listing", "pricingQuote", "demandStayListing", "structuredContent",
                  "avgRatingLocalized", "listingParamOverrides"}


def blobs_from_html(html):
    """Every <script type=application/json> body, plus window.X = {...} assigns."""
    out = []
    for m in re.finditer(
            r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', html, re.S):
        out.append(("script-json", m.group(1)))
    for m in re.finditer(
            r'<script[^>]*id="([^"]+)"[^>]*>(\{.*?\})</script>', html, re.S):
        out.append(("script-" + m.group(1), m.group(2)))
    for m in re.finditer(
            r'window\.(__[A-Z_]+__|booking\.[A-Za-z_]+)\s*=\s*(\{.*?\});', html, re.S):
        out.append(("window-" + m.group(1), m.group(2)))
    return out


def walk(node, markers, path="", depth=0, hits=None, max_depth=14):
    """Recursively find dicts containing any marker key."""
    if hits is None:
        hits = []
    if depth > max_depth or len(hits) >= 6:
        return hits
    if isinstance(node, dict):
        found = markers & set(node.keys())
        if found:
            hits.append((path or "<root>", sorted(found), node))
            return hits
        for k, v in node.items():
            walk(v, markers, "%s.%s" % (path, k) if path else k, depth + 1, hits)
    elif isinstance(node, list):
        for i, v in enumerate(node[:4]):
            walk(v, markers, "%s[%d]" % (path, i), depth + 1, hits)
    return hits


def unwrap_strings(node, depth=0):
    """Airbnb nests JSON inside strings; parse those so we can search them."""
    if depth > 6:
        return node
    if isinstance(node, str):
        s = node.strip()
        if s.startswith(("{", "[")) and len(s) > 40:
            try:
                return unwrap_strings(json.loads(s), depth + 1)
            except ValueError:
                return node
        return node
    if isinstance(node, dict):
        return {k: unwrap_strings(v, depth + 1) for k, v in node.items()}
    if isinstance(node, list):
        return [unwrap_strings(v, depth + 1) for v in node]
    return node


def summarize(obj, indent=2, limit=22):
    lines = []
    for k, v in list(obj.items())[:limit]:
        if isinstance(v, dict):
            t = "dict{%s}" % ",".join(list(v.keys())[:6])
        elif isinstance(v, list):
            t = "list[%d]" % len(v)
            if v and isinstance(v[0], dict):
                t += "{%s}" % ",".join(list(v[0].keys())[:6])
        elif isinstance(v, str):
            t = repr(v[:70])
        else:
            t = repr(v)
        lines.append(" " * indent + "%s: %s" % (k, t))
    return "\n".join(lines)


def run(site):
    path = os.path.join(OUT, "stays_%s.html" % site)
    if not os.path.exists(path):
        print("missing %s -- run debug_stays2.py %s first" % (path, site))
        return
    html = open(path, encoding="utf-8", errors="ignore").read()
    print("\n" + "=" * 62)
    print("%s  (%d KB of HTML)" % (site.upper(), len(html) // 1024))
    print("=" * 62)

    markers = BOOKING_MARKERS if site == "booking" else AIRBNB_MARKERS
    found_any = False

    for name, raw in sorted(blobs_from_html(html), key=lambda x: -len(x[1])):
        if len(raw) < 2000:
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        if site == "airbnb":
            data = unwrap_strings(data)
        hits = walk(data, markers)
        if not hits:
            continue
        found_any = True
        print("\n--- blob %s (%d KB) ---" % (name, len(raw) // 1024))
        for p, keys, obj in hits[:3]:
            print("\n  PATH: %s" % p)
            print("  MARKERS: %s" % ", ".join(keys))
            print("  FIELDS:")
            print(summarize(obj))
        break

    if not found_any:
        print("\nNo marker match. Top-level keys of the largest blobs:")
        for name, raw in sorted(blobs_from_html(html), key=lambda x: -len(x[1]))[:4]:
            try:
                data = json.loads(raw)
            except ValueError:
                continue
            keys = list(data.keys())[:12] if isinstance(data, dict) else type(data).__name__
            print("  %-24s %6dKB  %s" % (name, len(raw) // 1024, keys))

    # DOM fallback check: are the testid attributes present?
    if site == "booking":
        for sel in ["property-card", "title", "review-score",
                    "price-and-discounted-price", "availability-rate-information"]:
            print("  data-testid=%-32s occurrences: %d"
                  % (sel, html.count('data-testid="%s"' % sel)))


if __name__ == "__main__":
    sites = sys.argv[1:] or ["booking", "airbnb"]
    for s in sites:
        run(s)
