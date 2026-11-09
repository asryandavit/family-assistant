"""Photos for /china photo search (docs/briefs/CHINA_SEARCH.md §10, decision 095).

    pick(msg)          the image in a Telegram message (largest photo size, or an image sent
                       as a file) -> {"file_id", "size", "ext"} or None
    caption_command()  "/china [only <site>] [note]" in the caption -> (sites, note) / None
    download()         Bot API getFile -> .browser/china_data/photos/<job>.<ext> (gitignored)
    remove() / sweep() delete one photo / every photo older than photo_keep_minutes

Photos are kept only as long as the job needs them (config_china.json photo_keep_minutes:
0 = delete when the answer is sent; a few minutes lets 🔁 Only 1688 repeat the photo search).
Logs never show a file id next to a chat id; chat and user ids are masked (mask()).
"""
import os
import re
import time

from china import data_dir

MAX_BYTES = 10 * 1024 * 1024          # the extension's file_upload limit per call (10 MB)
EXTS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/bmp": "bmp"}
API = "https://api.telegram.org"
CMD_RE = re.compile(r"^/china(?:@\w+)?(?:\s+(.*))?$", re.IGNORECASE | re.DOTALL)
ONLY_RE = re.compile(r"^only\s+(\S+)\s*(.*)$", re.IGNORECASE | re.DOTALL)
SITES = {"pinduoduo": "pinduoduo", "pdd": "pinduoduo", "taobao": "taobao", "tmall": "taobao",
         "1688": "1688"}


def mask(any_id):
    """For logs and file names: never the full chat or user id."""
    s = str(any_id or "")
    return "…" + s[-3:] if len(s) > 3 else "…"


def pick(msg):
    """The image in a message, or None (stickers, videos, other files are not photos)."""
    sizes = msg.get("photo") or []
    if sizes:
        ok = [p for p in sizes if (p.get("file_size") or 0) <= MAX_BYTES]
        best = max(ok or sizes, key=lambda p: (p.get("width", 0) * p.get("height", 0),
                                               p.get("file_size") or 0))
        return {"file_id": best["file_id"], "size": best.get("file_size") or 0, "ext": "jpg"}
    doc = msg.get("document") or {}
    ext = EXTS.get((doc.get("mime_type") or "").lower())
    if doc.get("file_id") and ext:
        return {"file_id": doc["file_id"], "size": doc.get("file_size") or 0, "ext": ext}
    return None


def caption_command(caption):
    """(sites or None, note) when the caption is a /china command, else None.
    Raises ValueError with a human sentence for '/china only <unknown site>'."""
    m = CMD_RE.match((caption or "").strip())
    if not m:
        return None
    rest = (m.group(1) or "").strip()
    sites = None
    o = ONLY_RE.match(rest)
    if o:
        site = SITES.get(o.group(1).lower())
        if not site:
            raise ValueError("Which site? Caption <code>/china only pinduoduo|taobao|1688</code>")
        sites, rest = [site], o.group(2).strip()
    return sites, rest[:200]


def photos_dir(root=None):
    d = os.path.join(data_dir(root), "photos")
    os.makedirs(d, exist_ok=True)
    return d


def path_for(root, job_id, ext="jpg"):
    if not re.fullmatch(r"[0-9a-f]{8}", job_id or "") or ext not in EXTS.values():
        raise ValueError("bad photo name")
    return os.path.join(photos_dir(root), f"{job_id}.{ext}")


def find(root, job_id):
    """The kept photo of a job, or None (deleted after the job or by the sweep)."""
    for ext in EXTS.values():
        p = os.path.join(photos_dir(root), f"{job_id}.{ext}")
        if os.path.exists(p):
            return p
    return None


def download(token, file_id, dest, get=None):
    """getFile + the file itself -> dest. ValueError with a human sentence on any failure;
    a partial file is never left behind."""
    if get is None:
        import requests
        get = requests.get
    try:
        r = get(f"{API}/bot{token}/getFile", params={"file_id": file_id}, timeout=20).json()
    except Exception as e:  # noqa: BLE001 — any failure; never echo it: the URL carries the token
        raise ValueError(f"Telegram did not give the photo ({type(e).__name__})") from None
    r = r if isinstance(r, dict) else {}
    info = r.get("result") or {}
    fpath, size = info.get("file_path"), info.get("file_size") or 0
    if not r.get("ok") or not fpath or not re.fullmatch(r"[\w./-]{1,200}", fpath) or ".." in fpath:
        raise ValueError("Telegram did not give the photo")
    if size > MAX_BYTES:
        raise ValueError("the photo is larger than 10 MB")
    try:
        resp = get(f"{API}/file/bot{token}/{fpath}", timeout=60)
        data = resp.content
        ok = getattr(resp, "status_code", 200) == 200
    except Exception as e:  # noqa: BLE001 — any failure; never echo it: the URL carries the token
        raise ValueError(f"the photo download failed ({type(e).__name__})") from None
    if not ok or not data:
        raise ValueError("the photo download failed")
    if len(data) > MAX_BYTES:
        raise ValueError("the photo is larger than 10 MB")
    tmp = dest + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, dest)
    return dest


def remove(path):
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def sweep(root=None, keep_minutes=0, now=None):
    """Delete photos older than keep_minutes (and stray .part files). Returns how many."""
    now = time.time() if now is None else now
    n = 0
    d = photos_dir(root)
    for name in os.listdir(d):
        p = os.path.join(d, name)
        try:
            if now - os.path.getmtime(p) >= keep_minutes * 60:
                os.remove(p)
                n += 1
        except OSError:
            pass
    return n
