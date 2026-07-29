"""
sqlite_probe.py - capability + behaviour probe for the coach bot's storage layer.

Answers, against the real SQLite build and the real filesystem:
  1. Which SQLite engine version is bundled with this Python.
  2. Whether WAL actually engages on this volume (it does not on network shares).
  3. Whether STRICT tables are supported, and exactly what they reject.
  4. Whether busy_timeout is honoured when a second writer contends.
  5. Whether a reader can proceed while a writer holds the write lock.

Writes and deletes D:\\Claude\\family-assistant\\tmp\\sqlite_probe.db only.
"""

import ctypes
import pathlib
import sqlite3
import sys
import time

REPO = pathlib.Path(r"D:\Claude\family-assistant")
TMP = REPO / "tmp"
DB = TMP / "sqlite_probe.db"


def line(key, value):
    print(f"{key:<24}: {value}")


def cleanup():
    for suffix in ("", "-wal", "-shm"):
        p = pathlib.Path(str(DB) + suffix)
        if p.exists():
            try:
                p.unlink()
            except OSError as exc:
                print(f"  ! could not delete {p.name}: {exc}")


TMP.mkdir(parents=True, exist_ok=True)
cleanup()

print("=== environment ===")
line("python", sys.version.split()[0])
line("sqlite engine", sqlite3.sqlite_version)
line("threadsafety", sqlite3.threadsafety)
line("db path", DB)

drive_names = {
    0: "unknown", 1: "no root dir", 2: "removable",
    3: "fixed (local disk)", 4: "NETWORK SHARE", 5: "cd-rom", 6: "ram disk",
}
try:
    dt = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(str(REPO.drive) + "\\"))
    line("drive type", f"{REPO.drive} -> {dt} = {drive_names.get(dt, '?')}")
except Exception as exc:
    line("drive type", f"could not determine: {exc}")

con = sqlite3.connect(DB, isolation_level=None)

print("\n=== pragmas ===")
line("journal_mode", con.execute("PRAGMA journal_mode=WAL").fetchone()[0])
con.execute("PRAGMA busy_timeout=3000")
line("busy_timeout", con.execute("PRAGMA busy_timeout").fetchone()[0])
con.execute("PRAGMA foreign_keys=ON")
line("foreign_keys", con.execute("PRAGMA foreign_keys").fetchone()[0])
line("synchronous", con.execute("PRAGMA synchronous").fetchone()[0])

print("\n=== STRICT tables ===")
strict_ok = False
try:
    con.execute(
        "CREATE TABLE probe_strict ("
        "  id INTEGER PRIMARY KEY,"
        "  kg REAL NOT NULL,"
        "  reps INTEGER NOT NULL DEFAULT 0"
        ") STRICT"
    )
    strict_ok = True
    line("CREATE ... STRICT", "supported")
except sqlite3.Error as exc:
    line("CREATE ... STRICT", f"NOT SUPPORTED: {exc}")

if strict_ok:
    cases = [
        ("REAL <- 84.3 (float)", "kg", 84.3),
        ("REAL <- '84.3' (str)", "kg", "84.3"),
        ("REAL <- 'eighty-four'", "kg", "eighty-four"),
        ("INTEGER <- 3.7", "reps", 3.7),
        ("INTEGER <- 3.0", "reps", 3.0),
    ]
    for label, col, value in cases:
        other = "reps" if col == "kg" else "kg"
        default = 0 if other == "reps" else 0.0
        try:
            cur = con.execute(
                f"INSERT INTO probe_strict ({col}, {other}) VALUES (?, ?)",
                (value, default),
            )
            stored = con.execute(
                f"SELECT {col}, typeof({col}) FROM probe_strict WHERE id=?",
                (cur.lastrowid,),
            ).fetchone()
            line(label, f"ACCEPTED -> {stored[0]!r} as {stored[1]}")
        except sqlite3.Error as exc:
            line(label, f"REJECTED -> {type(exc).__name__}: {exc}")

print("\n=== lock behaviour (two connections, file-level locks) ===")
con2 = sqlite3.connect(DB, isolation_level=None)
con2.execute("PRAGMA busy_timeout=3000")

con.execute("BEGIN IMMEDIATE")
con.execute("INSERT INTO probe_strict (kg, reps) VALUES (99.9, 1)")

t0 = time.monotonic()
try:
    rows = con2.execute("SELECT count(*) FROM probe_strict").fetchone()[0]
    line("read during write", f"OK in {time.monotonic() - t0:.3f}s (sees {rows} committed rows)")
except sqlite3.Error as exc:
    line("read during write", f"BLOCKED after {time.monotonic() - t0:.2f}s: {exc}")

t0 = time.monotonic()
try:
    con2.execute("BEGIN IMMEDIATE")
    line("2nd writer", f"acquired lock in {time.monotonic() - t0:.2f}s - UNEXPECTED")
    con2.execute("ROLLBACK")
except sqlite3.Error as exc:
    line("2nd writer", f"waited {time.monotonic() - t0:.2f}s then {type(exc).__name__}: {exc}")

con.execute("ROLLBACK")

print("\n=== sidecar files ===")
for suffix in ("", "-wal", "-shm"):
    p = pathlib.Path(str(DB) + suffix)
    line(p.name, "present" if p.exists() else "absent")

con2.close()
con.close()
cleanup()
print("\ndone.")
