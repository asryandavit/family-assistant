Family: Davit (EN) + wife (RU) + son born 29 Dec 2024. Yerevan, Armenia (Asia/Yerevan,
UTC+4). Davit is a senior full-stack developer (14 yrs, React/NestJS) and a heavy Claude
Code user.

Two systems live in this project:
1. family-assistant — LIVE. Wizz Air fare monitoring + Booking/Airbnb accommodation search,
   controlled from Telegram, stored in Google Sheets. Repo D:\Claude\family-assistant on an
   always-on Windows 11 PC.
2. Family Coach Bot — IN DESIGN. Daily training and meals for the two adults, with the
   toddler appearing only as play ideas and inline meal modifications. Separate build that
   reuses family-assistant's proven patterns.

Full architecture, conventions and known limitations live in the Google Doc
"Family Assistant — Current Architecture (shared context)". Read it before proposing
anything technical for either system.

Non-negotiable conventions (rationale in the doc):
- Host is the always-on Windows PC, not the Mac. Scheduling via Windows Task Scheduler.
- LLM calls go through `claude -p` as a subprocess with the prompt piped via STDIN — free
  on the Max plan. Never the Anthropic HTTP API or Agent SDK.
- Jobs are standalone scripts that run, send their own Telegram message, and exit. The
  listener only receives commands and launches them.
- Python does all arithmetic; the model only judges and phrases. Model output never carries
  unvalidated numbers into storage.
- Telegram: HTML parse mode, not MarkdownV2.
- Never bypass a CAPTCHA or bot wall. Stop, log it, hand me a prefilled link.
- Secrets in Windows environment variables and gitignored files, never in the repo.

Working style: be honest and push back on weak ideas rather than agreeing; recommendation
first with a short reason; small verifiable steps; no validation filler.