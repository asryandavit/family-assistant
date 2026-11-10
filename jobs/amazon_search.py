"""/amazon worker: drains the Amazon queue, one browser job at a time (amazon/queue.py).

Started by the listener when a /amazon job is queued; exits when the queue is empty.
    python jobs/amazon_search.py            drain the queue
    python jobs/amazon_search.py --once "usb c charger 65w" [--stores uk,de] [--chat ID]
                                            run one search now (demo / measuring)
"""
import argparse
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from amazon import data_dir, queue, search  # noqa: E402
from lib import config, logfile, telegram, ui  # noqa: E402


def log(msg):
    line = "%s %s" % (ui.now_local().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    logfile.append(os.path.join(data_dir(ROOT), "worker.log"), line)   # capped, decision 103


def run(job, cfg):
    today = ui.now_local().date()
    if job.get("kind", "search") == "search":
        return search.run_search(job, cfg, ROOT, telegram, today, log=log)
    log("unknown job kind %r" % job.get("kind"))
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
            log("job %s %s" % (job.get("job"), job.get("kind")))
            try:
                log("job %s -> %s" % (job.get("job"), run(job, cfg)))
            except Exception as e:  # noqa: BLE001 - tell the asker and the owner, keep draining
                log("job %s crashed: %s\n%s" % (job.get("job"), e, traceback.format_exc()))
                telegram.send_html(cfg, "⚠️ Amazon search failed (%s). Try again or tell Davit."
                                   % telegram.esc(str(e)[:100]), silent=True, chat_id=job.get("chat_id"))
                telegram.notify(cfg, "⚠️ SYSTEM: /amazon job crashed: %s" % str(e)[:200])
    finally:
        queue.release(ROOT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once")
    ap.add_argument("--stores", default="")
    ap.add_argument("--chat")
    a = ap.parse_args()
    cfg = config.load()
    if a.once:
        chat = a.chat or telegram.allowed_chats(cfg)[0]
        job = {"job": queue.new_id(), "kind": "search", "chat_id": chat, "description": a.once,
               "stores": [s for s in a.stores.split(",") if s] or None, "no_questions": True}
        queue.enqueue(job, ROOT)
    drain(cfg)


if __name__ == "__main__":
    main()
