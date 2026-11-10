"""How the files in this folder were cut from full captures (CLAUDE.md §8: real pages, no
cookies, no tokens, no account data). A full Amazon page is 1-3 MB; the fields we read are
a few KB. Cut by id/card, scripts, styles and svg removed, CSRF-looking tokens blanked.

    python tests/fixtures/amazon/trim_capture.py <capture_dir> <out_dir>
Captures come from scrapers/market.py's Session (bot profile, delivery postcodes set)."""
import glob
import os
import re
import sys

KEEP_IDS = ["glow-ingress-block", "corePrice_feature_div", "averageCustomerReviews_feature_div",
            "acBadge_feature_div", "desktop_buybox"]


def clean(h):
    h = re.sub(r"<(script|style|svg|noscript)\b.*?</\1>", "", h, flags=re.S | re.I)
    h = re.sub(r"<!--.*?-->", "", h, flags=re.S)
    h = re.sub(r"<input\b[^>]*type=.hidden.[^>]*>", "", h, flags=re.I)   # session id, CSRF, customer ids
    h = re.sub(r"</?form\b[^>]*>", "", h, flags=re.I)
    h = re.sub(r"<meta\b[^>]*csrf[^>]*>", "", h, flags=re.I)
    h = re.sub(r"(sessionId|csrfToken|session-id|ubid)(&quot;|\")?\s*[:=]\s*(&quot;|\")[^&\"]*(&quot;|\")",
               r"\1=REDACTED", h, flags=re.I)
    h = re.sub(r"\b\d{3}-\d{7}-\d{7}\b", "000-0000000-0000000", h)       # Amazon session id shape
    return re.sub(r"\s+", " ", h)


def div_by_id(h, id_):
    m = re.search(r'<div[^>]*\bid="%s"[^>]*>' % re.escape(id_), h)
    if not m:
        return ""
    depth, pos = 0, m.start()
    for t in re.finditer(r"<(/?)div\b", h[pos:]):
        depth += -1 if t.group(1) else 1
        if depth == 0:
            end = h.find(">", pos + t.start()) + 1
            return h[pos:end]
    return h[pos:pos + 20000]


def trim_search(h, n=8):
    cards = re.split(r'(?=<div[^>]+data-component-type="s-search-result")', clean(h))[1:]
    organic = [c for c in cards if "puis-sponsored-label" not in c and "AdHolder" not in c[:400]]
    spons = [c for c in cards if c not in organic]
    pick = organic[:n - 2] + spons[:2]
    head = div_by_id(clean(h), "glow-ingress-block")
    # a card runs to the next card; cut each at its own closing by using the first 12 KB at most
    return "<!-- %d cards on the page, %d kept -->\n%s\n%s" % (
        len(cards), len(pick), head, "\n".join(c[:12000] for c in pick))


def trim_dp(h):
    h = clean(h)
    title = re.search(r'<span id="productTitle"[^>]*>.*?</span>', h)
    out = [title.group(0) if title else ""]
    for i in KEEP_IDS:
        out.append(div_by_id(h, i))
    return "\n".join(out)


if __name__ == "__main__":
    src, dst = sys.argv[1:3]
    os.makedirs(dst, exist_ok=True)
    for f in sorted(glob.glob(os.path.join(src, "*.html"))):
        name = os.path.basename(f)
        h = open(f, encoding="utf-8").read()
        out = trim_search(h) if name.endswith("_search.html") else trim_dp(h)
        with open(os.path.join(dst, name), "w", encoding="utf-8") as fh:
            fh.write(out)
        print(name, len(h), "->", len(out))
