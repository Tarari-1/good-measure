"""Good Measure web API (FastAPI), all under /api.

Run from the repo root:  .venv/bin/uvicorn backend.main:app --port 8000

Agents reach the trackers only through the MCP server. This API reads trackers
directly (read-only) for the dashboard, and changes them in exactly one place:
POST /api/proposals/{id}/approve, which re-validates and applies one cell change
for a named human. POST /api/reset restores the original data.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi import Path as PathParam
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from backend import approvals, runner
from backend.model import MODEL_NAME
from config import pricing, settings
from config.settings import CAPS
from tracker import audit, chase, db, defenses, imap_source, proposals, store
from tracker.email_source import default_source, save_local_email
from tracker.export import build_workbook

logger = logging.getLogger("good_measure.api")
ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
RUN_ID = r"^[a-f0-9]{12}$"
PROPOSAL_ID = r"^PR-\d{4,6}$"


def _load_reset():
    spec = importlib.util.spec_from_file_location("reset_db", settings.REPO_ROOT / "scripts" / "reset_db.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


reset_db = _load_reset()
db.ensure_working_db()
runner.load_saved()

app = FastAPI(title="Good Measure", description="Every update, for good measure.", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET", "POST", "PUT"],
                   allow_headers=["Content-Type"])
_tasks: set[asyncio.Task] = set()
_lock = asyncio.Lock()  # one write action at a time (start run, approve, reject, reset)


def _fail(code: int, reason: str) -> HTTPException:
    return HTTPException(status_code=code, detail=reason)


# --- request bodies -------------------------------------------------------------------


class SelectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email_ids: list[str] = Field(max_length=100)


class RunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email_ids: list[str] | None = Field(default=None, max_length=100)


class DecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approver: str = Field(max_length=80)
    acknowledged: StrictBool = False  # required (true) to approve an OVERSPEND-flagged change
    reason: str | None = Field(default=None, max_length=300)


class PasteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_name: str = Field(default="", max_length=80)
    from_email: str = Field(max_length=120, pattern=r"^[^@\s<>\"]{1,64}@[^@\s<>\"]{1,60}\.[A-Za-z]{2,24}$")
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=10, max_length=5000)


class ImapSearchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    since: date | None = None
    sender: str | None = Field(default=None, max_length=100)
    subject: str | None = Field(default=None, max_length=100)


class ImapImportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    uids: list[str] = Field(min_length=1, max_length=50)


class ResetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: StrictBool


# --- health ----------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "model": MODEL_NAME, "org": settings.ORG_NAME, "today": settings.DEMO_TODAY,
            "env_source": settings.env_source_label(), "mode": "stub" if runner.STUB else "live",
            "run_in_progress": runner.current_run(), "email_source": default_source().name,
            "tracker_owner": settings.TRACKER_OWNER, "caps": {"max_emails_per_run": CAPS.max_emails_per_run},
            "measures": asdict(settings.measures()), "imap_configured": imap_source.configured(),
            "pricing": pricing.as_dict()}


# --- emails ------------------------------------------------------------------------------


def _selection() -> list[str]:
    rows = store.read_all(store.SELECTION)
    return rows[0]["email_ids"] if rows else []


@app.get("/api/emails")
def list_emails() -> dict[str, Any]:
    src = default_source()
    selected = set(_selection())
    roster = {p["email"]: p for p in db.people()}
    out = []
    for m in src.list_messages():
        person = roster.get(m.from_email)
        out.append({**m.summary(), "selected": m.id in selected, "program": person["program"] if person else None,
                    "origin": "sample" if re.fullmatch(r"e\d+", m.id) else ("pasted" if m.id.startswith("p") else "imported"),
                    "on_roster": person is not None,
                    "flagged": bool(defenses.scan_for_injection(m.subject + "\n" + m.body))})
    return {"emails": out, "selected": sorted(selected), "max_per_run": CAPS.max_emails_per_run}


@app.get("/api/emails/{email_id}")
def get_email(email_id: str = PathParam(pattern=r"^[a-z0-9][a-z0-9\-]{0,40}$")) -> dict[str, Any]:
    msg = default_source().get(email_id)
    if msg is None:
        raise _fail(404, f"No email {email_id}.")
    return {**msg.as_dict(), "flagged_phrases": defenses.scan_for_injection(msg.subject + "\n" + msg.body)}


@app.put("/api/emails/selection")
def set_selection(body: SelectionBody) -> dict[str, Any]:
    known = set(default_source().list_ids())
    ids = [e for e in dict.fromkeys(body.email_ids) if e in known]
    with store.locked(store.SELECTION) as rows:
        rows.clear()
        rows.append({"email_ids": ids, "updated_at": store.now_utc()})
    return {"selected": ids}


@app.post("/api/emails/paste", status_code=202)
async def paste_email(body: PasteBody) -> dict[str, Any]:
    """Store one pasted email (untrusted, like any other) and process it on its own."""
    async with _lock:
        if runner.current_run():
            raise _fail(409, "A run is in progress; wait for it to finish.")
        existing = [i for i in default_source().list_ids() if re.fullmatch(r"p\d{3}", i)]
        email_id = f"p{len(existing) + 1:03d}"
        save_local_email(email_id=email_id, from_name=body.from_name.strip(), from_email=body.from_email.strip().lower(),
                         subject=body.subject.strip(), body=body.body.strip(), date=settings.DEMO_TODAY, origin="pasted")
        audit.event(run_id=None, step="email_pasted", name=email_id)
        try:
            rec = runner.start([email_id])
        except runner.RunRefused as exc:
            raise _fail(exc.code, exc.reason) from None
        task = asyncio.create_task(runner.execute(rec))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
    return {"email_id": email_id, "run_id": rec["run_id"], "status": rec["status"]}


# --- optional read-only IMAP --------------------------------------------------------------


@app.get("/api/imap/status")
def imap_status() -> dict[str, Any]:
    return {"configured": imap_source.configured()}  # never returns host, user or password


def _imap_guard() -> None:
    if not imap_source.configured():
        raise _fail(404, "IMAP is not configured.")


@app.post("/api/imap/search")
async def imap_search(body: ImapSearchBody) -> dict[str, Any]:
    _imap_guard()
    try:
        msgs = await asyncio.to_thread(imap_source.search, body.since.isoformat() if body.since else None,
                                       body.sender, body.subject)
    except imap_source.ImapError as exc:
        raise _fail(502, str(exc)) from None
    return {"messages": msgs, "max": imap_source.MAX_RESULTS}


@app.post("/api/imap/import")
async def imap_import(body: ImapImportBody) -> dict[str, Any]:
    _imap_guard()
    try:
        ids = await asyncio.to_thread(imap_source.import_messages, body.uids)
    except imap_source.ImapError as exc:
        raise _fail(502, str(exc)) from None
    audit.event(run_id=None, step="imap_import", result={"imported": len(ids)})
    return {"imported": ids}


# --- runs ---------------------------------------------------------------------------------


@app.post("/api/runs", status_code=202)
async def start_run(body: RunBody) -> dict[str, Any]:
    async with _lock:
        ids = body.email_ids if body.email_ids is not None else _selection()
        try:
            rec = runner.start(ids)
        except runner.RunRefused as exc:
            raise _fail(exc.code, exc.reason) from None
        task = asyncio.create_task(runner.execute(rec))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
    return {"run_id": rec["run_id"], "status": rec["status"], "email_ids": rec["email_ids"],
            "status_url": f"/api/runs/{rec['run_id']}"}


@app.get("/api/runs")
def list_runs() -> dict[str, Any]:
    return {"runs": [{k: r.get(k) for k in ("run_id", "status", "mode", "created_at", "finished_at", "email_ids",
                                             "reason", "proposals", "usage", "measures")} for r in runner.list_runs()],
            "current": runner.current_run()}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str = PathParam(pattern=RUN_ID)) -> dict[str, Any]:
    rec = runner.RUNS.get(run_id)
    if rec is None:
        raise _fail(404, f"No run {run_id}.")
    return rec


@app.get("/api/runs/{run_id}/events")
def run_events(run_id: str = PathParam(pattern=RUN_ID), after: int = Query(0, ge=0),
               limit: int = Query(300, ge=1, le=1000)) -> dict[str, Any]:
    if run_id not in runner.RUNS:
        raise _fail(404, f"No run {run_id}.")
    events = [e for e in audit.read_all() if e.get("run_id") == run_id]
    page = events[after:after + limit]
    return {"events": [{"seq": after + i + 1, **e} for i, e in enumerate(page)], "next": after + len(page),
            "total": len(events)}


# --- proposals -------------------------------------------------------------------------------


@app.get("/api/proposals")
def list_proposals(status: str | None = Query(None, pattern=r"^(pending|needs_decision|blocked|approved|rejected)$"),
                   run_id: str | None = Query(None, pattern=RUN_ID)) -> dict[str, Any]:
    rows = proposals.list_all(status=status, run_id=run_id)
    src = default_source()
    cache: dict[str, Any] = {}
    for p in rows:
        if p["email_id"] not in cache:
            msg = src.get(p["email_id"])
            cache[p["email_id"]] = msg.as_dict() if msg else None
        e = cache[p["email_id"]]
        p["email"] = {"subject": e["subject"], "from_name": e["from_name"], "from_email": e["from_email"],
                      "date": e["date"], "body": e["body"]} if e else None
        row = db.budget_line(p["row_id"]) if p["tracker"] == "budget" else db.activity(p["row_id"])
        p["row_label"] = (row.get("category") or row.get("activity")) if row else None
    return {"proposals": rows, "defenses": defenses.DEFENSES}


@app.post("/api/proposals/{proposal_id}/approve")
async def approve(body: DecisionBody, proposal_id: str = PathParam(pattern=PROPOSAL_ID)) -> dict[str, Any]:
    async with _lock:
        res = approvals.approve(proposal_id, body.approver, acknowledged=body.acknowledged)
    if not res["ok"]:
        raise HTTPException(status_code=res["code"], detail={"reason": res["reason"], "proposal": res.get("proposal")})
    return res


@app.post("/api/proposals/{proposal_id}/reject")
async def reject(body: DecisionBody, proposal_id: str = PathParam(pattern=PROPOSAL_ID)) -> dict[str, Any]:
    async with _lock:
        res = approvals.reject(proposal_id, body.approver, body.reason)
    if not res["ok"]:
        raise HTTPException(status_code=res["code"], detail={"reason": res["reason"]})
    return res


# --- trackers ---------------------------------------------------------------------------------


@app.get("/api/trackers/budget")
def budget() -> dict[str, Any]:
    changed = db.changed_cells()["budget"]
    lines = db.budget_lines()
    for line in lines:
        line["remaining"] = round(line["annual_budget"] - line["spent_to_date"] - line["committed"], 2)
        line["changed_fields"] = changed.get(line["line_id"], [])
    return {"lines": lines, "programs": db.programs(), "today": settings.DEMO_TODAY}


@app.get("/api/trackers/workplan")
def workplan() -> dict[str, Any]:
    changed = db.changed_cells()["workplan"]
    acts = db.activities()
    for a in acts:
        a["changed_fields"] = changed.get(a["id"], [])
        a["overdue"] = a["due_date"] < settings.DEMO_TODAY and a["status"] != "complete"
    return {"activities": acts, "programs": db.programs(), "today": settings.DEMO_TODAY}


@app.get("/api/trackers/changes")
def changes() -> dict[str, Any]:
    return {"changes": db.change_log()}


@app.get("/api/trackers/export.xlsx")
def export_xlsx() -> Response:
    name = f"bright-futures-trackers-{date.fromisoformat(settings.DEMO_TODAY).isoformat()}.xlsx"
    return Response(build_workbook(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# --- chase and digest ---------------------------------------------------------------------------


@app.get("/api/chase/overdue")
def overdue() -> dict[str, Any]:
    return {"owners": chase.overdue_owners(default_source()), "today": settings.DEMO_TODAY,
            "window_days": settings.REPORTING_WINDOW_DAYS}


@app.get("/api/chase/drafts")
def drafts(run_id: str | None = Query(None, pattern=RUN_ID)) -> dict[str, Any]:
    return {"drafts": chase.nudges(run_id)}


@app.get("/api/digest")
def digest() -> dict[str, Any]:
    return {"metrics": chase.tracker_summary(default_source()), "latest": runner.latest_digest()}


@app.get("/api/pricing")
def get_pricing() -> dict[str, Any]:
    return pricing.as_dict()


# --- safety -----------------------------------------------------------------------------------

DEFENSE_DETAILS = {
    "untrusted_email": "Emails reach agents only inside UNTRUSTED_EMAIL delimiters; an email with instructions aimed "
                       "at the AI is quarantined; any output leaking the agents' instructions is blocked.",
    "grounding": "The quote must be copied from the email, every number and date written must appear in it, and a "
                 "new due date needs the email to say the deadline moves.",
    "permission": "The sender (read from the email, not from the agent) may only change their own program's rows.",
    "rules": "Allowed fields and values only; spend only to a line the email's expense matches. Overspend is "
             "flagged, never blocked: spend over budget is recorded with an OVERSPEND flag, an over-budget "
             "commitment needs a decision, and approving either needs an explicit acknowledgement.",
    "caps": "Only selected emails; max proposals per email and per run; shared request/token caps and timeouts.",
}


@app.get("/api/safety")
def safety() -> dict[str, Any]:
    runs = [r for r in runner.list_runs() if r["status"] not in ("queued", "running")]
    latest = runs[0] if runs else None
    src = default_source()
    out: dict[str, Any] = {"defenses": [{"key": k, "label": defenses.DEFENSES[k], "detail": DEFENSE_DETAILS[k]}
                                        for k in defenses.DEFENSES],
                           "latest_run": None, "blocks": [], "quarantined": [], "skipped": []}
    if latest:
        out["latest_run"] = {k: latest.get(k) for k in ("run_id", "mode", "created_at", "status")}
        for p in proposals.list_all(run_id=latest["run_id"]):
            if p["blocks"]:
                out["blocks"].append({k: p.get(k) for k in ("id", "email_id", "row_id", "field", "amount", "new_value",
                                                             "status", "blocks", "sender")})
        for f in latest.get("email_flags", []):
            msg = src.get(f["email_id"])
            out["quarantined"].append({**f, "email": msg.as_dict() if msg else None})
        out["skipped"] = [o for o in latest.get("email_outcomes", []) if str(o.get("outcome", "")).startswith("skipped_")]
    return out


_selftest_lock = asyncio.Lock()


@app.post("/api/safety/selftest")
async def selftest() -> dict[str, Any]:
    """Run the deterministic defense tests (tests/test_defenses.py). No model is called; the tests
    use scratch copies of the data (tests/conftest.py)."""
    if _selftest_lock.locked():
        raise _fail(409, "The self-test is already running.")
    async with _selftest_lock:
        with tempfile.TemporaryDirectory() as tmp:
            xml = Path(tmp) / "result.xml"
            env = {k: v for k, v in os.environ.items() if k != "PORTKEY_API_KEY" and not k.startswith("IMAP_")}
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={xml}",
                "tests/test_defenses.py", cwd=str(settings.REPO_ROOT), env=env,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            try:
                await asyncio.wait_for(proc.wait(), timeout=120)
            except TimeoutError:
                proc.kill()
                raise _fail(504, "The self-test took too long.") from None
            if not xml.exists():
                raise _fail(500, "The self-test did not produce results.")
            root = ET.parse(xml).getroot()
    tests = []
    for case in root.iter("testcase"):
        failed = case.find("failure") is not None or case.find("error") is not None
        tests.append({"name": case.get("name"), "passed": not failed, "seconds": float(case.get("time") or 0)})
    passed = sum(t["passed"] for t in tests)
    audit.event(run_id=None, step="safety_selftest", result={"passed": passed, "total": len(tests)})
    return {"passed": passed, "failed": len(tests) - passed, "total": len(tests), "tests": tests,
            "model_calls": 0}


# --- reset ------------------------------------------------------------------------------------


@app.post("/api/reset")
async def reset(body: ResetBody) -> dict[str, Any]:
    if body.confirm is not True:
        raise _fail(400, 'Send {"confirm": true} to reset.')
    async with _lock:
        if runner.current_run():
            raise _fail(409, "A run is in progress; reset after it finishes.")
        return reset_db.reset_database(source="api")
