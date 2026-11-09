"""/china worker: drains the China queue, one Chrome job at a time (china/queue.py).

Started by the listener when a /china job is queued; exits when the queue is empty.
    python jobs/china_search.py            drain the queue
    python jobs/china_search.py --once "GaN charger 65W" [--sites pinduoduo,1688] [--chat ID]
                                           run one search now (demo / debugging)
"""
import argparse
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from china import data_dir, queue, search  # noqa: E402
from lib import config, telegram, ui  # noqa: E402


def log(msg):
    line = "%s %s" % (ui.now_local().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with open(os.path.join(data_dir(ROOT), "worker.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def run(job, cfg):
    today = ui.now_local().date()
    kind = job.get("kind", "search")
    if kind == "search":
        return search.run_search(job, cfg, ROOT, telegram, today, log=log)
    if kind == "reviews":
        return search.run_reviews(job, cfg, ROOT, telegram, log=log)
    log("unknown job kind %r" % kind)
    return "unknown"


def drain(cfg):
    if not queue.acquire(ROOT):
        log("another worker is running; exiting")
        return
    try:
        while True:
            job = queue.pop(ROOT)
            if not job:
                break
            queue.mark(job.get("job"), ROOT)
            log("job %s %s from %s" % (job.get("job"), job.get("kind"), "chat"))
            try:
                log("job %s -> %s" % (job.get("job"), run(job, cfg)))
            except Exception as e:
                log("job %s crashed: %s\n%s" % (job.get("job"), e, traceback.format_exc()))
                telegram.send_html(cfg, "⚠️ China search failed (%s). Try again or tell Davit."
                                   % telegram.esc(str(e)[:100]), silent=True,
                                   chat_id=job.get("chat_id"))
                telegram.notify(cfg, "⚠️ SYSTEM: /china job crashed: %s" % str(e)[:200])
    finally:
        queue.release(ROOT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once")
    ap.add_argument("--sites", default="")
    ap.add_argument("--chat")
    a = ap.parse_args()
    cfg = config.load()
    if a.once:
        chat = a.chat or telegram.allowed_chats(cfg)[0]
        job = {"job": queue.new_id(), "kind": "search", "chat_id": chat, "description": a.once,
               "sites": [s for s in a.sites.split(",") if s] or None, "no_questions": True}
        queue.enqueue(job, ROOT)
    drain(cfg)


if __name__ == "__main__":
    main()
