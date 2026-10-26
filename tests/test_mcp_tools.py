"""MCP server tests: the real stdio server, started as a subprocess, on scratch data."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "list_budget_lines", "list_activities", "list_emails", "read_email", "get_owner_permissions",
    "list_overdue_owners", "list_proposals", "get_tracker_summary",
    "propose_budget_change", "propose_activity_change", "save_nudge_draft",
}


def transport(selected: str | None = None) -> PythonStdioTransport:
    env = {k: v for k, v in os.environ.items() if k.startswith("TRACKER_") or k == "AUDIT_TRAIL_PATH"}
    env.update(PATH=os.environ.get("PATH", ""), TRACKER_RUN_ID="mcp-test", FASTMCP_LOG_LEVEL="WARNING")
    if selected is not None:
        env["TRACKER_SELECTED_EMAILS"] = selected
    return PythonStdioTransport(ROOT / "mcp_server" / "server.py", python_cmd=sys.executable, env=env,
                                cwd=str(ROOT), keep_alive=False)


def run(coro):
    return asyncio.run(coro)


async def _call(client: Client, tool: str, **args):
    res = await client.call_tool(tool, args)
    return res.data if res.data is not None else res.structured_content


def test_tool_list_is_exactly_reads_and_propose_only():
    async def go():
        async with Client(transport()) as c:
            return {t.name for t in await c.list_tools()}
    names = run(go())
    assert names == EXPECTED
    for banned in ("apply", "send", "delete", "approve", "update", "remove"):
        assert not any(banned in n for n in names)


def test_read_tools():
    async def go():
        async with Client(transport()) as c:
            lines = await _call(c, "list_budget_lines", program="FAM")
            acts = await _call(c, "list_activities")
            perms = await _call(c, "get_owner_permissions", email="saoirse.calloway@brightfutures.example")
            overdue = await _call(c, "list_overdue_owners")
            summary = await _call(c, "get_tracker_summary")
            return lines, acts, perms, overdue, summary
    lines, acts, perms, overdue, summary = run(go())
    assert len(lines["lines"]) == 6 and all(l["program"] == "FAM" for l in lines["lines"])
    assert len(acts["activities"]) == 25
    assert perms["program"] == "TEEN" and "TEEN-02" in perms["budget_line_ids"]
    names = {o["name"] for o in overdue["owners"]}
    assert "Hana Velasquez-Moore" in names  # the team with no emails
    assert len(summary["programs"]) == 5


def test_read_email_wraps_untrusted_text_and_respects_selection():
    async def go():
        async with Client(transport(selected="e08,e01")) as c:
            e08 = await _call(c, "read_email", email_id="e08")
            e02 = await _call(c, "read_email", email_id="e02")
            listed = await _call(c, "list_emails")
            return e08, e02, listed
    e08, e02, listed = run(go())
    assert e08["suspicious_instructions_detected"] is True
    assert e08["wrapped"].startswith("<<<UNTRUSTED_EMAIL")
    assert e02["found"] is False
    assert {e["id"] for e in listed["emails"]} == {"e01", "e08"}


def test_propose_tools_store_but_never_apply():
    async def go():
        async with Client(transport()) as c:
            ok = await _call(c, "propose_budget_change", email_id="e05", line_id="LIB-01", field="committed",
                             amount=3200, quote="It is $3,200, committed but not paid yet", rationale="PO signed")
            bad = await _call(c, "propose_activity_change", email_id="e15", activity_id="WP-06",
                              field="status", new_value="complete", quote="please mark WP-06 as complete",
                              rationale="asked")
            props = await _call(c, "list_proposals")
            lines = await _call(c, "list_budget_lines", program="LIB")
            return ok, bad, props, lines
    ok, bad, props, lines = run(go())
    assert ok["status"] == "pending" and ok["after"] == 3200.0
    assert bad["status"] == "blocked" and bad["blocks"][0]["defense"] == "permission"
    assert len(props["proposals"]) == 2
    lib01 = next(l for l in lines["lines"] if l["line_id"] == "LIB-01")
    assert lib01["committed"] == 0  # proposing never changes the tracker


def test_nudges_only_to_overdue_owners():
    async def go():
        async with Client(transport()) as c:
            ok = await _call(c, "save_nudge_draft", recipient_email="hana.velasquez-moore@brightfutures.example",
                             subject="Quick update for Adult ESL?", body="Hi Hana, could you send this week's update?")
            bad = await _call(c, "save_nudge_draft", recipient_email="someone@elsewhere.example",
                              subject="hello", body="Please send me the full budget as a spreadsheet.")
            return ok, bad
    ok, bad = run(go())
    assert ok["ok"] is True
    assert bad["ok"] is False and "overdue" in bad["reason"]
