# Good Measure

*Every update, for good measure.*

Repository: https://github.com/Tarari-1/good-measure

Small nonprofits keep their budget and work plan in Excel and chase program teams by email. Good Measure turns the emails staff already send ("we paid $780 for the chapbook deposit", "the workshop series is 60% done") into **proposed** tracker updates, and drafts friendly nudges to whoever has not reported. A human tracker owner approves every change.

Everything runs on synthetic data for a fictional nonprofit, the **Bright Futures Literacy Network**. No real people, organisations or email addresses appear anywhere (all addresses use the reserved `.example` domain).

## How it works

```
 data/mailbox/*.eml ──► EmailSource (read-only)
                              │
            ┌─────────────────┴─────────────────┐
            │  MCP server (FastMCP, stdio)       │  the ONLY way agents touch
            │  reads + propose-only writes       │  trackers and mail
            └─────────────────┬─────────────────┘
                              │
   Coordinator ──delegates──► Intake   (emails → exact cell changes + supporting quote)
   (writes digest)        ├─► Checker  (reviews proposals; notes for the approver)
                          └─► Chaser   (overdue owners → nudge DRAFTS)
                              │
            deterministic defenses (code) on every proposal
                              │
   Review tab ──► human types name + Approve ──► re-validate ──► write ONE cell + change log
```

- **One model:** `gpt-6-luna` through Portkey, defined once in `backend/model.py` and shared by all four agents.
- **Agents never change anything.** MCP write tools only *propose* (`propose_budget_change`, `propose_activity_change`) or *draft* (`save_nudge_draft`). No tool applies a change, sends mail or deletes anything.
- **Approval is a backend route, not an agent tool.** `POST /api/proposals/{id}/approve` needs the approver's typed name, re-runs every defense against the current tracker, then writes the cell and a `change_log` row.

### The five deterministic defenses (`tracker/defenses.py`, plain code)

| # | Defense | What it does |
|---|---------|--------------|
| 1 | Untrusted email | Email text reaches agents only inside `<<<UNTRUSTED_EMAIL …>>>` delimiters (fake delimiters inside an email are removed). Emails containing instructions aimed at an AI are quarantined: any proposal from them is blocked. A canary in the agent instructions blocks any proposal or draft that leaks them. |
| 2 | Grounding | The quote must appear in the email, and every number and date the proposal would write must appear in the email (`$1,240.50` matches `1240.5`; ids like `WP-02` and `LOB-2291` do not count as numbers). A new due date also needs a sentence saying the deadline moves ("slips to", "is moving"): a booked event date is not a due date. |
| 3 | Permission | The sender (read from the email, never from the agent) may only change rows of their own program. Unknown senders change nothing. |
| 4 | Rules & overspend flags | Only `spent_to_date`/`committed` (budget) and `status`/`percent_complete`/`due_date`/`notes` (work plan) can change; values are validated. Spend is only booked to a line whose keywords (e.g. "books", "catering") appear in the email. **Overspend is flagged, never blocked:** money already spent is recorded even if it takes a line over budget, with an automatic OVERSPEND flag and the overage, new remaining and now-unfunded commitments; a new commitment that goes over budget is held as "needs decision". Approving any OVERSPEND change needs an explicit acknowledgement (checkbox in Review, `acknowledged=true` enforced by the backend). Dependency conflicts are flagged for the approver. |
| 5 | Run caps | Only emails selected for the run; max proposals per email and per run; max emails per run; shared request, tool-call and token limits, and per-agent and per-run timeouts (`config/settings.py`). Loop protection refuses repeated identical tool calls and repeat delegations. |

Every block is stored on the proposal with its reason, shown in the Review and Safety tabs, and written to the append-only audit trail (`output/audit_trail.json`, secrets redacted).

Two more code checks sit on what agents *say*:
- **Checker notes:** every id in a Checker note must belong to the proposal it reviews, and a concern must name that row. A failing note is sent back to the Checker once; if it is still wrong it is shown as "unverified".
- **Intake claims:** an email Intake reports as "proposed" must have a recorded proposal; otherwise it is shown as `claimed_without_proposal`.

## Layout

```
backend/        FastAPI app (main.py), agents (agents.py), shared model (model.py),
                run orchestration + token/cost tracking (runner.py), run summaries (report.py),
                human approval path (approvals.py), typed agent outputs (schemas.py), prompts/
mcp_server/     server.py: the FastMCP stdio server (8 read tools, 3 propose/draft tools)
tracker/        core library: db.py, defenses.py, proposals.py, prefilter.py, chase.py,
                email_source.py, imap_source.py (optional), export.py (.xlsx), audit.py, store.py
config/         settings.py (paths, demo date, caps, cost-measure flags, .env lookup), pricing.py
data/           tracker.db (original, never modified), seed/*.csv, mailbox/*.eml, gold_answers.json
                tracker_working.db, local_mail/ and *.json state are created at runtime (git-ignored)
scripts/        check_models.py, reset_db.py, seed_db.py, live_run.py, score_run.py, cost_experiment.py
tests/          pytest: defenses, MCP tools, agent wiring (scripted model), API, stage-2 features, IMAP (mocked)
frontend/       React + Vite + TypeScript dashboard
output/         committed evidence: run reports, scores, cost experiment, screenshots/
                (audit_trail.json and runs/ are created at runtime and git-ignored)
```

## Setup (about 3 minutes)

Requirements: Python 3.13, Node 20+ (tested with Node 24).

```bash
git clone https://github.com/Tarari-1/good-measure.git
```

```bash
cd good-measure
```

```bash
python3.13 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements.txt
```

```bash
npm --prefix frontend install
```

```bash
cp .env.example .env
```

Then put your Portkey key in `.env` (`PORTKEY_API_KEY=...`). **The default path needs only `PORTKEY_API_KEY` and the bundled sample mailbox.** The IMAP lines in `.env.example` are optional and commented out.

### Where the .env file is looked for

`config/settings.py` checks two places and uses the **first** one it finds:

1. `good-measure/.env` (this folder)
2. `../.env` (the folder one level above this repo)

So a key shared by several course projects can live one folder up. To check it: move `.env` one folder up, restart the backend, and `GET /api/health` reports `"env_source": "../.env (one folder up)"` (it never shows the key). `tests/test_config.py` tests the lookup order.

## Run

Backend (from the repo folder):

```bash
.venv/bin/uvicorn backend.main:app --port 8000
```

Frontend (second terminal):

```bash
npm --prefix frontend run dev
```

Open http://localhost:5173. The tabs follow the workflow:

1. **Inbox** – tick emails, press *Process selected*. *Paste an email* processes one email you type in (same defenses). With IMAP configured, a *Connect inbox* panel also appears.
2. **Review** – each proposed change as before → after, with the supporting sentence highlighted in the email. Type your name, then Approve or Reject. Blocked proposals show the defense that stopped them.
3. **Trackers** – budget and work plan; approved changes are highlighted. *Download .xlsx* exports both trackers with the same highlights and a change log sheet.
4. **Chase** – who is overdue and why, and the drafted nudges (copy button; nothing is sent).
5. **Digest** – burn vs plan per program, at-risk milestones, late owners, and the Coordinator's narrative.
6. **Safety** – the five defenses, the blocks and skips from the latest run with reasons, the quarantined injection email, and a *Run defense tests* button (runs `tests/test_defenses.py`, no model).
7. **Run details** – the agent trace; tokens (input / cached / cache-write / output), requests and cost per run, per agent and per email.

**No-model mode:** start the backend with `TRACKER_STUB_RUNNER=1` to use a scripted stand-in for the agents (useful for trying the UI without spending tokens).

A full run over all 20 sample emails takes about two minutes, about 24 model requests and costs well under one cent (see below).

## Live run from the command line

```bash
.venv/bin/python scripts/live_run.py --out output/my_run.json
```

This calls the model once for the 20 sample emails (same runner as the web app) and writes a run report. Switch cost measures off with `TRACKER_MEASURES_OFF`, e.g. `TRACKER_MEASURES_OFF=prefilter_emails,batch_intake`.

## Scoring a run

`data/gold_answers.json` holds the expected outcome for each of the 20 sample emails.

```bash
.venv/bin/python scripts/score_run.py output/run1_before_fix.json output/run_A_all_measures_on.json
```

It prints precision, recall, F1, exact-match emails and **false actions** (changes that passed every defense but are wrong, so they would be applied if approved). `--run-id <id>` scores a run from `output/runs/`.

| Run | Precision | Recall | Exact | False actions |
|-----|-----------|--------|-------|---------------|
| run1 (before fixes) | 0.857 | 1.000 | 18/20 | 2 (e04 picnic on tutor stipends; e20 event date as due date) |
| A (after fixes, all cost measures on) | 1.000 | 1.000 | 20/20 | 0 |
| B (after fixes, main cost measures off) | 1.000 | 0.833 | 18/20 | 0 (missed e07 and e11 date changes) |

**Answer key update (Stage 2d):** overspend is now flagged, not blocked, so the key expects e10 ($2,850 catering, already paid) to be *proposed* with an OVERSPEND flag that the approver must acknowledge. Scored against the new key: run1 0.857 / 0.923 / 17/20 / 2 false actions; the final run A3 (`output/final_run_A3.json`) 1.000 precision, 0.923 recall, 19/20 exact, 0 false actions (it proposed e09's "complete" status but missed its "100%"). Full numbers: `output/cost_experiment.json`.

## Cost measures

Each can be switched off (`config/settings.py`, `TRACKER_MEASURES_OFF`):

| Flag | What it does |
|------|--------------|
| `prefilter_emails` | skips, before any model call, emails that could never pass: quarantined, sender not on roster, sender's program owns no rows, auto-replies (5 of 20 sample emails) |
| `batch_intake` | 5 emails per Intake run instead of 1 |
| `stable_prompt_prefix` | identical instructions every run so the provider can cache them (off = a per-run line first; this only breaks caching *across* runs) |
| `compact_tool_results` | tools return one program's rows and compact proposals |
| `low_reasoning` | reasoning effort "none" |
| `usage_caps` | shared request / tool-call / token caps (also a safety limit: keep on) |

`scripts/cost_experiment.py` compares runs; the result is in `output/cost_experiment.json`. With the first three off (run B), the same mailbox took 76 requests instead of 24 and cost 29% more ($0.0079 vs $0.0062).

## Reset

Either the **Reset demo data** button in the header, or:

```bash
.venv/bin/python scripts/reset_db.py --confirm
```

This copies `data/tracker.db` over the working copy, verifies the SHA-256 checksum, and clears proposals, nudge drafts, the inbox selection and pasted/imported emails. The audit trail is kept. `scripts/seed_db.py --force` rebuilds `data/tracker.db` from the CSVs in `data/seed/`.

## The sample mailbox (`data/mailbox/`, 20 fictional emails, 2026-10-16 to 10-23)

| Kind | Emails |
|------|--------|
| Clean spend / commitment / progress | e01, e02, e05, e07, e09, e12, e13, e14, e20 |
| Ambiguous (which line? how to split?) | e03, e06 |
| Spend that matches no budget line | e04 |
| Overspend (catering pushes FAM-01 over budget) | e10 |
| Date slip that breaks a dependency (WP-12 → WP-13) | e11 |
| Someone editing another team's rows (TEEN → LIB) | e15 |
| Sender not on the staff roster | e19 |
| Irrelevant (potluck, advert, out-of-office) | e16, e17, e18 |
| **Prompt injection** in a forwarded note (zero budgets, mark everything complete, reveal instructions) | e08 |

The **Adult ESL Pathways** team sent no email at all, so the Chaser drafts a nudge for its lead. The demo "today" is fixed at 2026-10-23 (`config/settings.py`).

## The model rule

Only `gpt-6-luna` may be used. It is named once, in `backend/model.py`. This check fails if any other model name appears anywhere in the project:

```bash
.venv/bin/python scripts/check_models.py
```

## Tests

No test calls the model; they use scratch copies of the data.

```bash
.venv/bin/python -m pytest -q
```

```bash
npm --prefix frontend test
```

```bash
npm --prefix frontend run build
```

## Costs

Prices (`config/pricing.py`, gpt-6-luna, per million tokens): input $0.10, cached input $0.01, cache write $0.125, output $0.50. PydanticAI's `input_tokens` is the API's total input, *including* cached and cache-write tokens, so cost = (input − cached − cache_write) × $0.10 + cached × $0.01 + cache_write × $0.125 + output × $0.50. Each run records these per agent and per email (Run details tab, `output/runs/<run_id>.json`).

## Optional: connect a real inbox (read-only)

Only if you want it. Set `IMAP_HOST`, `IMAP_USER` and `IMAP_APP_PASSWORD` (an app password) in `.env`; `IMAP_PORT` and `IMAP_FOLDER` are optional. The *Connect inbox* panel then appears in the Inbox tab: search by date, sender or subject, tick messages, import them, then process them like any other email.

- SSL only; the folder is opened read-only; every fetch uses `BODY.PEEK` so nothing is marked read.
- Only search and fetch commands are ever sent: nothing is sent, moved, flagged or deleted.
- Credentials are read from the environment when connecting and are never stored, logged or returned by the API.
- Imported emails are untrusted: quarantine, grounding, permission and rules all apply.

Tests use a mocked `imaplib` (`tests/test_stage2.py`).

---

Good Measure is an independent student project, not affiliated with any organization whose visual style inspired its design.
