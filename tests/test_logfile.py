"""lib/logfile.py: size-capped logs (decision 103)."""
import os
import subprocess
import sys
import time

from lib import logfile


def _write(p, n):
    with open(p, "w", encoding="utf-8") as f:
        f.write("x" * n)


def test_under_cap_is_left_alone(tmp_path):
    p = str(tmp_path / "a.log")
    _write(p, 10)
    assert logfile.rotate(p, max_bytes=100, keep=3) is False
    assert os.listdir(tmp_path) == ["a.log"]


def test_missing_file_is_not_an_error(tmp_path):
    assert logfile.rotate(str(tmp_path / "none.log"), max_bytes=1, keep=3) is False


def test_rotation_shifts_and_drops_the_oldest(tmp_path):
    p = str(tmp_path / "a.log")
    for i in (1, 2, 3):
        _write(f"{p}.{i}", i)          # sizes 1, 2, 3 mark which copy is which
    _write(p, 200)
    assert logfile.rotate(p, max_bytes=100, keep=3) is True
    assert not os.path.exists(p)
    assert os.path.getsize(p + ".1") == 200
    assert os.path.getsize(p + ".2") == 1
    assert os.path.getsize(p + ".3") == 2      # the old .3 (size 3) is gone
    assert not os.path.exists(p + ".4")


def test_append_rotates_then_writes(tmp_path):
    p = str(tmp_path / "w.log")
    _write(p, 150)
    logfile.append(p, "hello", max_bytes=100, keep=2)
    with open(p, encoding="utf-8") as f:
        assert f.read() == "hello\n"
    assert os.path.getsize(p + ".1") == 150


def test_append_creates_the_folder(tmp_path):
    p = str(tmp_path / "sub" / "w.log")
    logfile.append(p, "x")
    assert os.path.exists(p)


def test_held_open_by_another_process_is_copied_and_truncated(tmp_path):
    """The listener keeps listener.log open for its whole life. On Windows that blocks a
    rename; the helper must copy + truncate instead, and the holder keeps appending."""
    p = str(tmp_path / "listener.log")
    _write(p, 300)
    holder = subprocess.Popen(
        [sys.executable, "-c",
         ("import sys,time\n"
         "f=open(sys.argv[1],'a',encoding='utf-8')\n"
         "print('ready',flush=True)\n"
         "sys.stdin.readline()\n"
         "f.write('after\\n'); f.flush()\n"
         "print('done',flush=True)\n"
         "time.sleep(0.2)\n"), p],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "ready"
        assert logfile.rotate(p, max_bytes=100, keep=3) is True
        assert os.path.getsize(p + ".1") == 300
        holder.stdin.write("go\n")
        holder.stdin.flush()
        assert holder.stdout.readline().strip() == "done"
    finally:
        holder.wait(timeout=10)
    with open(p, encoding="utf-8") as f:
        assert f.read() == "after\n"           # appended at the new end, no hole of NULs


def test_never_raises_on_a_bad_path(tmp_path):
    d = tmp_path / "isadir"
    d.mkdir()
    logfile.append(str(d), "x")                  # a folder, not a file: swallowed
    time.sleep(0)
