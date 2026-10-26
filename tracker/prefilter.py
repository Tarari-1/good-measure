"""Deterministic pre-filter: emails that cannot lead to a valid tracker change are
skipped before any model sees them (cost measure "prefilter_emails").

Skipped, with a recorded reason:
  quarantined      contains instructions aimed at an AI (defense 1); anything proposed from it would be blocked
  not_on_roster    sender is not on the staff roster; the permission defense would block any change
  no_tracker_rows  sender's program owns no budget lines or activities (e.g. Operations)
  auto_reply       automatic replies / out-of-office messages

Every skip is safe: the defenses would block any proposal from these emails anyway,
so skipping only saves tokens. It never lets something through.
"""

from __future__ import annotations

import re
from typing import Any

from tracker import db, defenses
from tracker.email_source import EmailMessage

_AUTO_REPLY = re.compile(r"^\s*(automatic reply|auto-?reply|out of (the )?office|autoreply)\b", re.I)

REASONS = {
    "quarantined": "Contains instructions aimed at the AI; quarantined before any model call.",
    "not_on_roster": "Sender is not on the staff roster, so no tracker change could be accepted.",
    "no_tracker_rows": "Sender's program owns no tracker rows.",
    "auto_reply": "Automatic reply; not a tracker update.",
}


def classify(msg: EmailMessage) -> str | None:
    """The skip reason key for one email, or None if it should go to Intake."""
    if defenses.scan_for_injection(f"{msg.subject}\n{msg.body}"):
        return "quarantined"
    if _AUTO_REPLY.search(msg.subject):
        return "auto_reply"
    person = db.person_by_email(msg.from_email)
    if person is None:
        return "not_on_roster"
    if not db.budget_lines(person["program"]) and not db.activities(person["program"]):
        return "no_tracker_rows"
    return None


def split(messages: list[EmailMessage]) -> tuple[list[str], list[dict[str, Any]]]:
    """(ids to process, skipped [{email_id, skip, note}])."""
    keep, skipped = [], []
    for m in messages:
        reason = classify(m)
        if reason is None:
            keep.append(m.id)
        else:
            skipped.append({"email_id": m.id, "outcome": f"skipped_{reason}", "proposal_ids": [],
                            "note": REASONS[reason]})
    return keep, skipped
