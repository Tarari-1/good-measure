"""Typed outputs for the four agents, and the per-run state they share."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

AgentName = Literal["coordinator", "intake", "checker", "chaser"]
AGENT_NAMES: tuple[AgentName, ...] = ("coordinator", "intake", "checker", "chaser")


# --- Intake ----------------------------------------------------------------------------


class EmailOutcome(BaseModel):
    email_id: str
    outcome: Literal["proposed", "needs_clarification", "no_matching_row", "not_a_tracker_update", "suspicious"]
    proposal_ids: list[str] = Field(default_factory=list, description="Ids returned by propose_* tools for this email.")
    note: str = Field(description="One sentence: what the email says, or why nothing was proposed.")


class IntakeReport(BaseModel):
    emails: list[EmailOutcome]


# --- Checker -------------------------------------------------------------------------


class ProposalReview(BaseModel):
    proposal_id: str
    verdict: Literal["looks_right", "concern"]
    note: str = Field(description="One sentence. For a concern, say what the approver should check.")


class CheckerReport(BaseModel):
    reviews: list[ProposalReview]
    summary: str = Field(description="Two sentences at most.")


# --- Chaser --------------------------------------------------------------------------


class NudgeOutcome(BaseModel):
    recipient_email: str
    draft_id: str | None = Field(description="Id from save_nudge_draft, or null if it was refused.")
    reason_chased: str


class ChaserReport(BaseModel):
    nudges: list[NudgeOutcome]
    summary: str


# --- Coordinator (weekly digest) -----------------------------------------------------


class ProgramLine(BaseModel):
    program: str
    burn_pct: float
    plan_pct: float
    comment: str = Field(description="One short sentence.")


class WeeklyDigest(BaseModel):
    headline: str = Field(description="One sentence summary of the week.")
    burn_vs_plan: list[ProgramLine]
    at_risk_milestones: list[str] = Field(description="'<id> <activity>: why it is at risk' items.")
    late_owners: list[str] = Field(description="'<name> (<program>): what is missing' items.")
    proposals_summary: str = Field(description="How many changes were proposed, how many were blocked and why.")
    decisions_for_tracker_owner: list[str] = Field(description="What the human approver should look at first.")


# --- shared run state --------------------------------------------------------------


@dataclass
class RunState:
    """Shared by every agent run inside one top-level run (one budget, one run id)."""

    run_id: str
    selected_ids: list[str]
    intake_ids: list[str] = field(default_factory=list)
    delegations: int = 0
    delegation_signatures: set[str] = field(default_factory=set)
    stopped: str | None = None
    per_agent: dict[str, dict[str, int]] = field(default_factory=dict)
    intake_reports: list[dict] = field(default_factory=list)
    intake_batches: list[dict] = field(default_factory=list)  # per Intake run: emails + token usage
    checker_report: dict | None = None
    chaser_report: dict | None = None


@dataclass
class AgentDeps:
    agent: AgentName
    state: RunState
    seen_tool_calls: set[str] = field(default_factory=set)
