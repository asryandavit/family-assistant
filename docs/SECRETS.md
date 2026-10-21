# SECRETS.md — everything this system needs that is NOT in Git

Every key, token, credential file and machine-specific setting, where it lives today, and
how to recreate it. **Values never go in this file or anywhere in Git** — only names.
`python selfcheck.py` checks each item below and names whatever is missing; run it after
any change and after moving machines.

Keep this file current: any change that adds a new secret updates this table in the same
commit (CLAUDE.md §1/§10).

## 1. Inventory

| # | Name | Kind | Lives today | Used by | Required | How to (re)create |
|---|---|---|---|---|---|---|
| 1 | `TELEGRAM_BOT_TOKEN` | env var (Windows user) | this PC | everything that sends/receives Telegram | **yes** | @BotFather → /mybots → *Davit Family Assistant* → API Token (or /revoke for a new one; the old one stops working) |
| 2 | `TELEGRAM_CHAT_ID` | env var | this PC | Davit's chat — owner, system messages, travel alerts | **yes** | Davit sends /start; the id appears in `.browser/listener.log` as "ignored message from foreign chat …" if unset |
| 3 | `TELEGRAM_CHAT_ID_2` | env var | this PC | Karine's chat (decision 082) | optional | same as #2, from Karine's chat |
| 4 | `secrets/service_account.json` | file (gitignored) | this PC | Google Sheets / Drive writes (travel Sheet, Shopping list, future health Sheets) | **yes** | Google Cloud → project `family-assistant-503305` → IAM → Service accounts → `sheets-writer@…` → Keys → Add key (JSON). Delete the old key there if the file may have leaked. |
| 5 | Sharing of each Google Sheet with the service account | Google Drive setting | Google | travel Sheet (`config.json` `spreadsheet_id`), Shopping list (`config_coach.json` `shopping_sheet_id`), later health Sheets | **yes** | each Sheet → Share → `sheets-writer@family-assistant-503305.iam.gserviceaccount.com` → Editor. Moves with Google, not with the PC. |
| 6 | `YOUTUBE_API_KEY` | env var | this PC (once created) | `jobs/exercise_videos.py` (exercise video library) | optional | §3 below |
| 7 | Claude Code login (`claude` CLI) | per-user login on the machine | this PC | travel insight line, future /health assistant (`claude -p`, Max subscription) | yes for those | install Claude Code, run `claude` once and sign in with the Max account. **`ANTHROPIC_API_KEY` must stay unset**, or `claude -p` bills the metered API. |
| 8 | `.browser/wizz`, `.browser/stays_*` | Playwright browser profiles (gitignored) | this PC | Wizz fare scan, Booking/Airbnb stays | yes for travel | recreated automatically on first run; first scans may meet a cookie/verification page — run once by hand with `headless: false` |
| 9 | `secrets/health_sheets.json` | file (gitignored) — *planned* | — | /health (docs/briefs/HEALTH_RECORDS.md) | when built | written by the health-records setup |
| 10 | `machine.json` | file (gitignored) — *planned* | — | machine-specific paths (COACH_SPEC §6) | when built | copy `machine.example.json` and fill in |
| 11 | Scheduled tasks `FamilyAssistant-*` | Windows Task Scheduler | this PC | listener (always on), daily travel scan, coach jobs | **yes** | `scheduler/register-listener.ps1`, `scheduler/register-tasks.ps1` (elevated PowerShell); coach tasks per their scripts |

Not secrets, already in Git: spreadsheet ids, Drive links (`config.json`, `config_coach.json`).

## 2. Rules

- Secrets live in **environment variables** or the gitignored `secrets/` folder — nowhere
  else. `.gitignore` covers `secrets/`, `service_account.json`, `.browser/`, `.env`, `*.log`.
- Never paste a secret into a chat, an issue, a commit or a doc. If one leaks: revoke it at
  its source (BotFather /revoke, Google Cloud key delete, API key regenerate), then replace.
- One Telegram poller per bot token (decision 002): when moving, **stop the old machine's
  listener before starting the new one**, or the two steal each other's messages.

## 3. YouTube API key — step by step (now)

1. Open <https://console.cloud.google.com/> signed in with the Google account that owns the
   project **family-assistant-503305** (the one the bot's Sheets account lives in).
2. Top bar → project picker → select **family-assistant-503305**.
3. ☰ menu → **APIs & Services → Library** → search **YouTube Data API v3** → **Enable**.
4. **APIs & Services → Credentials → + Create credentials → API key.** Copy the key shown.
5. Click the new key → **Edit**: name it `family-assistant youtube`; under **API
   restrictions** choose **Restrict key** → tick **YouTube Data API v3** → **Save**.
   (Leave application restrictions at None; your home IP changes.) No billing is needed for
   the free daily quota.
6. On this PC, in **your own** PowerShell window (not in a chat), run — with your key in
   place of the placeholder:
   ```powershell
   [Environment]::SetEnvironmentVariable("YOUTUBE_API_KEY", "PASTE-YOUR-KEY-HERE", "User")
   ```
7. Close and reopen any terminal, then check: `python selfcheck.py` → `env YOUTUBE_API_KEY
   set (39 chars)`.

## 4. Moving to another machine (Windows PC, Linux server or AWS)

Do these in order; tick each.

1. **On the old machine:** `python selfcheck.py` and save the output — it's the list of what
   the new machine must have. Copy `secrets/service_account.json` to a USB stick or password
   manager (it's one file; don't email it).
2. **New machine:** install Python 3.12+, Git, `pip install -r requirements.txt`,
   `playwright install chromium`, Claude Code (#7) and sign in. Clone
   `asryandavit/family-assistant` (set `git config user.name/user.email` for this repo).
3. **Secrets:**
   - Windows: set #1, #2, #3, #6 as *user* environment variables
     (`[Environment]::SetEnvironmentVariable(...)`).
   - Linux server: put them in a root-only file, e.g. `/etc/family-assistant.env`
     (`chmod 600`), loaded by the service (systemd `EnvironmentFile=`).
   - **AWS:** store #1–#4 and #6 in **AWS Secrets Manager** (or SSM Parameter Store,
     *SecureString*) and have the service read them at start-up into the environment; give
     the instance an IAM role allowed to read only those secrets. Never bake them into an
     AMI, a Docker image or user-data.
   - Put `secrets/service_account.json` in place (or fetch it from Secrets Manager into that
     path at start-up, file mode 600).
4. **Scheduling:** Windows → run the `scheduler/*.ps1` scripts. Linux/AWS → these are
   Windows-only (`schtasks`, `pythonw`); replace with a systemd service for the listener and
   systemd timers or cron for the jobs, keeping the same times (Asia/Yerevan) — only
   `scheduler/` and `lib/tasks.py` need to change (CLAUDE.md §6).
5. **Browser scans on a server:** set `headless: true` in `config.json` for Wizz and stays;
   expect a first-run verification page — run once interactively if needed.
6. **Stop the old listener**, then start the new one (decision 002).
7. `python selfcheck.py` on the new machine → every line OK (warnings only for optional
   items you chose not to set). Send `/status` and `/menu` from both phones.
8. On the old machine, delete `secrets/` and the user environment variables once the new
   one has run for a day.

Google sharing (#5) and the bot token itself don't change when moving — only where the
token is stored.
