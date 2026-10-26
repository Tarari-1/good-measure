"""Who needs chasing, saving nudge drafts, and the numbers behind the weekly digest.

"Has reported" means: sent at least one email in the reporting window (the
REPORTING_WINDOW_DAYS before DEMO_TODAY). An owner is overdue if their whole
program sent nothing in the window, or they own an activity that is past due and
not complete and they sent nothing themselves. Nudges are drafts only, and may
only be addressed to an overdue owner (so an email cannot steer a nudge elsewhere).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from config import settings
from tracker import db, defenses, store
from tracker.email_source import EmailSource


def _window_start() -> str:
    return (date.fromisoformat(settings.DEMO_TODAY) - timedelta(days=settings.REPORTING_WINDOW_DAYS)).isoformat()


def overdue_owners(source: EmailSource) -> list[dict[str, Any]]:
    start, today = _window_start(), settings.DEMO_TODAY
    recent = [m for m in source.list_messages() if start <= m.date <= today]
    senders = {m.from_email.lower() for m in recent}
    last_seen: dict[str, str] = {}
    for m in recent:
        last_seen[m.from_email.lower()] = max(last_seen.get(m.from_email.lower(), ""), m.date)
    people = db.people()
    by_name = {p["name"]: p for p in people}
    programs = {p["code"]: p for p in db.programs()}
    team_reported = {code: any(p["email"] in senders for p in people if p["program"] == code) for code in programs}
    out: list[dict[str, Any]] = []
    for person in people:
        if person["program"] not in programs:
            continue
        reasons: list[str] = []
        is_lead = programs[person["program"]]["lead_email"] == person["email"]
        if is_lead and not team_reported[person["program"]]:
            reasons.append(f"No update from anyone on {programs[person['program']]['name']} since {start}.")
        late = [a for a in db.activities(person["program"])
                if by_name.get(a["owner"], {}).get("email") == person["email"]
                and a["due_date"] < today and a["status"] != "complete"]
        if late and person["email"] not in senders:
            reasons += [f"{a['id']} {a['activity']} was due {a['due_date']} ({a['percent_complete']}% done)." for a in late]
        if reasons:
            out.append({"name": person["name"], "email": person["email"], "program": person["program"],
                        "program_name": programs[person["program"]]["name"], "role": person["role"],
                        "team_reported": team_reported[person["program"]],
                        "last_email": last_seen.get(person["email"]),
                        "overdue_activities": [{"id": a["id"], "activity": a["activity"], "due_date": a["due_date"],
                                                "percent_complete": a["percent_complete"], "status": a["status"]}
                                               for a in late],
                        "reasons": reasons})
    return out


def save_nudge(*, run_id: str, recipient_email: str, subject: str, body: str, source: EmailSource) -> dict[str, Any]:
    """Store a nudge DRAFT. Refused (with a reason) rather than saved if it breaks a rule."""
    recipient_email = (recipient_email or "").strip().lower()
    subject, body = (subject or "").strip(), (body or "").strip()
    allowed = {o["email"]: o for o in overdue_owners(source)}
    if recipient_email not in allowed:
        return {"ok": False, "reason": f"{recipient_email or 'That address'} is not an overdue owner; "
                                       "nudges may only go to people on the overdue list."}
    if not (3 <= len(subject) <= 140) or not (20 <= len(body) <= 2000):
        return {"ok": False, "reason": "Subject must be 3-140 characters and body 20-2000 characters."}
    if defenses.leaks_instructions(subject, body):
        return {"ok": False, "reason": "Draft contains the agents' private instructions; not saved."}
    with store.locked(store.NUDGES) as records:
        if sum(1 for r in records if r.get("run_id") == run_id) >= settings.CAPS.max_nudges_per_run:
            return {"ok": False, "reason": f"Per-run cap of {settings.CAPS.max_nudges_per_run} nudges reached."}
        if any(r.get("run_id") == run_id and r["recipient_email"] == recipient_email for r in records):
            return {"ok": False, "reason": f"A nudge to {recipient_email} was already drafted in this run."}
        owner = allowed[recipient_email]
        draft = {"id": store.next_id(records, "NG"), "run_id": run_id, "recipient_name": owner["name"],
                 "recipient_email": recipient_email, "program": owner["program"], "subject": subject, "body": body,
                 "reasons": owner["reasons"], "status": "draft", "sent": False, "created_at": store.now_utc()}
        records.append(draft)
    return {"ok": True, "draft_id": draft["id"], "note": "Saved as a draft only; nothing was sent."}


def nudges(run_id: str | None = None) -> list[dict[str, Any]]:
    rows = store.read_all(store.NUDGES)
    return [r for r in rows if r.get("run_id") == run_id] if run_id else rows


def tracker_summary(source: EmailSource) -> dict[str, Any]:
    """Burn vs plan per program, at-risk milestones and late owners (deterministic)."""
    start = date.fromisoformat(settings.FISCAL_YEAR_START)
    end = date.fromisoformat(settings.FISCAL_YEAR_END)
    today = date.fromisoformat(settings.DEMO_TODAY)
    plan_pct = round(100 * (today - start).days / ((end - start).days + 1), 1)
    programs = []
    for prog in db.programs():
        lines = db.budget_lines(prog["code"])
        budget = sum(l["annual_budget"] for l in lines)
        spent = sum(l["spent_to_date"] for l in lines)
        committed = sum(l["committed"] for l in lines)
        burn = round(100 * spent / budget, 1) if budget else 0.0
        hot = [l["line_id"] for l in lines if l["spent_to_date"] + l["committed"] > 0.9 * l["annual_budget"]]
        programs.append({"program": prog["code"], "name": prog["name"], "annual_budget": budget,
                         "spent_to_date": spent, "committed": committed, "burn_pct": burn,
                         "committed_pct": round(100 * (spent + committed) / budget, 1) if budget else 0.0,
                         "plan_pct": plan_pct, "variance_pts": round(burn - plan_pct, 1),
                         "lines_over_90pct": hot})
    horizon = (today + timedelta(days=21)).isoformat()
    at_risk = []
    for a in db.activities():
        if a["status"] == "complete":
            continue
        if a["due_date"] < settings.DEMO_TODAY:
            at_risk.append({**a, "risk": "overdue"})
        elif a["status"] in ("at_risk", "blocked"):
            at_risk.append({**a, "risk": a["status"]})
        elif a["due_date"] <= horizon and a["percent_complete"] < 50:
            at_risk.append({**a, "risk": "due within 3 weeks, under 50% done"})
    pending = [p for p in store.read_all(store.PROPOSALS) if p.get("status") == "pending"]
    return {"today": settings.DEMO_TODAY, "fiscal_year": [settings.FISCAL_YEAR_START, settings.FISCAL_YEAR_END],
            "plan_pct": plan_pct, "programs": programs,
            "totals": {k: sum(p[k] for p in programs) for k in ("annual_budget", "spent_to_date", "committed")},
            "at_risk": at_risk, "late_owners": overdue_owners(source),
            "pending_proposals": len(pending)}
