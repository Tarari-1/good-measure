"""A compact, citable summary of one run (used by scripts/live_run.py and scripts/score_run.py)."""

from __future__ import annotations

from typing import Any

from tracker import proposals


def build_report(rec: dict[str, Any]) -> dict[str, Any]:
    props = proposals.list_all(run_id=rec["run_id"])
    return {
        "run_id": rec["run_id"], "status": rec["status"], "reason": rec.get("reason"), "mode": rec.get("mode"),
        "created_at": rec.get("created_at"), "finished_at": rec.get("finished_at"),
        "measures": rec.get("measures"),
        "email_ids": rec.get("email_ids"),
        "email_flags": [f["email_id"] for f in rec.get("email_flags", [])],
        "proposals": [{k: p.get(k) for k in ("id", "email_id", "tracker", "row_id", "field", "amount", "new_value",
                                             "before", "after", "status", "overspend_flag", "overspend")}
                      | {"blocked_by": [b["defense"] for b in p["blocks"]], "block_reasons": [b["reason"] for b in p["blocks"]],
                         "warnings": [w["type"] for w in p["warnings"]],
                         "checker": (p.get("checker_review") or {}).get("verdict"),
                         "checker_note": (p.get("checker_review") or {}).get("note"),
                         "checker_note_verified": (p.get("checker_review") or {}).get("verified")}
                      for p in props],
        "email_outcomes": [{k: o.get(k) for k in ("email_id", "outcome", "note")} for o in rec.get("email_outcomes", [])],
        "nudges": rec.get("nudge_ids"),
        "digest_headline": (rec.get("digest") or {}).get("headline"),
        "usage": rec.get("usage"),
        "per_email": rec.get("per_email"),
    }
