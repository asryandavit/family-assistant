"""Size-capped plain-text logs: rotate a log file once it passes a size, keep a few old copies.

    append(path, line)              rotate if over the cap, then append one line
    rotate(path, max_bytes, keep)   path -> path.1 -> ... -> path.<keep>; the oldest is dropped

Rotation renames when it can. When the live file cannot be renamed because another process
holds it open (on Windows the listener keeps .browser/listener.log open for its whole life),
it copies the file to path.1 and truncates the original in place; the holder appends in
append mode, so its next line lands at the new end of the file. A line written between the
copy and the truncate is lost; that window is milliseconds.

Never raises: a log that cannot be rotated must not break the job that writes it.
Additive (CLAUDE.md §1): nothing in lib/ called this before 2026-11-10, decision 103.
"""
import os
import shutil

DEFAULT_MAX_BYTES = 2_000_000
DEFAULT_KEEP = 3


def _size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def rotate(path, max_bytes=DEFAULT_MAX_BYTES, keep=DEFAULT_KEEP):
    """Rotate `path` if it is larger than max_bytes. Returns True when it rotated."""
    if keep < 1 or _size(path) <= max_bytes:
        return False
    try:
        oldest = f"{path}.{keep}"
        if os.path.exists(oldest):
            os.remove(oldest)
        for i in range(keep - 1, 0, -1):
            src = f"{path}.{i}"
            if os.path.exists(src):
                os.replace(src, f"{path}.{i + 1}")
        try:
            os.replace(path, path + ".1")
        except PermissionError:
            # held open by another process (Windows): copy, then truncate in place
            shutil.copyfile(path, path + ".1")
            with open(path, "r+b") as f:
                f.truncate(0)
        return True
    except OSError:
        return False


def append(path, line, max_bytes=DEFAULT_MAX_BYTES, keep=DEFAULT_KEEP):
    """Append one line (newline added) to path, rotating first if it is over the cap."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        rotate(path, max_bytes, keep)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
