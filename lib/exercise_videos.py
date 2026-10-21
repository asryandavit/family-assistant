"""Exercise video library — the parts that don't need the YouTube API.

    plan/training/exercises.md     the exercise library (ids, names, levels)
    plan/training/video-config.md  channel allowlist, synonyms, manual picks (hand-edited)
    plan/training/exercise-videos.md   generated: one row per exercise, video or NULL

Rules (owner, 2026-10-21): search "<name> form tutorial"; take the top result that is
1–8 minutes long, from an allowlisted channel, whose title contains the exercise name or
a synonym; store a URL only after fetching it successfully; otherwise store no video and
list the exercise for a manual pick. Re-verification re-fetches every stored URL and drops
the ones that fail. Search itself lives in jobs/exercise_videos.py (official API).
"""
import re
from datetime import date

MIN_SEC, MAX_SEC = 60, 480                       # 1–8 minutes
OEMBED = "https://www.youtube.com/oembed"
WATCH = "https://www.youtube.com/watch?v=%s"
SEARCH_SUFFIX = "form tutorial"

SECTION_PATTERN = {
    "Breathing and core foundations": "core / breathing",
    "Lower body": "lower body",
    "Upper body": "upper body",
    "Planks and anti-rotation": "core",
    "Conditioning (cardio, low impact first)": "cardio",
    "Mobility (desk antidote, daily)": "mobility",
}
_FLOOR = ("br-", "ex-deadbug", "ex-bridge", "ex-birddog", "ex-plank", "ex-prone",
          "ex-superman", "ex-side-plank", "ex-hip-thrust", "mb-cat-cow", "mb-child",
          "mb-open-book")


# ------------------------------------------------------------------ tables

def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_sep(cells):
    return all(set(c) <= set("-: ") for c in cells)


def _table_rows(md, heading):
    """Body rows of the first Markdown table under '## <heading>'."""
    rows, inside = [], False
    for line in (md or "").splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = line[3:].strip().lower() == heading.lower()
            continue
        if inside and line.strip().startswith("|"):
            rows.append(_cells(line))
    body = [r for r in rows if not _is_sep(r)]
    return body[1:] if body else []                     # drop the header row


def equipment_for(ex_id, name):
    s = (ex_id + " " + name).lower()
    for word, equip in (("wall", "wall"), ("counter", "kitchen counter"), ("sofa", "sofa"),
                        ("doorway", "doorway"), ("stairs", "stairs"), ("stair", "stairs"),
                        ("chair", "chair"), ("sit-stand", "chair")):
        if word in s:
            return equip
    return "mat" if ex_id.startswith(_FLOOR) else "none"


def parse_library(md):
    """exercises.md -> [{id, name, level, pattern, equipment}] in file order."""
    out, section = [], None
    for line in (md or "").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if not line.startswith("| `"):
            continue
        c = _cells(line)
        ex_id = c[0].strip("`")
        level = int(c[2]) if len(c) > 2 and c[2].isdigit() else None
        out.append({"id": ex_id, "name": c[1], "level": level,
                    "pattern": SECTION_PATTERN.get(section, (section or "").lower()),
                    "equipment": equipment_for(ex_id, c[1])})
    return out


def parse_config(md):
    """video-config.md -> {channels: [...], synonyms: {id: [..]}, manual: {id: url}}."""
    channels = []
    for c in _table_rows(md, "Channel allowlist"):
        if len(c) < 4 or not c[1] or c[1].startswith("*"):
            continue
        channels.append({"group": c[0], "name": c[1], "channel_id": c[2], "status": c[3].lower()})
    synonyms = {}
    for c in _table_rows(md, "Synonyms"):
        if len(c) >= 2 and c[0]:
            synonyms[c[0].strip("`")] = [s.strip() for s in c[1].split(",") if s.strip()]
    manual = {}
    for c in _table_rows(md, "Manual picks"):
        if len(c) >= 2 and c[0] and c[1]:
            manual[c[0].strip("`")] = c[1]
    return {"channels": channels, "synonyms": synonyms, "manual": manual}


def approved_channel_ids(cfg):
    return {c["channel_id"] for c in cfg["channels"] if c["channel_id"] and c["status"] == "approved"}


# ------------------------------------------------------------------ matching

def core_name(name):
    """'Sit-to-stand (chair)' -> 'Sit-to-stand'; 'Dead bug — heel taps' -> 'Dead bug';
    'Reverse lunge, holding the wall' -> 'Reverse lunge'."""
    s = re.split(r"\s+[—–-]\s+|\(|,", name or "")[0]
    return s.strip()


def search_query(name):
    return "%s %s" % (core_name(name), SEARCH_SUFFIX)


def _norm_words(s):
    s = (s or "").lower().replace("°", " ").replace("'", "")
    return re.findall(r"[a-z0-9]+", s)


def _word_in(w, words):
    return any(w == x or x in (w + "s", w + "es") or w in (x + "s", x + "es") for x in words)


def title_matches(title, name, synonyms=()):
    """The phrase (core name or a synonym) whose words all appear in the title, or None."""
    words = _norm_words(title)
    for phrase in [core_name(name)] + list(synonyms or []):
        need = _norm_words(phrase)
        if need and all(_word_in(w, words) for w in need):
            return phrase
    return None


def iso_seconds(iso):
    """'PT1M12S' -> 72; None if not an ISO-8601 duration."""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m or not any(m.groups()):
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def length_ok(seconds):
    return seconds is not None and MIN_SEC <= seconds <= MAX_SEC


def choose(candidates, allowed_ids, name, synonyms=()):
    """First candidate (in search order) that passes every rule, or None.
    candidates: [{video_id, title, channel_id, channel, duration_sec}]"""
    for c in candidates:
        if (c.get("channel_id") in allowed_ids and length_ok(c.get("duration_sec"))
                and title_matches(c.get("title"), name, synonyms)):
            return c
    return None


def video_id_from_url(url):
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else None


# ------------------------------------------------------------------ link check

def check_link(url, session):
    """Fetch YouTube's official oEmbed for the URL: 200 = public and available.
    Returns {ok, status, title, channel}; any other status or error -> ok False."""
    try:
        r = session.get(OEMBED, params={"url": url, "format": "json"}, timeout=20)
    except Exception as e:                                        # network error
        return {"ok": False, "status": "error: %s" % str(e)[:80], "title": None, "channel": None}
    if r.status_code != 200:
        return {"ok": False, "status": r.status_code, "title": None, "channel": None}
    j = r.json()
    return {"ok": True, "status": 200, "title": j.get("title"), "channel": j.get("author_name")}


# ------------------------------------------------------------------ generated file

COLUMNS = ["Exercise id", "Name", "Level", "Pattern", "Equipment",
           "Video title", "Channel", "Length", "URL", "Verified"]


def _clean(s):
    return str(s if s is not None else "").replace("|", "/").replace("\n", " ").strip()


def _length(sec):
    return "%d:%02d" % divmod(int(sec), 60) if sec else ""


def _seconds(text):
    m = re.fullmatch(r"(\d+):(\d{2})", text or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def render(rows, report, today=None):
    """rows: library rows merged with video fields (video_url None = no video)."""
    today = today or date.today().isoformat()
    out = ["# Exercise videos",
           "",
           "Generated by `jobs/exercise_videos.py` — do not edit; change "
           "[video-config.md](video-config.md) instead. A URL is listed only if it was "
           "fetched successfully on the date shown.",
           "",
           "| " + " | ".join(COLUMNS) + " |",
           "|" + "---|" * len(COLUMNS)]
    for r in rows:
        out.append("| " + " | ".join([
            "`%s`" % r["id"], _clean(r["name"]), _clean(r.get("level")), _clean(r.get("pattern")),
            _clean(r.get("equipment")), _clean(r.get("video_title")), _clean(r.get("channel")),
            _length(r.get("duration_sec")), _clean(r.get("video_url")), _clean(r.get("verified_at")),
        ]) + " |")
    out += ["", "## Needs manual pick", ""]
    out += ["- `%s` — %s" % (i, n) for i, n in report.get("manual", [])] or ["- none"]
    out += ["", "## Last run (%s)" % today, "",
            "seeded %d · verified %d · failed %d" % (report.get("seeded", 0),
                                                       report.get("verified", 0),
                                                       report.get("failed", 0))]
    if report.get("failed_ids"):
        out.append("")
        out += ["- dropped `%s` — %s" % (i, why) for i, why in report["failed_ids"]]
    return "\n".join(out) + "\n"


def parse_generated(md):
    """exercise-videos.md -> {id: {video_url, video_title, channel, duration_sec, verified_at}}."""
    out = {}
    for line in (md or "").splitlines():
        if not line.startswith("| `"):
            continue
        c = _cells(line)
        if len(c) < len(COLUMNS):
            continue
        out[c[0].strip("`")] = {"video_title": c[5] or None, "channel": c[6] or None,
                                "duration_sec": _seconds(c[7]), "video_url": c[8] or None,
                                "verified_at": c[9] or None}
    return out
