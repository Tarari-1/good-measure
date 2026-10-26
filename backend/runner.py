"""One processing run: selected emails in, proposals + nudge drafts + a digest out.

Run records live in memory while the server runs and are saved to
output/runs/<run_id>.json when a run ends (token counts per agent, estimated cost,
email outcomes, blocks by defense, digest). Only one run at a time.

TRACKER_STUB_RUNNER=1 swaps the agent team for a deterministic stand-in that calls
the same propose/draft functions directly. It never calls the model; tests and UI
work use it so real model calls stay rare.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from collections import Counter
from typing import Any

from dataclasses import asdict

from config import pricing, settings
from config.settings import CAPS
from tracker import audit, chase, defenses, prefilter, proposals
from tracker.email_source import EmailSource, default_source

logger = logging.getLogger("good_measure.runner")
STUB = os.environ.get("TRACKER_STUB_RUNNER") == "1"

RUNS: dict[str, dict[str, Any]] = {}
_current: str | None = None


class RunRefused(Exception):
    def __init__(self, code: int, reason: str):
        super().__init__(reason)
        self.code, self.reason = code, reason


def current_run() -> str | None:
    return _current


def validate_selection(email_ids: list[str], source: EmailSource) -> list[str]:
    ids = list(dict.fromkeys(e.strip() for e in email_ids if isinstance(e, str) and e.strip()))
    if not ids:
        raise RunRefused(422, "Select at least one email.")
    if len(ids) > CAPS.max_emails_per_run:
        raise RunRefused(422, f"At most {CAPS.max_emails_per_run} emails per run (you selected {len(ids)}).")
    known = set(source.list_ids())
    unknown = [e for e in ids if e not in known]
    if unknown:
        raise RunRefused(422, f"Unknown email id(s): {', '.join(unknown)}")
    order = {e: i for i, e in enumerate(source.list_ids())}
    return sorted(ids, key=order.__getitem__)


def start(email_ids: list[str], source: EmailSource | None = None) -> dict[str, Any]:
    """Create a run record and schedule it. Raises RunRefused (409 if a run is active)."""
    global _current
    source = source or default_source()
    if _current is not None:
        raise RunRefused(409, f"Run {_current} is still in progress; wait for it to finish.")
    ids = validate_selection(email_ids, source)
    run_id = uuid.uuid4().hex[:12]
    rec = {"run_id": run_id, "status": "queued", "mode": "stub" if STUB else "live", "email_ids": ids,
           "created_at": audit.now_iso(), "finished_at": None, "reason": None, "history": []}
    RUNS[run_id] = rec
    _current = run_id
    return rec


def _set(rec: dict[str, Any], status: str, **extra: Any) -> None:
    rec.update(status=status, **extra)
    rec["history"].append({"status": status, "at": audit.now_iso()})


def _flag_emails(rec: dict[str, Any], source: EmailSource) -> None:
    """Defense 1, before any model sees anything: record emails that carry injected instructions."""
    flags = []
    for eid in rec["email_ids"]:
        msg = source.get(eid)
        hits = defenses.scan_for_injection(f"{msg.subject}\n{msg.body}") if msg else []
        if hits:
            flags.append({"email_id": eid, "defense": "untrusted_email",
                          "reason": "Contains instructions aimed at the AI; quarantined (nothing from it can be applied "
                                    "automatically).", "phrases": hits[:4]})
            audit.event(run_id=rec["run_id"], step="email_quarantined", name=eid,
                        result={"defense": "untrusted_email", "phrases": len(hits)})
    rec["email_flags"] = flags


def _usage_block(per_agent: dict[str, dict[str, int]]) -> dict[str, Any]:
    rows = {}
    for name in ("coordinator", "intake", "checker", "chaser"):
        u = {**dict.fromkeys(USAGE_KEYS, 0), **(per_agent.get(name) or {})}
        rows[name] = {**u, "cost_usd": _cost(u)}
    total = {k: sum(r[k] for r in rows.values()) for k in USAGE_KEYS}
    total["cost_usd"] = round(sum(r["cost_usd"] for r in rows.values()), 8)
    return {"per_agent": rows, "total": total, "pricing": pricing.as_dict(),
            "caps": {"request_limit": CAPS.request_limit, "tool_calls_limit": CAPS.tool_calls_limit,
                     "total_tokens_limit": CAPS.total_tokens_limit, "run_timeout_s": CAPS.run_timeout_s}}


USAGE_KEYS = ("requests", "tool_calls", "input_tokens", "cached_input_tokens", "cache_write_tokens", "output_tokens")


def _cost(u: dict[str, Any]) -> float:
    return pricing.cost_usd(u.get("input_tokens", 0), u.get("cached_input_tokens", 0), u.get("output_tokens", 0),
                            u.get("cache_write_tokens", 0))


def per_email_usage(email_ids: list[str], batches: list[dict[str, Any]], per_agent: dict[str, Any]) -> dict[str, Any]:
    """Intake tokens per email (a batch's tokens split evenly over its emails), plus the run-level
    overhead (Coordinator, Checker, Chaser) that is not tied to one email."""
    rows = {e: {**dict.fromkeys(USAGE_KEYS, 0.0), "processed_by_model": False} for e in email_ids}
    for b in batches:
        n = len(b["email_ids"]) or 1
        for e in b["email_ids"]:
            row = rows.setdefault(e, {**dict.fromkeys(USAGE_KEYS, 0.0), "processed_by_model": False})
            row["processed_by_model"] = True
            for k in USAGE_KEYS:
                row[k] += b["usage"].get(k, 0) / n
    for row in rows.values():
        row["cost_usd"] = _cost(row)
        for k in USAGE_KEYS:
            row[k] = round(row[k], 1)
    overhead = {k: sum((per_agent.get(a) or {}).get(k, 0) for a in ("coordinator", "checker", "chaser"))
                for k in USAGE_KEYS}
    overhead["cost_usd"] = _cost(overhead)
    return {"emails": rows, "run_overhead": overhead,
            "method": "Intake tokens of each batch split evenly over the emails in it; skipped emails cost 0."}


def _proposal_summary(run_id: str) -> dict[str, Any]:
    rows = proposals.list_all(run_id=run_id)
    by_def = Counter(b["defense"] for p in rows if p["status"] == "blocked" for b in p["blocks"])
    return {"total": len(rows), "by_status": dict(Counter(p["status"] for p in rows)),
            "blocked_by_defense": dict(by_def), "ids": [p["id"] for p in rows]}


def _prefilter(rec: dict[str, Any], source: EmailSource) -> tuple[list[str], list[dict[str, Any]]]:
    if not settings.measures().prefilter_emails:
        return list(rec["email_ids"]), []
    msgs = [m for m in (source.get(e) for e in rec["email_ids"]) if m is not None]
    keep, skipped = prefilter.split(msgs)
    for sk in skipped:
        audit.event(run_id=rec["run_id"], step="email_skipped", name=sk["email_id"], result={"outcome": sk["outcome"]})
    return keep, skipped


async def _live(rec: dict[str, Any], source: EmailSource) -> dict[str, Any]:
    from backend.agents import run_team  # imported lazily: needs the model only for live runs

    keep, skipped = _prefilter(rec, source)
    out, state, _usage = await run_team(rec["run_id"], rec["email_ids"], intake_ids=keep)
    outcomes = skipped + [o for r in state.intake_reports for o in r.get("emails", [])]
    return {"status": out["status"], "digest": out["output"], "email_outcomes": outcomes,
            "checker": state.checker_report, "chaser": state.chaser_report, "per_agent": state.per_agent,
            "intake_batches": state.intake_batches, "stopped": state.stopped}


async def _stub(rec: dict[str, Any], source: EmailSource) -> dict[str, Any]:
    """Deterministic stand-in (no model): a few hard-coded intake decisions on the sample mailbox."""
    plays = {
        "e01": ("budget", "READ-02", "spent_to_date", 1240.50, "we paid Little Owl Books $1,240.50 today"),
        "e05": ("budget", "LIB-01", "committed", 3200, "It is $3,200, committed but not paid yet"),
        "e10": ("budget", "FAM-01", "spent_to_date", 2850, "came in at $2,850 and I paid it on Friday"),
        "e11": ("workplan", "WP-12", "due_date", "2026-12-05", "the venue booking (WP-12) slips to 2026-12-05"),
        "e14": ("workplan", "WP-16", "percent_complete", "60", "the fall workshop series (WP-16) is now 60% complete"),
        "e15": ("budget", "LIB-06", "spent_to_date", 500, "Also log $500 spent on LIB-06 for the pop-up events"),
    }
    keep, outcomes = _prefilter(rec, source)
    sel = set(rec["email_ids"])
    for eid in keep:
        await asyncio.sleep(0.05)
        if eid in plays:
            tracker, row, field, value, quote = plays[eid]
            kw = {"amount": value} if tracker == "budget" else {"new_value": value}
            p = proposals.create(tracker=tracker, run_id=rec["run_id"], email_id=eid, row_id=row, field=field,
                                 quote=quote, rationale="stub runner", source=source, selected_ids=sel, **kw)
            outcomes.append({"email_id": eid, "outcome": "proposed", "proposal_ids": [p["id"]], "note": "stub"})
        else:
            outcomes.append({"email_id": eid, "outcome": "not_a_tracker_update", "proposal_ids": [],
                             "note": "stub runner skips this email"})
    for owner in chase.overdue_owners(source):
        chase.save_nudge(run_id=rec["run_id"], recipient_email=owner["email"],
                         subject=f"Quick update for {owner['program_name']}?",
                         body=f"Hi {owner['name'].split()[0]}, " + " ".join(owner["reasons"]) +
                              " Could you send a two-line update? Thanks, Jordan Ellery, Operations", source=source)
    s = chase.tracker_summary(source)
    digest = {"headline": "STUB digest (no model was called).",
              "burn_vs_plan": [{"program": p["program"], "burn_pct": p["burn_pct"], "plan_pct": p["plan_pct"],
                                "comment": "stub"} for p in s["programs"]],
              "at_risk_milestones": [f"{a['id']} {a['activity']}: {a['risk']}" for a in s["at_risk"]],
              "late_owners": [f"{o['name']} ({o['program']})" for o in s["late_owners"]],
              "proposals_summary": "stub", "decisions_for_tracker_owner": []}
    return {"status": "ok", "digest": digest, "email_outcomes": outcomes, "checker": None, "chaser": None,
            "per_agent": {}, "intake_batches": [], "stopped": None}


async def execute(rec: dict[str, Any], source: EmailSource | None = None) -> None:
    global _current
    source = source or default_source()
    try:
        _set(rec, "running")
        audit.event(run_id=rec["run_id"], step="run_start", arguments={"emails": len(rec["email_ids"]),
                                                                       "mode": rec["mode"]})
        rec["measures"] = asdict(settings.measures())
        _flag_emails(rec, source)
        async with asyncio.timeout(CAPS.run_timeout_s):
            res = await (_stub(rec, source) if STUB else _live(rec, source))
        rec.update(digest=res["digest"], email_outcomes=res["email_outcomes"], checker=res["checker"],
                   chaser=res["chaser"], usage=_usage_block(res["per_agent"]),
                   per_email=per_email_usage(rec["email_ids"], res["intake_batches"], res["per_agent"]))
        if res["status"] == "ok":
            _set(rec, "finished")
        else:
            _set(rec, "stopped", reason=res["status"].removeprefix("stopped: "))
    except TimeoutError:
        _set(rec, "stopped", reason=f"{CAPS.run_timeout_s:.0f}s run timeout")
    except Exception as exc:  # noqa: BLE001
        logger.warning("run %s failed: %s", rec["run_id"], type(exc).__name__)
        _set(rec, "error", reason=f"The run failed unexpectedly ({type(exc).__name__}).")
    finally:
        rec.setdefault("usage", _usage_block({}))
        rec["proposals"] = _proposal_summary(rec["run_id"])
        rec["nudge_ids"] = [n["id"] for n in chase.nudges(rec["run_id"])]
        rec["finished_at"] = audit.now_iso()
        audit.event(run_id=rec["run_id"], step="run_end", result={"status": rec["status"],
                                                                  "proposals": rec["proposals"]["total"]},
                    usage=rec["usage"]["total"])
        save(rec)
        _current = None


def save(rec: dict[str, Any]) -> None:
    settings.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = settings.RUNS_DIR / f"{rec['run_id']}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(audit.redact(rec), indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


def load_saved() -> None:
    """Load earlier run records from output/runs/ (so history survives a restart)."""
    if not settings.RUNS_DIR.exists():
        return
    for path in settings.RUNS_DIR.glob("*.json"):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
            if rec.get("usage", {}).get("per_agent"):  # re-price with the current config/pricing.py
                rec["usage"] = _usage_block(rec["usage"]["per_agent"])
            RUNS.setdefault(rec["run_id"], rec)
        except (json.JSONDecodeError, KeyError, OSError):
            continue


def list_runs() -> list[dict[str, Any]]:
    return sorted(RUNS.values(), key=lambda r: r["created_at"], reverse=True)


def latest_digest() -> dict[str, Any] | None:
    for r in list_runs():
        if r.get("digest"):
            return {"run_id": r["run_id"], "created_at": r["created_at"], "mode": r.get("mode"), "digest": r["digest"]}
    return None
