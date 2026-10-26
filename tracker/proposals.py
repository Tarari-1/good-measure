"""Creating and re-validating proposed tracker changes.

A proposal is one cell change: (tracker, row, field, before -> after), the email
it came from, the supporting quote, and the result of every defense. It is stored
in data/proposals.json with status "pending" (waiting for a human), "needs_decision"
(an over-budget commitment, flagged OVERSPEND) or "blocked" (a defense stopped it, with
the reasons). Spend that goes over budget is "pending" with an OVERSPEND flag. Nothing here writes to a tracker: only
backend/approvals.py does, after a named human approves and evaluate() passes again.

The sender is always read from the email itself, never taken from an agent, so an
agent cannot claim an email came from someone else.
"""

from __future__ import annotations

from typing import Any

from tracker import db, defenses, store
from tracker.email_source import EmailSource


def _email_or_none(source: EmailSource, email_id: str) -> dict[str, Any] | None:
    msg = source.get(email_id)
    return msg.as_dict() if msg else None


def evaluate(p: dict[str, Any], source: EmailSource) -> dict[str, Any]:
    """Run defenses 1-4 for a proposal against the CURRENT tracker data.

    Returns {"blocks", "warnings", "before", "after", "program", "value"}.
    """
    email = _email_or_none(source, p["email_id"])
    if email is None:
        return {"blocks": [defenses.block("grounding", f"Email {p['email_id']} does not exist.")],
                "warnings": [], "before": None, "after": None, "program": None, "value": None, "overspend": None}
    blocks = defenses.check_untrusted(email, p.get("quote"), p.get("rationale"),
                                      p.get("new_value") if p["field"] == "notes" else None)
    sender = db.person_by_email(email["from_email"])
    if p["tracker"] == "budget":
        line = db.budget_line(p["row_id"])
        rule_blocks, warnings, change = defenses.check_budget_rules(
            line, p["field"], p.get("amount"), bool(p.get("overspend_flag")), email, p["row_id"])
        program = line["program"] if line else None
        values = {"amount": p.get("amount")}
        value = change.get("after")
    else:
        acts = db.activities()
        act = next((a for a in acts if a["id"] == p["row_id"]), None)
        rule_blocks, warnings, change, value = defenses.check_activity_rules(
            act, p["field"], p.get("new_value"), acts, p["row_id"])
        program = act["program"] if act else None
        values = {p["field"]: value} if p["field"] in ("percent_complete", "due_date", "notes") else {}
    blocks += defenses.check_grounding(email, p.get("quote") or "", values)
    if program is not None:
        blocks += defenses.check_permission(email["from_email"], sender, program, p["row_id"])
    blocks += rule_blocks
    return {"blocks": blocks, "warnings": warnings, "before": change.get("before"), "after": change.get("after"),
            "program": program, "value": value, "sender": email["from_email"], "overspend": change.get("overspend"),
            "sender_name": sender["name"] if sender else email["from_name"]}


def create(*, tracker: str, run_id: str, email_id: str, row_id: str, field: str, quote: str, rationale: str,
           source: EmailSource, selected_ids: set[str] | None, amount: float | None = None,
           new_value: Any = None, overspend_flag: bool = False, proposed_by: str = "intake") -> dict[str, Any]:
    """Validate and store one proposal (status pending or blocked). Never touches the trackers."""
    p: dict[str, Any] = {
        "tracker": tracker, "run_id": run_id, "email_id": email_id, "row_id": str(row_id).strip().upper(),
        "field": str(field).strip(), "quote": (quote or "").strip()[:600], "rationale": (rationale or "").strip()[:600],
        "amount": amount, "new_value": new_value, "overspend_flag": bool(overspend_flag), "proposed_by": proposed_by,
    }
    with store.locked(store.PROPOSALS) as records:
        this_run = [r for r in records if r.get("run_id") == run_id]
        cap_blocks = defenses.check_caps(email_id, selected_ids, len(this_run),
                                         sum(1 for r in this_run if r.get("email_id") == email_id))
        result = evaluate(p, source)
        blocks = cap_blocks + result["blocks"]
        overspend = None if blocks else result["overspend"]
        if blocks:
            status = "blocked"
        elif overspend and overspend["kind"] == "commitment":
            status = "needs_decision"  # an over-budget commitment is a choice, not a fact: held for a decision
        else:
            status = "pending"  # includes recorded spend over budget (flagged, never blocked)
        p.update(
            id=store.next_id(records, "PR"),
            program=result["program"], sender=result.get("sender"), sender_name=result.get("sender_name"),
            before=result["before"], after=result["after"], overspend=overspend, overspend_flag=bool(overspend),
            status=status, blocks=blocks, warnings=result["warnings"],
            checker_review=None, created_at=store.now_utc(), decided_by=None, decided_at=None,
        )
        if tracker == "workplan" and result["value"] is not None:
            p["new_value"] = result["value"]
        records.append(p)
    return p


def list_all(status: str | None = None, run_id: str | None = None) -> list[dict[str, Any]]:
    rows = store.read_all(store.PROPOSALS)
    if status:
        rows = [r for r in rows if r.get("status") == status]
    if run_id:
        rows = [r for r in rows if r.get("run_id") == run_id]
    return rows


def compact(p: dict[str, Any]) -> dict[str, Any]:
    """What an agent sees about a proposal (no quote text, to keep tokens down)."""
    return {k: p.get(k) for k in ("id", "status", "tracker", "email_id", "row_id", "field", "amount", "new_value",
                                  "before", "after", "overspend_flag", "overspend", "blocks", "warnings", "sender")}


def attach_reviews(reviews: list[dict[str, Any]], run_id: str | None = None) -> dict[str, int]:
    """Store the Checker agent's notes on this run's proposals. Notes never change a status.

    Each note is checked in code (defenses.check_review_note); a note that cites an id not in
    its proposal, or a concern that does not name the row, is stored as verified=False.
    """
    by_id = {r["proposal_id"]: r for r in reviews}
    n = unverified = 0
    with store.locked(store.PROPOSALS) as records:
        for r in records:
            if r["id"] in by_id and (run_id is None or r.get("run_id") == run_id):
                rev = by_id[r["id"]]
                problems = defenses.check_review_note(rev, r)
                r["checker_review"] = {"verdict": rev.get("verdict"), "note": rev.get("note"),
                                       "verified": not problems, "problems": problems}
                n += 1
                unverified += bool(problems)
    return {"attached": n, "unverified": unverified}
