"""The human approval path: the ONLY code that writes to a tracker.

It is a plain backend function behind POST /api/proposals/{id}/approve (approver
name typed in the UI). It is NOT an MCP tool and no agent can reach it.

Approving re-runs every defense against the current tracker data, so a proposal
that was fine an hour ago but would now overspend (because another change landed
first) is refused and marked blocked, with the reason.
"""

from __future__ import annotations

import re
from typing import Any

from tracker import audit, db, proposals, store
from tracker.email_source import EmailSource, default_source

# A person's name: 2 to 60 characters, starting with a letter.
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{1,59}$")


def _clean_name(name: str) -> str | None:
    name = " ".join((name or "").split())
    return name if NAME_RE.match(name) else None


def approve(proposal_id: str, approver: str, source: EmailSource | None = None) -> dict[str, Any]:
    source = source or default_source()
    who = _clean_name(approver)
    if who is None:
        return {"ok": False, "code": 422, "reason": "Type your name (letters, spaces, . ' -) to approve."}
    with store.locked(store.PROPOSALS) as records:
        p = next((r for r in records if r["id"] == proposal_id), None)
        if p is None:
            return {"ok": False, "code": 404, "reason": f"No proposal {proposal_id}."}
        if p["status"] != "pending":
            return {"ok": False, "code": 409, "reason": f"{proposal_id} is {p['status']}, not pending."}
        check = proposals.evaluate(p, source)
        if check["blocks"]:
            p.update(status="blocked", blocks=p["blocks"] + [{**b, "reason": "At approval: " + b["reason"]}
                                                            for b in check["blocks"]],
                     decided_at=store.now_utc())
            audit.event(run_id=p["run_id"], step="approval_blocked", name=proposal_id,
                        arguments={"approver": who}, result={"blocks": len(check["blocks"])},
                        blocks=check["blocks"])
            return {"ok": False, "code": 409, "reason": "Re-validation failed; the proposal is now blocked.",
                    "proposal": dict(p)}
        new_value = check["after"]
        if p["tracker"] == "budget":
            new_value = round(float(new_value), 2)
        applied = db.apply_change(tracker=p["tracker"], row_id=p["row_id"], field=p["field"],
                                  expected_old=check["before"], new_value=new_value, proposal_id=proposal_id,
                                  approved_by=who, applied_at=store.now_utc())
        if not applied["ok"]:
            return {"ok": False, "code": 409, "reason": applied["reason"]}
        p.update(status="approved", decided_by=who, decided_at=store.now_utc(), before=check["before"],
                 after=new_value, warnings=check["warnings"])
        result = dict(p)
    audit.event(run_id=p["run_id"], step="approved_and_applied", name=proposal_id,
                arguments={"approver": who, "row_id": p["row_id"], "field": p["field"]},
                result={"before": check["before"], "after": new_value})
    return {"ok": True, "proposal": result}


def reject(proposal_id: str, approver: str, reason: str | None = None) -> dict[str, Any]:
    who = _clean_name(approver)
    if who is None:
        return {"ok": False, "code": 422, "reason": "Type your name (letters, spaces, . ' -) to reject."}
    with store.locked(store.PROPOSALS) as records:
        p = next((r for r in records if r["id"] == proposal_id), None)
        if p is None:
            return {"ok": False, "code": 404, "reason": f"No proposal {proposal_id}."}
        if p["status"] not in ("pending", "blocked"):
            return {"ok": False, "code": 409, "reason": f"{proposal_id} is {p['status']}; it cannot be rejected."}
        p.update(status="rejected", decided_by=who, decided_at=store.now_utc(),
                 rejection_reason=(reason or "").strip()[:300] or None)
        result = dict(p)
    audit.event(run_id=p["run_id"], step="rejected", name=proposal_id, arguments={"approver": who})
    return {"ok": True, "proposal": result}
