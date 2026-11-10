"""jobs/housekeeping.py (decision 103): only Chrome caches go, logins never, busy profiles are
skipped, logs are capped, the owner hears about a low disk."""
import json
import os
import time

import pytest

from jobs import housekeeping as hk
from scrapers import browser_lock

CACHES = ["Default/Cache", "Default/Code Cache", "Default/GPUCache",
          "Default/Service Worker/CacheStorage", "GrShaderCache", "ShaderCache"]
KEEP = ["Default/Cookies", "Default/Login Data", "Default/Preferences", "Local State",
        "Default/Local Storage/leveldb/000003.log", "Default/IndexedDB/x.leveldb/LOG",
        "Default/Network/Cookies", "Default/Service Worker/Database/MANIFEST",
        "Default/Service Worker/ScriptCache/index", "Default/Secure Preferences"]


def _file(root, rel, n=1000):
    p = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(b"x" * n)
    return p


def make_profile(root, name="market"):
    prof = os.path.join(str(root), ".browser", name)
    for rel in CACHES:
        _file(prof, rel + "/data_0", 5000)
        _file(prof, rel + "/sub/f_00001", 3000)
    for rel in KEEP:
        _file(prof, rel, 100)
    return prof


def cfg(**kw):
    c = dict(hk.DEFAULTS, profiles=["market"], cache_dirs=CACHES,
             logs=[".browser/listener.log"], log_max_bytes=1000, log_keep=2, min_free_gb=5)
    c.update(kw)
    return c


def _no_lock_files(root):
    return not os.path.exists(browser_lock.path(str(root)))


# ---------------------------------------------------------------- happy path
def test_caches_go_and_logins_stay(tmp_path):
    prof = make_profile(tmp_path)
    st = hk.run(str(tmp_path), cfg(), procs=[], disk_paths=[str(tmp_path)])
    p = st["profiles"][0]
    assert p["status"] == "cleaned" and p["freed"] == len(CACHES) * 8000 and not p["errors"]
    for rel in CACHES:
        assert not os.path.exists(os.path.join(prof, *rel.split("/")))
    for rel in KEEP:
        assert os.path.exists(os.path.join(prof, *rel.split("/"))), rel
    assert _no_lock_files(tmp_path)                  # the market lock was released


def test_dry_run_deletes_nothing(tmp_path):
    prof = make_profile(tmp_path)
    st = hk.run(str(tmp_path), cfg(), dry_run=True, procs=[], disk_paths=[str(tmp_path)])
    assert st["profiles"][0]["would_free"] == len(CACHES) * 8000
    assert st["profiles"][0]["freed"] == 0
    assert os.path.exists(os.path.join(prof, "Default", "Cache", "data_0"))
    assert not os.path.exists(os.path.join(str(tmp_path), ".browser", "housekeeping.json"))


def test_report_is_one_line_in_its_own_log(tmp_path):
    make_profile(tmp_path)
    hk.run(str(tmp_path), cfg(), procs=[], disk_paths=[str(tmp_path)])
    with open(os.path.join(str(tmp_path), ".browser", "housekeeping.log"), encoding="utf-8") as f:
        lines = f.read().splitlines()
    assert len(lines) == 1
    assert "freed 0.0 MB (market 0.0 MB)" in lines[0] and "disks:" in lines[0]
    st = hk.load_state(str(tmp_path))
    assert st["freed_bytes"] == len(CACHES) * 8000 and st["last_run_utc"].endswith("+00:00")


def test_missing_profile_is_quiet(tmp_path):
    st = hk.run(str(tmp_path), cfg(profiles=["wizz"]), procs=[], disk_paths=[str(tmp_path)])
    assert st["profiles"][0]["status"] == "missing"
    assert "skipped" not in st["line"]


# ---------------------------------------------------------------- in use -> skipped
def test_profile_held_by_the_market_lock_is_skipped(tmp_path):
    prof = make_profile(tmp_path)
    with open(browser_lock.path(str(tmp_path)), "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "since": time.time(), "who": "amazon"}, f)
    st = hk.run(str(tmp_path), cfg(), procs=[], disk_paths=[str(tmp_path)])
    p = st["profiles"][0]
    assert p["status"].startswith("in use") and "amazon" in p["status"]
    assert p["freed"] == 0
    assert os.path.exists(os.path.join(prof, "Default", "Cache", "data_0"))
    assert "skipped: market in use" in st["line"]
    with open(browser_lock.path(str(tmp_path)), encoding="utf-8") as f:
        assert json.load(f)["who"] == "amazon"       # someone else's lock is left alone


def test_profile_with_a_running_browser_is_skipped(tmp_path):
    prof = make_profile(tmp_path, "wizz")
    procs = [(4242, ["chrome.exe", "--type=renderer"]),
             (4243, ["chrome.exe", "--user-data-dir=" + prof, "--remote-debugging-pipe"])]
    st = hk.run(str(tmp_path), cfg(profiles=["wizz"]), procs=procs, disk_paths=[str(tmp_path)])
    assert st["profiles"][0]["status"] == "in use (browser pid 4243)"
    assert os.path.exists(os.path.join(prof, "Default", "Cache", "data_0"))


def test_a_browser_on_a_similar_profile_name_does_not_block(tmp_path):
    make_profile(tmp_path, "market")
    other = os.path.join(str(tmp_path), ".browser", "market_chrome")
    procs = [(1, ["chrome.exe", "--user-data-dir=" + other])]
    st = hk.run(str(tmp_path), cfg(), procs=procs, disk_paths=[str(tmp_path)])
    assert st["profiles"][0]["status"] == "cleaned"


def test_chrome_lockfile_held_open_means_in_use(tmp_path, monkeypatch):
    prof = make_profile(tmp_path, "taobao")
    _file(prof, "lockfile", 0)
    real_open = os.open

    def deny(p, *a, **k):
        if os.path.basename(p) == "lockfile":
            raise PermissionError(13, "in use")
        return real_open(p, *a, **k)
    monkeypatch.setattr(hk.os, "open", deny)
    st = hk.run(str(tmp_path), cfg(profiles=["taobao"]), procs=[], disk_paths=[str(tmp_path)])
    assert st["profiles"][0]["status"].startswith("in use")
    assert os.path.exists(os.path.join(prof, "Default", "Cache", "data_0"))


def test_stale_lockfile_left_by_a_crash_does_not_block(tmp_path):
    prof = make_profile(tmp_path, "taobao")
    _file(prof, "lockfile", 0)                       # openable = nobody holds it
    st = hk.run(str(tmp_path), cfg(profiles=["taobao"]), procs=[], disk_paths=[str(tmp_path)])
    assert st["profiles"][0]["status"] == "cleaned"


def test_unknown_process_list_means_hands_off(tmp_path):
    make_profile(tmp_path, "wizz")
    st = hk.run(str(tmp_path), cfg(profiles=["wizz"]), procs=None, disk_paths=[str(tmp_path)])
    assert "psutil missing" in st["profiles"][0]["status"]
    assert st["profiles"][0]["freed"] == 0


def test_browser_starting_mid_clean_stops_the_profile(tmp_path, monkeypatch):
    make_profile(tmp_path, "wizz")
    calls = {"n": 0}

    def held(_p):
        calls["n"] += 1
        return calls["n"] > 2                        # free at the check, busy after one folder
    monkeypatch.setattr(hk, "lock_held", held)
    st = hk.run(str(tmp_path), cfg(profiles=["wizz"]), procs=[], disk_paths=[str(tmp_path)])
    p = st["profiles"][0]
    assert p["status"].startswith("in use (a browser started")
    assert p["freed"] == 8000                         # only the first folder went


# ---------------------------------------------------------------- refusals
@pytest.mark.parametrize("rel", ["Default/Cookies", "Default/Login Data", "Default/Network",
                                 "Default/Local Storage", "Default/IndexedDB",
                                 "Default/Preferences", "default/login data", "Local State",
                                 "Default/Network/Cache", "../wizz/Default/Cache",
                                 "Default/../../x", "/etc", "C:/Windows", ""])
def test_login_and_escape_paths_are_refused(tmp_path, rel):
    prof = make_profile(tmp_path)
    st = hk.run(str(tmp_path), cfg(cache_dirs=["Default/Cache", rel]), procs=[],
                disk_paths=[str(tmp_path)])
    assert st["profiles"][0]["status"].startswith("refused")
    for keep in KEEP + ["Default/Cache/data_0"]:     # refused = nothing at all deleted
        assert os.path.exists(os.path.join(prof, *keep.split("/"))), keep


@pytest.mark.parametrize("name", ["..", "../..", "a/b", ("C:\\Users\\x\\AppData\\Local\\Google"
                                  "\\Chrome\\User Data"), "/home/x/.config/google-chrome", ""])
def test_profiles_outside_dot_browser_are_refused(tmp_path, name):
    st = hk.run(str(tmp_path), cfg(profiles=[name]), procs=[], disk_paths=[str(tmp_path)])
    assert st["profiles"][0]["status"].startswith("refused")


def test_real_config_is_valid_and_names_no_login_store():
    c = hk.load_cfg()
    assert set(c["profiles"]) >= {"market", "wizz", "stays_booking", "stays_airbnb", "taobao"}
    for name in c["profiles"]:
        prof = hk.profile_path(hk.ROOT, name)
        for rel in c["cache_dirs"]:
            hk.cache_path(prof, rel)                 # raises on anything protected


# ---------------------------------------------------------------- logs, inbox, disks
def test_logs_over_the_cap_rotate(tmp_path):
    _file(str(tmp_path), ".browser/listener.log", 5000)
    _file(str(tmp_path), ".browser/amazon_data/worker.log", 10)
    st = hk.run(str(tmp_path), cfg(profiles=[], logs=[".browser/listener.log",
                                                       ".browser/amazon_data/worker.log",
                                                       "config.json"]),
                procs=[], disk_paths=[str(tmp_path)])
    assert st["rotated"] == [".browser/listener.log"]
    assert os.path.getsize(os.path.join(str(tmp_path), ".browser", "listener.log.1")) == 5000
    assert "logs rotated: listener.log" in st["line"]


def test_old_inbox_tmp_files_go_new_ones_and_requests_stay(tmp_path):
    d = os.path.join(str(tmp_path), ".browser", "miniapp_inbox")
    old = _file(d, "a.json.tmp")
    new = _file(d, "b.json.tmp")
    req = _file(d, "c.json")
    alive = _file(d, "alive")
    t = time.time() - 2 * 86400
    os.utime(old, (t, t))
    os.utime(req, (t, t))
    assert hk.clean_inbox_tmp(str(tmp_path), 24) == 1
    assert not os.path.exists(old)
    assert all(os.path.exists(p) for p in (new, req, alive))


def test_low_disk_sends_one_plain_message(tmp_path):
    sent = []
    st = hk.run(str(tmp_path), cfg(profiles=[], min_free_gb=10 ** 9), send=True,
                notify=sent.append, procs=[], disk_paths=[str(tmp_path)])
    assert len(sent) == 1 and "Disk space is low" in sent[0] and "<" not in sent[0]
    with open(os.path.join(str(tmp_path), ".browser", "housekeeping.log"),
              encoding="utf-8") as f:
        assert st["low"] and "LOW DISK" in f.read()


def test_enough_disk_or_no_send_is_silent(tmp_path):
    sent = []
    hk.run(str(tmp_path), cfg(profiles=[], min_free_gb=0), send=True, notify=sent.append,
           procs=[], disk_paths=[str(tmp_path)])
    hk.run(str(tmp_path), cfg(profiles=[], min_free_gb=10 ** 9), send=False,
           notify=sent.append, procs=[], disk_paths=[str(tmp_path)])
    assert sent == []


def test_disks_are_listed_once_each(tmp_path):
    rows = hk.disks(str(tmp_path), [str(tmp_path), str(tmp_path / "..")])
    assert len(rows) == 1 and rows[0]["free"] > 0


def test_crash_tells_the_owner(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(hk, "run", lambda **k: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(hk, "ROOT", str(tmp_path))
    monkeypatch.setattr(hk, "log", lambda *a, **k: None)
    import lib.config
    import lib.telegram
    monkeypatch.setattr(lib.config, "load", dict)
    monkeypatch.setattr(lib.telegram, "notify", lambda c, text: sent.append(text))
    assert hk.main(["--send"]) == 1
    assert sent and "housekeeping failed: boom" in sent[0]
