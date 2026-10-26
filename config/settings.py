"""All project settings in one place: paths, the demo date, per-run caps, .env lookup.

.env lookup order (first file found wins, nothing else is searched):
  1. <repo>/.env
  2. <repo>/../.env   (the folder one level above the repo)
Only PORTKEY_API_KEY is required. The key is never printed or logged; callers only
ever learn *which* file was used.

Every path can be overridden by an environment variable so tests can point the
whole app at scratch copies (TRACKER_ORIGINAL_DB, TRACKER_DB, TRACKER_STATE_DIR,
TRACKER_MAILBOX_DIR, AUDIT_TRAIL_PATH, TRACKER_RUNS_DIR).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]


def env_candidates(repo_root: Path = REPO_ROOT) -> list[Path]:
    return [repo_root / ".env", repo_root.parent / ".env"]


def find_env_file(repo_root: Path = REPO_ROOT) -> Path | None:
    """The .env file that will be used, or None if neither location has one."""
    for candidate in env_candidates(repo_root):
        if candidate.is_file():
            return candidate
    return None


def load_env(repo_root: Path = REPO_ROOT) -> Path | None:
    """Load the first .env found (repo, then one folder up). Existing env vars win."""
    path = find_env_file(repo_root)
    if path is not None:
        load_dotenv(path, override=False)
    return path


ENV_FILE = load_env()


def env_source_label(path: Path | None = ENV_FILE, repo_root: Path = REPO_ROOT) -> str:
    """Where the key came from, in words safe to show in the UI (never the key)."""
    if path is None:
        return "environment" if os.getenv("PORTKEY_API_KEY") else "missing"
    return "repo/.env" if path.parent == repo_root else "../.env (one folder up)"


def _path(var: str, default: Path) -> Path:
    return Path(os.environ.get(var) or default).resolve()


# --- data locations ------------------------------------------------------------------
ORIGINAL_DB = _path("TRACKER_ORIGINAL_DB", REPO_ROOT / "data" / "tracker.db")
WORKING_DB = _path("TRACKER_DB", REPO_ROOT / "data" / "tracker_working.db")
STATE_DIR = _path("TRACKER_STATE_DIR", REPO_ROOT / "data")  # proposals.json, nudges.json, selection.json
MAILBOX_DIR = _path("TRACKER_MAILBOX_DIR", REPO_ROOT / "data" / "mailbox")
LOCAL_MAIL_DIR = STATE_DIR / "local_mail"  # pasted and IMAP-imported emails (untrusted, cleared by reset)
SEED_DIR = REPO_ROOT / "data" / "seed"
OUTPUT_DIR = REPO_ROOT / "output"
AUDIT_TRAIL_PATH = _path("AUDIT_TRAIL_PATH", OUTPUT_DIR / "audit_trail.json")
RUNS_DIR = _path("TRACKER_RUNS_DIR", OUTPUT_DIR / "runs")

# --- the demo world ----------------------------------------------------------------
ORG_NAME = "Bright Futures Literacy Network"  # fictional
DEMO_TODAY = "2026-10-23"  # fixed "today" for every date calculation
FISCAL_YEAR_START = "2026-07-01"
FISCAL_YEAR_END = "2027-06-30"
REPORTING_WINDOW_DAYS = 7  # a team "has reported" if it emailed within this many days of DEMO_TODAY
TRACKER_OWNER = "Jordan Ellery (Operations Manager)"  # fictional; the human who approves changes


# --- per-run caps (deterministic defense 5) ---------------------------------------
@dataclass(frozen=True)
class RunCaps:
    max_emails_per_run: int = 25
    intake_batch_size: int = 5  # emails handed to one Intake run
    max_proposals_per_run: int = 40
    max_proposals_per_email: int = 4
    max_nudges_per_run: int = 8
    request_limit: int = 80  # model requests per run, shared by all four agents
    tool_calls_limit: int = 220  # tool calls per run, shared
    total_tokens_limit: int = 700_000  # input + output tokens per run, shared
    output_tokens_per_request: int = 4_000
    reasoning_effort: str = "none"
    agent_timeout_s: float = 300.0  # wall clock for one agent run
    run_timeout_s: float = 900.0  # wall clock for the whole run
    max_delegations: int = 12  # delegate_* calls per run (loop protection)


CAPS = RunCaps()


# --- cost-saving measures (each can be switched off for experiments) ------------------
@dataclass(frozen=True)
class CostMeasures:
    prefilter_emails: bool = True  # skip quarantined / off-roster / no-rows / auto-reply emails before any model call
    batch_intake: bool = True  # several emails per Intake run (off: one Intake run per email)
    stable_prompt_prefix: bool = True  # identical instructions every run, so the provider can cache them
    compact_tool_results: bool = True  # tools return one program's rows / compact proposals (off: everything)
    low_reasoning: bool = True  # reasoning effort "none" (off: "low")
    usage_caps: bool = True  # shared request/tool-call/token limits (a safety limit too; keep on)


MEASURE_NAMES = tuple(CostMeasures.__dataclass_fields__)


def measures() -> CostMeasures:
    """Read at call time. TRACKER_MEASURES_OFF="prefilter_emails,batch_intake" switches measures off."""
    off = {m.strip() for m in os.environ.get("TRACKER_MEASURES_OFF", "").split(",") if m.strip()}
    unknown = off - set(MEASURE_NAMES)
    if unknown:
        raise ValueError(f"Unknown cost measure(s) in TRACKER_MEASURES_OFF: {', '.join(sorted(unknown))}")
    return CostMeasures(**{m: m not in off for m in MEASURE_NAMES})
