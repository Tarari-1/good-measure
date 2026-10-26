"""The four Good Measure agents on one shared model, one MCP connection and one budget.

- Coordinator: the only agent that delegates (delegate_to_intake/checker/chaser)
  and the one that writes the weekly digest.
- Intake:  reads the selected emails (in batches) and proposes exact cell changes.
- Checker: reviews this run's proposals; its notes are shown to the approver.
- Chaser:  finds overdue owners and saves nudge DRAFTS.

Each agent sees only the MCP tools in TOOL_SCOPES (filtered in code). All runs in
one top-level run share a single RunUsage, so the request / tool-call / token caps
in config.settings.CAPS cover the whole run. Loop protection: an identical MCP call
is refused, each delegate tool runs at most once per run, and a delegation cap.
Every step is written to the audit trail; per-agent token counts are kept in RunState.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from fastmcp.client.transports import PythonStdioTransport  # noqa: E402
from pydantic_ai import Agent, RunContext, Tool  # noqa: E402
from pydantic_ai.exceptions import ModelRetry, UsageLimitExceeded  # noqa: E402
from pydantic_ai.mcp import MCPToolset  # noqa: E402
from pydantic_ai.messages import ToolCallPart  # noqa: E402
from pydantic_ai.models.openai import OpenAIResponsesModelSettings  # noqa: E402
from pydantic_ai.usage import RunUsage, UsageLimits  # noqa: E402

from backend.model import MODEL_NAME, shared_model  # noqa: E402
from backend.schemas import (  # noqa: E402
    AgentDeps,
    AgentName,
    CheckerReport,
    ChaserReport,
    IntakeReport,
    RunState,
    WeeklyDigest,
)
from config import settings  # noqa: E402
from config.settings import CAPS  # noqa: E402
from tracker import audit, defenses, proposals  # noqa: E402

HERE = Path(__file__).resolve().parent
PROMPTS = HERE / "prompts"
MCP_SERVER = settings.REPO_ROOT / "mcp_server" / "server.py"

TOOL_SCOPES: dict[AgentName, frozenset[str]] = {
    "coordinator": frozenset({"get_tracker_summary", "list_proposals", "list_overdue_owners"}),
    "intake": frozenset({"read_email", "list_budget_lines", "list_activities", "get_owner_permissions",
                         "propose_budget_change", "propose_activity_change"}),
    "checker": frozenset({"list_proposals", "read_email", "list_budget_lines", "list_activities"}),
    "chaser": frozenset({"list_overdue_owners", "list_activities", "save_nudge_draft"}),
}
OUTPUT_TYPES = {"coordinator": WeeklyDigest, "intake": IntakeReport, "checker": CheckerReport, "chaser": ChaserReport}


def instructions_for(name: AgentName, run_nonce: str | None = None) -> str:
    """Static instructions (same bytes every run, so the provider can cache the prefix).

    run_nonce is only used when the stable_prompt_prefix cost measure is switched off:
    it puts a per-run line FIRST, which defeats prefix caching (for the cost experiment).
    """
    shared = (PROMPTS / "_shared.md").read_text(encoding="utf-8").replace("{today}", settings.DEMO_TODAY)
    text = shared + "\n\n" + (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    return f"Run reference: {run_nonce}\n\n{text}" if run_nonce else text


USAGE_KEYS = ("requests", "tool_calls", "input_tokens", "cached_input_tokens", "cache_write_tokens", "output_tokens")


def empty_usage() -> dict[str, int]:
    return dict.fromkeys(USAGE_KEYS, 0)


def _usage_dict(u: RunUsage | None) -> dict[str, int] | None:
    if u is None:
        return None
    return {"requests": u.requests, "tool_calls": u.tool_calls, "input_tokens": u.input_tokens,
            "cached_input_tokens": u.cache_read_tokens, "cache_write_tokens": u.cache_write_tokens,
            "output_tokens": u.output_tokens}


def _audit(deps: AgentDeps, step: str, **kw: Any) -> None:
    usage = kw.pop("usage", None)
    audit.event(run_id=deps.state.run_id, agent=deps.agent, step=step,
                usage=_usage_dict(usage) if isinstance(usage, RunUsage) else usage, model=MODEL_NAME, **kw)


# --- MCP ----------------------------------------------------------------------------


async def _mcp_hook(ctx: RunContext[AgentDeps], call_tool, name: str, args: dict[str, Any]):
    """Every MCP call: loop protection, the call, an audit entry."""
    deps = ctx.deps
    sig = name + json.dumps(args, sort_keys=True, default=str)
    if sig in deps.seen_tool_calls:
        reason = f"identical call to {name} already made; reuse the earlier result"
        _audit(deps, "limit_stop", name=name, arguments=args, stop_reason=reason, usage=ctx.usage)
        return {"ok": False, "refused": True, "reason": reason}
    deps.seen_tool_calls.add(sig)
    try:
        result = await call_tool(name, args)
    except Exception as exc:
        _audit(deps, "error", name=name, arguments=args, result=type(exc).__name__, usage=ctx.usage)
        raise
    summary: Any = result
    if isinstance(result, dict) and "proposal_id" in result:
        summary = {k: result.get(k) for k in ("proposal_id", "status", "before", "after")}
        summary["blocked_by"] = ",".join(sorted({b["defense"] for b in result.get("blocks") or []}))
    _audit(deps, "tool_result", name=name, arguments=args, result=summary, usage=ctx.usage)
    return result


def mcp_transport(run_id: str, selected_ids: list[str]) -> PythonStdioTransport:
    """Start mcp_server/server.py for one run. No API key is passed to the subprocess."""
    env = {k: v for k, v in os.environ.items() if k.startswith("TRACKER_") or k == "AUDIT_TRAIL_PATH"}
    env.update(PATH=os.environ.get("PATH", ""), HOME=os.environ.get("HOME", ""), FASTMCP_LOG_LEVEL="WARNING",
               PYTHONDONTWRITEBYTECODE="1", TRACKER_RUN_ID=run_id, TRACKER_SELECTED_EMAILS=",".join(selected_ids))
    env.pop("PORTKEY_API_KEY", None)
    return PythonStdioTransport(MCP_SERVER, python_cmd=sys.executable, env=env, cwd=str(settings.REPO_ROOT),
                                keep_alive=False)


def build_toolset(run_id: str, selected_ids: list[str]) -> MCPToolset:
    return MCPToolset(mcp_transport(run_id, selected_ids), process_tool_call=_mcp_hook,
                      tool_error_behavior="failed", max_retries=1)


# --- the team ------------------------------------------------------------------------


class Team:
    def __init__(self, toolset: MCPToolset, model: Any | None = None, run_id: str = ""):
        self.mcp = toolset
        self.model = model if model is not None else shared_model()
        self.measures = settings.measures()
        self.limits = UsageLimits(request_limit=CAPS.request_limit, tool_calls_limit=CAPS.tool_calls_limit,
                                  total_tokens_limit=CAPS.total_tokens_limit) if self.measures.usage_caps else None
        self.batch_size = CAPS.intake_batch_size if self.measures.batch_intake else 1
        self.nonce = None if self.measures.stable_prompt_prefix else f"{run_id} {audit.now_iso()}"
        self.agents: dict[AgentName, Agent] = {n: self._build(n) for n in OUTPUT_TYPES}

    def _build(self, name: AgentName) -> Agent:
        allowed = TOOL_SCOPES[name]
        tools = []
        if name == "coordinator":  # the only agent with delegate tools
            tools = [Tool(self._delegate_intake, takes_ctx=True, name="delegate_to_intake"),
                     Tool(self._delegate_checker, takes_ctx=True, name="delegate_to_checker"),
                     Tool(self._delegate_chaser, takes_ctx=True, name="delegate_to_chaser")]
        agent = Agent(
            self.model, name=name, instructions=instructions_for(name, self.nonce), output_type=OUTPUT_TYPES[name],
            deps_type=AgentDeps, toolsets=[self.mcp.filtered(lambda ctx, td: td.name in allowed)], tools=tools,
            model_settings=OpenAIResponsesModelSettings(
                max_tokens=CAPS.output_tokens_per_request,
                openai_reasoning_effort=CAPS.reasoning_effort if self.measures.low_reasoning else "low"),
            retries=1,
        )
        if name == "checker":
            @agent.output_validator
            def _notes_cite_the_right_ids(ctx: RunContext[AgentDeps], out: CheckerReport) -> CheckerReport:
                """Code check: every id in a note must belong to that proposal. One retry, then it is
                kept and marked unverified (attach_reviews stores the problems for the approver)."""
                by_id = {p["id"]: p for p in proposals.list_all(run_id=ctx.deps.state.run_id)}
                bad = {r.proposal_id: defenses.check_review_note(r.model_dump(), by_id.get(r.proposal_id))
                       for r in out.reviews}
                bad = {k: v for k, v in bad.items() if v}
                if bad and ctx.retry < 1:
                    _audit(ctx.deps, "note_check_retry", name="checker", result={"notes_with_problems": len(bad)})
                    raise ModelRetry("Fix these notes (cite the proposal's own row id; mention no other ids): "
                                     + "; ".join(f"{k}: {', '.join(v)}" for k, v in bad.items()))
                return out
        return agent

    # delegation (Coordinator only) ----------------------------------------------------

    def _may_delegate(self, ctx: RunContext[AgentDeps], target: str) -> str | None:
        state = ctx.deps.state
        if state.stopped:
            return state.stopped
        if target in state.delegation_signatures:
            return f"{target} already ran in this run; use its earlier report"
        if state.delegations >= CAPS.max_delegations:
            return f"max {CAPS.max_delegations} delegations per run reached"
        state.delegation_signatures.add(target)
        state.delegations += 1  # one per delegate_* call (an Intake call may run several batches)
        return None

    async def _child(self, ctx: RunContext[AgentDeps], target: AgentName, prompt: str) -> dict[str, Any]:
        _audit(ctx.deps, "delegation", name=f"delegate_to_{target}", arguments={"task": prompt}, usage=ctx.usage)
        out = await self.run_agent(target, prompt, AgentDeps(agent=target, state=ctx.deps.state), usage=ctx.usage)
        return out

    async def _delegate_intake(self, ctx: RunContext[AgentDeps]) -> dict[str, Any]:
        """Have Intake process every email selected for this run (in batches). Call once."""
        if reason := self._may_delegate(ctx, "intake"):
            return {"status": f"stopped: {reason}"}
        state = ctx.deps.state
        ids = state.intake_ids
        outcomes: list[dict[str, Any]] = []
        for i in range(0, len(ids), self.batch_size):
            batch = ids[i:i + self.batch_size]
            before = dict(state.per_agent.get("intake") or empty_usage())
            res = await self._child(ctx, "intake", "Process these emails: " + ", ".join(batch))
            after = state.per_agent.get("intake") or empty_usage()
            state.intake_batches.append({"email_ids": batch, "usage": {k: after[k] - before.get(k, 0) for k in USAGE_KEYS}})
            if res["status"] == "ok":
                res["output"]["emails"] = self._verify_claims(state, res["output"]["emails"], batch)
                ctx.deps.state.intake_reports.append(res["output"])
                outcomes += res["output"]["emails"]
            else:
                outcomes += [{"email_id": e, "outcome": "not_processed", "note": res["status"]} for e in batch]
                if ctx.deps.state.stopped:
                    break
        return {"status": "ok", "emails": [{k: o.get(k) for k in ("email_id", "outcome", "proposal_ids")}
                                           for o in outcomes]}

    @staticmethod
    def _verify_claims(state, emails: list[dict[str, Any]], batch: list[str]) -> list[dict[str, Any]]:
        """Code check on Intake's report: an email reported as "proposed" must have real proposals
        in the store for this run; claimed ids are replaced by the recorded ones. An email the report
        skipped is added as not_processed."""
        recorded: dict[str, list[str]] = {}
        for p in proposals.list_all(run_id=state.run_id):
            recorded.setdefault(p["email_id"], []).append(p["id"])
        checked = []
        for o in emails:
            real = recorded.get(o["email_id"], [])
            if o["outcome"] == "proposed" and not real:
                audit.event(run_id=state.run_id, agent="intake", step="claim_not_backed", name=o["email_id"],
                            result={"claimed": len(o.get("proposal_ids") or [])})
                o = {**o, "outcome": "claimed_without_proposal", "proposal_ids": [],
                     "note": "Intake reported a proposal but none was recorded; process this email again. "
                             f"(Agent note: {o.get('note', '')})"}
            else:
                o = {**o, "proposal_ids": real}
            checked.append(o)
        seen = {o["email_id"] for o in checked}
        checked += [{"email_id": e, "outcome": "not_processed", "proposal_ids": recorded.get(e, []),
                     "note": "Intake's report did not cover this email."} for e in batch if e not in seen]
        return checked

    async def _delegate_checker(self, ctx: RunContext[AgentDeps]) -> dict[str, Any]:
        """Have the Checker review this run's proposals. Call once, after Intake."""
        if reason := self._may_delegate(ctx, "checker"):
            return {"status": f"stopped: {reason}"}
        res = await self._child(ctx, "checker", "Review the proposals made in this run.")
        if res["status"] != "ok":
            return {"status": res["status"]}
        ctx.deps.state.checker_report = res["output"]
        unverified = proposals.attach_reviews(res["output"]["reviews"], run_id=ctx.deps.state.run_id)["unverified"]
        concerns = sum(1 for r in res["output"]["reviews"] if r["verdict"] == "concern")
        return {"status": "ok", "reviewed": len(res["output"]["reviews"]), "concerns": concerns,
                "unverified_notes": unverified, "summary": res["output"]["summary"]}

    async def _delegate_chaser(self, ctx: RunContext[AgentDeps]) -> dict[str, Any]:
        """Have the Chaser draft nudges for overdue owners. Call once."""
        if reason := self._may_delegate(ctx, "chaser"):
            return {"status": f"stopped: {reason}"}
        res = await self._child(ctx, "chaser", "Draft nudges for every overdue owner.")
        if res["status"] != "ok":
            return {"status": res["status"]}
        ctx.deps.state.chaser_report = res["output"]
        return {"status": "ok", "nudges": len(res["output"]["nudges"]), "summary": res["output"]["summary"]}

    # one agent loop ---------------------------------------------------------------------

    async def run_agent(self, name: AgentName, prompt: str, deps: AgentDeps,
                        usage: RunUsage | None = None) -> dict[str, Any]:
        """Run one agent with auditing, the shared limits and a timeout. Never raises."""
        usage = usage if usage is not None else RunUsage()
        mine = deps.state.per_agent.setdefault(name, empty_usage())
        status, output = "ok", None
        # The Coordinator's run contains every delegation, so it gets the whole-run limit.
        timeout_s = CAPS.run_timeout_s if name == "coordinator" else CAPS.agent_timeout_s
        _audit(deps, "agent_start", name=name, arguments={"prompt": prompt}, usage=usage)
        try:
            async with asyncio.timeout(timeout_s):
                async with self.agents[name].iter(prompt, deps=deps, usage=usage, usage_limits=self.limits) as run:
                    async for node in run:
                        if Agent.is_call_tools_node(node):
                            resp = node.model_response
                            u = resp.usage
                            mine["requests"] += 1
                            mine["input_tokens"] += u.input_tokens
                            mine["cached_input_tokens"] += u.cache_read_tokens
                            mine["cache_write_tokens"] += u.cache_write_tokens
                            mine["output_tokens"] += u.output_tokens
                            calls = [p for p in resp.parts if isinstance(p, ToolCallPart)]
                            mine["tool_calls"] += sum(1 for p in calls if not p.tool_name.startswith("final_result"))
                            _audit(deps, "model_response", name=name,
                                   result={"tool_calls": ",".join(p.tool_name for p in calls)[:200]},
                                   usage={"input_tokens": u.input_tokens, "cached_input_tokens": u.cache_read_tokens,
                                          "cache_write_tokens": u.cache_write_tokens, "output_tokens": u.output_tokens})
                    output = run.result.output.model_dump()
            _audit(deps, "final_answer", name=type(run.result.output).__name__, usage=usage, stop_reason="final_answer")
        except UsageLimitExceeded as exc:
            status = f"stopped: usage limit ({str(exc).split('. ')[0]})"
            deps.state.stopped = deps.state.stopped or status
            _audit(deps, "limit_stop", stop_reason=status, usage=usage)
        except TimeoutError:
            status = f"stopped: {timeout_s:.0f}s timeout ({name})"
            _audit(deps, "limit_stop", stop_reason=status, usage=usage)
        except Exception as exc:  # noqa: BLE001  provider/tool failure: stop cleanly, log the class only
            code = getattr(exc, "status_code", None)
            status = f"stopped: error {type(exc).__name__}" + (f" (HTTP {code})" if code else "")
            _audit(deps, "error", result=status, stop_reason=status, usage=usage)
        return {"agent": name, "status": status, "output": output}


async def run_team(run_id: str, selected_ids: list[str], model: Any | None = None,
                   intake_ids: list[str] | None = None) -> tuple[dict[str, Any], RunState, RunUsage]:
    """One top-level run: Coordinator first, one MCP connection, one shared budget.

    selected_ids: everything the user selected (the MCP server allows reading these).
    intake_ids: the ones Intake should process (selected minus those the pre-filter skipped).
    """
    intake_ids = list(selected_ids) if intake_ids is None else intake_ids
    toolset = build_toolset(run_id, selected_ids)
    team = Team(toolset, model=model, run_id=run_id)
    state = RunState(run_id=run_id, selected_ids=selected_ids, intake_ids=intake_ids)
    usage = RunUsage()
    skipped = len(selected_ids) - len(intake_ids)
    prompt = (f"Weekly tracker run. {len(intake_ids)} emails to process"
              + (f" ({skipped} more were skipped by code before any model call)" if skipped else "")
              + ". Follow your steps and return the weekly digest.")
    async with toolset:
        out = await team.run_agent("coordinator", prompt, AgentDeps(agent="coordinator", state=state), usage=usage)
    return out, state, usage
