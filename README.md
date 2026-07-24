# Family Assistant — scheduled jobs (free stack)

Runs on your always-on Windows PC. **Trigger:** Windows Task Scheduler.
**Reasoning:** `claude -p` (uses your Max plan — no metered API cost).
**Storage:** Google Sheets only. Nothing about your trips lives on the machine —
only the code and two credential files (service account + browser profile).

## What v1 does automatically
- `jobs/travel_scan.py` — pulls the Wizz Air fare finder from Yerevan (EVN),
  hands the fares to Claude for analysis, writes rows to the `Flights` tab,
  and Telegrams you only when a fare beats your threshold.
- `jobs/training.py` and `jobs/meals.py` — same skeleton, no scraper: a prompt
  goes to `claude -p`, the result lands in a Sheets tab + Telegram.

Accommodation (Booking / Airbnb / Kiwi open-jaw) stays **on-demand** — you run
that deep-dive in claude.ai/Cowork when a flight deal fires. See `prompts/`.

## The one honest caveat: first run is a discovery run
The Wizz scraper doesn't guess their internal fare API. On first run it captures
every JSON response the fare-finder page makes and writes previews to
`.browser/discovery.json`. You look at that once, find the response that contains
fares, and paste a matching URL fragment into `config.json → wizz.fare_api_match`.
After that it runs unattended. If Wizz redesigns and it breaks, re-run discovery.

The scraper treats any CAPTCHA / "verify you're human" page as a **hard stop** —
it logs `blocked` to the `Runs` tab and exits. It never clicks through one.

## Setup order (once)
1. `pip install -r requirements.txt` then `playwright install chromium`
2. Google Sheet:
   - Create one spreadsheet with tabs: `Flights`, `Training`, `Meals`, `Config`, `Runs`.
   - Create a Google Cloud service account, download its JSON to `secrets/service_account.json`.
   - Share the sheet (Editor) with the service account's email.
   - Put the spreadsheet ID in `config.json`.
3. Telegram: set env vars `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` on the machine
   (System Properties → Environment Variables). Nothing secret goes in the repo.
4. Make sure `claude` (Claude Code CLI) is installed and logged into your Max account:
   `claude -p "say hi"` should work from a plain terminal.
5. Edit `config.json` (watchlist routes, threshold, date windows).
6. First manual run: `python jobs/travel_scan.py` → do the discovery step above.
7. Register schedules: run `scheduler/register-tasks.ps1` in an elevated PowerShell.

## Cost note
Keep the Claude step as `claude -p` on this box. If you ever move triggering to
n8n, still call `claude -p` locally — do **not** call the Anthropic API directly
from a workflow, that's metered and defeats the "free" point.

## Files that must stay out of Git
`secrets/`, `.browser/`, and anything with a token. A `.gitignore` is included.
