# HEALTH RECORDS BRIEF — on-demand lab records per person

Self-contained brief for one Claude Code session. **Build only after the "Daily plan in
Telegram" session (card 2) has finished** — both edit `listener.py` and `lib/`.
Planned 2026-10-19 from the owner's amendments; the system prompt is
`prompts/health_records.md`. Read first: `CLAUDE.md`, `docs/TELEGRAM_UX.md` (§5a routing),
`docs/DECISIONS.md` 079 and 082, `docs/COACH_SPEC.md` §2 (privacy) and §13 (AI layer).

---

## 1. What it is

`/health` opens a private, on-demand assistant for **one person's** health record:
read a lab report (photo or text, Armenian / Russian / English), check it in code, save it
after the person confirms, review trends, prepare questions for the doctor, and propose
plain-language changes to the meal/training plan that apply only when approved.

**Owner's amendments (binding):**

1. **Strictly on-demand.** No proactive messages. Lab-recheck reminders are opt-in per
   person, default **off**.
2. **Storage follows decision 079:** one private Google Sheet per person, tabs
   `lab_results`, `medications`, `notes`, `appointments`, `wellness_brief`. Tools are
   closures bound to that person's spreadsheet id. Health Sheets are backed up quarterly by
   copying to a private Drive backup folder (Task Scheduler).
3. **Lab extraction goes through a code validator** (units, per-analyte plausibility,
   HOMA-IR / non-HDL / Friedewald consistency, reference-range parse) **before** the
   confirmation step. Failed rows are quarantined and cannot be saved.
4. **`publish_brief()` → `propose_brief()` + `approve_brief()`;** planners read approved
   briefs only.
5. **Consent flag per person;** a record is created only from the person's own chat;
   guardian role only for minors.

Out of scope: diagnosis, medication advice or doses, anything proactive, sharing between
people, reading anyone else's record.

## 2. Architecture

```
Telegram  /health  (or a photo/document while a /health conversation is open)
   │
listener.py ── conversation state per chat (30-min expiry, /stop exits; COACH_SPEC §11)
   │  launches as a job, like /price, with the asker's chat (decision 082)
jobs/health_turn.py ── resolves chat → person → that person's sheet id, consent check
   │
claude -p  --mcp-config <per-run file>  --allowedTools "mcp__health__*"
           --append-system-prompt-file prompts/health_records.md   --resume <session>
   │  (Max subscription, not the API — COACH_SPEC §13; cross-process claude lock)
coach/health_mcp.py ── local stdio MCP server started for THIS person only:
   │  every tool is a closure over one spreadsheet id; there is no tool that takes a
   │  person or sheet argument, so another person's data is unreachable by construction
lib/health_validate.py ── pure, deterministic, unit-tested validator (§4)
lib/health_store.py ── gspread read/write of the 5 tabs (service account, decision 079)
```

**Discovery first (CLAUDE.md §8 — measure, don't assume):**

1. `claude -p` with `--mcp-config` + `--allowedTools` calls tools from a tiny test MCP
   server, **when launched from the listener** (pythonw scheduled task, not from inside a
   Claude Code session — the nested call failed on 2026-10-18).
2. Image input: a downloaded Telegram photo passed to `claude -p` (file path in the prompt
   or `--add-dir`) is read correctly; test with a real Armenian and a Russian lab sheet.
3. Conversation continuity: `--resume <session_id>` (from `--output-format json`) keeps the
   intake → validate → confirm flow across Telegram messages; measure latency per turn.
4. gspread: create the five tabs, append rows, read back; Drive `files.copy` into the
   backup folder with the service account.

If (1) or (3) fails, stop and report: the fallback is a stateless design (each turn sends
the conversation so far), which must be agreed with the owner first.

## 3. Storage — one private Sheet per person

Created in the **person's own Drive** (Karine's in Karine's Drive), shared with the bot's
service account `sheets-writer@family-assistant-503305.iam.gserviceaccount.com` as Editor
(the person or owner does the share; the session shows the exact action and asks).
Sheet ids live in a **gitignored** `secrets/health_sheets.json`
(`{"<chat_id>": {"person": "davit", "sheet_id": "...", "role": "self"}}`), never in Git.

| Tab | Columns |
|---|---|
| `profile` (metadata) | person, display_name, birth_year, consent_given_on, reminder_optin, guardian_of |
| `lab_results` | panel_id, panel_date, lab_name, analyte_code, analyte_name_as_printed, value, unit, value_si, unit_si, ref_low, ref_high, ref_text, flag, source (photo/text), saved_utc |
| `medications` | name, dose, started_on, stopped_on, note, updated_utc |
| `notes` | kind (question / doctor_said / context), text, created_utc |
| `appointments` | date_local, with_whom, note |
| `wellness_brief` | brief_id, status (proposed / approved / rejected), field, before, after, reason, proposed_utc, approved_utc |

Rules: dates `*_local` / `*_utc` per CLAUDE.md §4. `lab_results` is append-only (corrections
are new rows + a note). Every value is written by code after validation, never typed by
the model. No health data in Telegram messages to anyone but the person, in logs
(log only counts and ids), or in Git.

**Honest limit, said once in the consent text:** isolation is enforced by the bot's code
and the per-person tool server. The bot's service-account key is on Davit's computer, so it
is not cryptographic separation from the machine owner.

**Backups:** `FamilyAssistant-Coach-HealthBackup`, quarterly, registered only through
`scheduler/` after the owner's yes: Drive `files.copy` of each health Sheet into that
person's private backup folder (`Health backups`, shared with the service account), named
`<person> health backup <YYYY-MM-DD>`; keep the last 8. Plus Sheets' own version history.

## 4. Validator — `lib/health_validate.py` (numbers are code)

Input: rows extracted by the model. Output per row: `ok` or `quarantined` + a reason in a
human sentence. Pure functions, every rule unit-tested, rejection paths included.

- **Codes:** map to the enum `ALT, AST, GGT, ALP, BILI_T, BILI_D, TC, LDL, HDL, TG,
  NON_HDL, APOB, LPA, GLU, HBA1C, INSULIN, HOMA_IR, CREA, VIT_D, B12, FIB4, PLT` (PLT is
  added because FIB-4 needs platelets). Unknown code → quarantined ("not a known test").
- **Values:** decimal comma normalised (`3,4` → 3.4), `<`/`>` qualifiers kept separately,
  non-numbers quarantined.
- **Units:** an allow-list per analyte with exact conversions to one SI unit
  (e.g. cholesterol mg/dL ÷ 38.67 → mmol/L, TG mg/dL ÷ 88.57, glucose mg/dL ÷ 18.016,
  creatinine mg/dL × 88.42 → µmol/L, vitamin D ng/mL × 2.496 → nmol/L, HbA1c % ↔
  mmol/mol via the IFCC equation). Unit missing or not allowed → quarantined.
- **Plausibility:** a wide physiological range per analyte in SI units (rejects typos like
  LDL 34 mmol/L); outside → quarantined, never "corrected".
- **Reference range parse:** `3.5–5.0`, `3.5-5.0`, `< 5.2`, `> 1.0`, `до 5,2`,
  `մինչև 5.2` → ref_low/ref_high; unparseable → keep `ref_text`, flag computed only when
  numeric bounds exist. The printed flag is cross-checked against the computed one.
- **Panel consistency** (same panel date, all needed analytes present, SI units):
  - `NON_HDL ≈ TC − HDL`
  - Friedewald `LDL ≈ TC − HDL − TG / 2.2` (mmol/L), only when TG < 4.5 mmol/L and LDL
    is reported as calculated; measured LDL is not forced to match
  - `HOMA_IR ≈ GLU (mmol/L) × INSULIN (µU/mL) / 22.5`
  - `FIB4 ≈ age × AST / (PLT × √ALT)` (age from `profile.birth_year`)
  Tolerance per formula (rounding on printed values); a mismatch quarantines the derived
  row with both numbers shown. Derived values are never computed for display by the model.
- **Trends** (`get_results` / review): `then → now`, absolute and % change, direction vs
  reference — computed by code and returned by the tool; the model only phrases them.

## 5. Tools (the MCP server, bound to one person)

`get_profile()`, `record_consent()`, `set_reminder_optin(bool)`, `get_panels()`,
`get_results(analyte_codes, since)` (with computed deltas), `validate_rows(rows)`,
`save_panel(rows)` (re-validates; refuses any non-ok row or without consent),
`get_medications()`, `set_medication(name, dose, started_on, stopped_on, note)`,
`get_notes(kind)`, `save_note(kind, text)`, `get_appointments()`,
`set_appointment(date, with_whom)`, `propose_brief()`, `approve_brief(brief_id)`,
`export_record()` (CSV/JSON file sent to the person's chat only), `delete_record()`
(two-step: the bot asks the person to type `DELETE <display name>`; then the Sheet's tabs
are cleared and the backups listed for manual removal — irreversible, said plainly).

Every write tool checks consent first and refuses without it.

## 6. Briefs: proposed → approved → planners

`propose_brief()` derives **non-medical constraints only** from the record (e.g. saturated
fat cap, fibre target, alcohol, eggs per week, fish per week) using fixed, tested rules —
never raw lab values — and returns a diff against the last approved brief. The person sees
the diff in plain words and approves or rejects. Planners (daily plan, basket) read only
`status = approved`; nothing else in the bot can read the health Sheet.

**Open question for the owner:** in today's manual stage the plan lives in `plan/*.md`.
Does an approved brief (a) only show as "pending plan changes" that Davit then asks Claude
to apply to `plan/`, or (b) get read by the daily-plan job and shown as notes? Default (a).

## 7. Consent, people, roles

- Allowed people = the two bot chats (decision 082). A record is created **only from the
  person's own chat**; `/health` from another chat can never open or create it.
- Consent: first `/health` explains in three sentences what is stored, where, who can see
  it (including the honest limit in §3), then asks for yes; `record_consent()` stores the
  date. No consent → nothing is saved, nothing is read.
- **Guardian role only for minors (the son):** the record is the son's; **open question:**
  which chat(s) hold guardian access — Davit's, Karine's, or both? Guardians see only the
  minor's record, never each other's. Default: ask.
- Karine's record is Karine's: created from Karine's chat, in Karine's Drive, with Karine's
  consent. Davit's chat cannot reach it.

## 8. Telegram UX (docs/TELEGRAM_UX.md)

- `/health` and a 🩺 Health entry inside **⚙️ System** (or its own Home section once built)
  — both open the conversation for the chat that tapped it.
- Photos and documents are read **only** inside an open `/health` conversation; otherwise
  the bot ignores them as today.
- Tables in `<pre>` blocks; quarantined rows marked ⚠ with the reason; long reviews folded.
- Silent replies; every reply goes to the asking chat only (never `send_family`).
- Red-flag symptoms → urgent-care message first, as the prompt says.
- Opt-in recheck reminders (only if `reminder_optin`): one silent message on the recheck
  date the person set, nothing else.

## 9. Steps (one commit each; show real console output after each)

1. Discovery probes (§2) — report, decide fallback with the owner if needed.
2. `lib/health_validate.py` + tests (all rules, rejection paths, real lab fixtures the
   owner provides — never invented lab sheets).
3. `lib/health_store.py` + per-person Sheet creation/sharing (owner's yes), tests with a
   fake gspread.
4. `coach/health_mcp.py` + tests: tools bound to one sheet id; no cross-person path.
5. `jobs/health_turn.py` + `prompts/health_records.md` wiring; conversation state.
6. `listener.py`: `/health`, photo routing inside the conversation (own commit, additive,
   all routing tests green incl. `tests/test_listener_two_chats.py`).
7. Brief propose/approve + planner hook per the owner's answer to §6.
8. Backup task via `scheduler/` (owner's yes), export, delete flow.
9. Docs: decision in `docs/DECISIONS.md`, `docs/TELEGRAM_UX.md`, `docs/SECRETS.md` (sheet-id
   file), `plan/tracking.md` (points to /health for lab results).

Done when: tests green, a real lab sheet goes photo → validated table → confirm → saved →
review, a quarantined row cannot be saved, the other person's chat cannot reach the record,
and the owner has approved one brief diff end to end.
