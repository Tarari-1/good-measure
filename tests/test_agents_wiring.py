"""The whole agent pipeline with a scripted FunctionModel instead of the real model.

Checks the wiring, not intelligence: the Coordinator is the only agent with
delegate tools, each agent sees only its MCP tools, proposals flow through the real
MCP server and defenses, per-agent usage is recorded, and loop protection refuses a
second delegation to the same agent.
"""

from __future__ import annotations

import asyncio

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

from backend import agents
from tracker import chase, proposals

SEEN_TOOLS: dict[str, set[str]] = {}


def _returns(messages: list[ModelMessage]) -> list[ToolReturnPart]:
    return [p for m in messages for p in getattr(m, "parts", []) if isinstance(p, ToolReturnPart)]


def scripted(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    tools = {t.name for t in info.function_tools}
    out = info.output_tools[0].name
    done = {r.tool_name for r in _returns(messages)}
    usage = RequestUsage(input_tokens=100, cache_read_tokens=40, output_tokens=10)

    def call(name, **args):
        return ModelResponse(parts=[ToolCallPart(name, args)], usage=usage)

    if "delegate_to_intake" in tools:  # coordinator
        SEEN_TOOLS["coordinator"] = tools
        for step in ("delegate_to_intake", "delegate_to_checker", "delegate_to_chaser"):
            if step not in done:
                return call(step)
        if sum(1 for r in _returns(messages) if r.tool_name == "delegate_to_intake") < 2:
            return call("delegate_to_intake")  # a second time: must be refused (loop protection)
        return call(out, headline="h", burn_vs_plan=[], at_risk_milestones=[], late_owners=[],
                    proposals_summary="p", decisions_for_tracker_owner=[])
    if "propose_budget_change" in tools:  # intake
        SEEN_TOOLS["intake"] = tools
        if "read_email" not in done:
            return call("read_email", email_id="e13")
        if "propose_budget_change" not in done:
            return call("propose_budget_change", email_id="e13", line_id="TEEN-02", field="spent_to_date",
                        amount=780, quote="I paid the print deposit for the student chapbook today: $780",
                        rationale="deposit paid")
        return call(out, emails=[{"email_id": "e13", "outcome": "proposed", "proposal_ids": ["PR-0001"], "note": "n"}])
    if "save_nudge_draft" in tools:  # chaser
        SEEN_TOOLS["chaser"] = tools
        if "save_nudge_draft" not in done:
            return call("save_nudge_draft", recipient_email="hana.velasquez-moore@brightfutures.example",
                        subject="Adult ESL update?", body="Hi Hana, could you send a two-line update this week?")
        return call(out, nudges=[], summary="s")
    SEEN_TOOLS["checker"] = tools
    if "list_proposals" not in done:
        return call("list_proposals")
    retried = any(getattr(p, "part_kind", "") == "retry-prompt" for m in messages for p in getattr(m, "parts", []))
    if not retried:  # first answer cites the wrong line: the code check must send it back once
        return call(out, reviews=[{"proposal_id": "PR-0001", "verdict": "concern", "note": "Belongs on READ-02."}],
                    summary="s")
    return call(out, reviews=[{"proposal_id": "PR-0001", "verdict": "concern",
                               "note": "TEEN-02 deposit matches the email."}], summary="s")


def test_pipeline_with_scripted_model():
    out, state, usage = asyncio.run(agents.run_team("abcdef123456", ["e13", "e14"], model=FunctionModel(scripted)))
    assert out["status"] == "ok", out
    # tool scopes
    assert {t for t in SEEN_TOOLS["coordinator"] if t.startswith("delegate_to_")} == {
        "delegate_to_intake", "delegate_to_checker", "delegate_to_chaser"}
    for name in ("intake", "checker", "chaser"):
        assert not any(t.startswith("delegate_to_") for t in SEEN_TOOLS[name])
        assert SEEN_TOOLS[name] <= agents.TOOL_SCOPES[name] | {"final_result"}
    assert "propose_budget_change" not in SEEN_TOOLS["checker"]
    # effects went through MCP + defenses
    props = proposals.list_all(run_id="abcdef123456")
    assert len(props) == 1 and props[0]["status"] == "pending"
    review = props[0]["checker_review"]
    assert review["verdict"] == "concern" and review["verified"] is True  # corrected after one code-check retry
    assert len(chase.nudges("abcdef123456")) == 1
    # usage per agent and shared
    assert state.per_agent["intake"]["input_tokens"] > 0 and state.per_agent["intake"]["cached_input_tokens"] > 0
    assert set(state.per_agent) == {"coordinator", "intake", "checker", "chaser"}
    assert usage.requests == sum(a["requests"] for a in state.per_agent.values())
    assert state.delegations == 3  # the second delegate_to_intake was refused


def test_intake_claim_without_proposal_is_caught():
    from backend.agents import Team
    from backend.schemas import RunState

    st = RunState(run_id="claimcheck01", selected_ids=["e11", "e07"])
    out = Team._verify_claims(st, [{"email_id": "e11", "outcome": "proposed", "proposal_ids": ["PR-9999"], "note": "n"}],
                              ["e11", "e07"])
    assert out[0]["outcome"] == "claimed_without_proposal" and out[0]["proposal_ids"] == []
    assert out[1] == {"email_id": "e07", "outcome": "not_processed", "proposal_ids": [],
                      "note": "Intake's report did not cover this email."}
