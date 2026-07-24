import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import claude, config, sheets, telegram

JOB = "meals"


def main():
    cfg = config.load()
    try:
        out = claude.run(cfg, "prompts/meals.md", data={"date": date.today().isoformat()})
        sheets.append_rows(cfg, "Meals", out.get("rows", []))
        sheets.log_run(cfg, JOB, "ok")
        if out.get("summary"):
            telegram.notify(cfg, "Today's meals:\n" + out["summary"])
    except Exception as e:
        sheets.log_run(cfg, JOB, "error", str(e)[:300])
        telegram.notify(cfg, f"Meals job errored: {e}")
        raise


if __name__ == "__main__":
    main()
