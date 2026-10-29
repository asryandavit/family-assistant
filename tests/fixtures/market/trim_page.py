"""Trim a captured store page to the parts the parsers read (fixtures stay small).

    python tests/fixtures/market/trim_page.py amazon|vega IN.html OUT.html

Keeps <title> and each kept element's whole outer HTML (balanced tags), in page order;
scripts, styles, SVG and comments inside them are dropped. Nothing is rewritten: every
kept byte is from the real capture.
"""
import re
import sys

KEEP = {
    "amazon": ["glow-ingress-block", "productTitle", "corePriceDisplay_desktop_feature_div",
               "corePrice_feature_div", "availability", "outOfStock", "mir-layout-DELIVERY_BLOCK",
               "productOverview_feature_div", "prodDetails", "detailBullets_feature_div",
               "productDetails_feature_div"],
}


def element(html, id_):
    """Outer HTML of the element with this id (first one), or ''."""
    m = re.search(r'<(\w+)\b[^>]*\bid="%s"[^>]*>' % re.escape(id_), html)
    if not m:
        return ""
    tag = m.group(1).lower()
    depth, pos = 0, m.start()
    pat = re.compile(r"<(/?)%s\b[^>]*?(/?)>" % tag, re.I)
    for t in pat.finditer(html, m.start()):
        if t.group(2):            # self-closing
            continue
        depth += -1 if t.group(1) else 1
        if depth == 0:
            return html[pos:t.end()]
    return html[pos:pos + 20000]


def clean(h):
    for pat in (r"<script\b.*?</script>", r"<style\b.*?</style>", r"<svg\b.*?</svg>",
                r"<!--.*?-->", r"<noscript\b.*?</noscript>"):
        h = re.sub(pat, "", h, flags=re.S | re.I)
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t]+", " ", h))


def trim(kind, html):
    title = re.search(r"<title\b.*?</title>", html, re.S | re.I)
    parts = [title.group(0) if title else ""]
    if kind == "vega":                       # vega.am: the JSON-LD blocks carry price + stock
        parts += re.findall(r'<script type="application/ld\+json">.*?</script>', html, re.S)
        return "<html><head>%s</head><body>\n%s\n</body></html>\n" % (parts[0], "\n".join(parts[1:]))
    for id_ in KEEP[kind]:
        el = element(html, id_)
        if el:
            parts.append("<!-- kept #%s -->\n%s" % (id_, clean(el)))
    return "<html><head>%s</head><body>\n%s\n</body></html>\n" % (parts[0], "\n".join(parts[1:]))


if __name__ == "__main__":
    kind, src, dst = sys.argv[1:4]
    with open(src, encoding="utf-8") as f:
        out = trim(kind, f.read())
    with open(dst, "w", encoding="utf-8") as f:
        f.write(out)
    print("%s -> %s (%d bytes)" % (src, dst, len(out)))
