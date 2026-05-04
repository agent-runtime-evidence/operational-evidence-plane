"""Scenario registry for committed Operational Evidence Plane examples."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_STATE_REF = "demo/state/code_review_agent.sqlite"


@dataclass(frozen=True)
class ScenarioArtifacts:
    name: str
    manifest: str
    event: str
    permission: str
    trace: str
    eval_result: str
    reconstruction: str
    policy_input: str
    expected_reconstruction_status: str
    expected_event_type: str
    expected_event_outcome_status: str
    expected_permission_allow: bool
    expected_trace_status: str
    expected_replay_status: str
    expected_eval_status: str
    expected_permission_evidence_status: str
    expected_trace_evidence_status: str
    expected_replay_state_evidence_status: str
    expected_eval_evidence_status: str
    expected_replay_state_ref: str
    expected_blocking_loss_fields: tuple[str, ...] = ()
    requires_sqlite_state: bool = False

    def path(self, relative_path: str) -> Path:
        path = Path(relative_path)
        if path.is_absolute():
            return path
        return REPO_ROOT / path

    @property
    def dtr_files(self) -> dict[str, str]:
        return {
            "release_manifest": self.manifest,
            "agent_step": self.event,
            "permission": self.permission,
            "trace_bundle": self.trace,
            "eval_result": self.eval_result,
        }


SCENARIOS: dict[str, ScenarioArtifacts] = {
    "code_review_agent": ScenarioArtifacts(
        name="code_review_agent",
        manifest="manifest/examples/code_review_agent_release.v0.json",
        event="events/examples/code_review_agent_step.v0.json",
        permission="permissions/examples/code_review_tool_permission.v0.json",
        trace="traces/examples/code_review_agent_trace.v0.json",
        eval_result="traces/examples/code_review_agent_eval.v0.json",
        reconstruction="playbooks/examples/code_review_reconstruction_packet.v0.json",
        policy_input="permissions/policy/input/code_review_read_diff.json",
        expected_reconstruction_status="ready",
        expected_event_type="agent_step.completed",
        expected_event_outcome_status="succeeded",
        expected_permission_allow=True,
        expected_trace_status="replay_ready",
        expected_replay_status="ready",
        expected_eval_status="passed",
        expected_permission_evidence_status="present",
        expected_trace_evidence_status="ready",
        expected_replay_state_evidence_status="ready",
        expected_eval_evidence_status="passed",
        expected_replay_state_ref=CANONICAL_STATE_REF,
        requires_sqlite_state=True,
    ),
    "code_review_agent_denied": ScenarioArtifacts(
        name="code_review_agent_denied",
        manifest="manifest/examples/code_review_agent_release.v0.json",
        event="events/examples/code_review_agent_denied_step.v0.json",
        permission="permissions/examples/code_review_tool_permission_denied.v0.json",
        trace="traces/examples/code_review_agent_denied_trace.v0.json",
        eval_result="traces/examples/code_review_agent_denied_eval.v0.json",
        reconstruction="playbooks/examples/code_review_denied_reconstruction_packet.v0.json",
        policy_input="permissions/policy/input/code_review_write_diff.json",
        expected_reconstruction_status="blocked",
        expected_event_type="tool_call.denied",
        expected_event_outcome_status="denied",
        expected_permission_allow=False,
        expected_trace_status="partial",
        expected_replay_status="missing",
        expected_eval_status="failed",
        expected_permission_evidence_status="denied",
        expected_trace_evidence_status="present",
        expected_replay_state_evidence_status="missing",
        expected_eval_evidence_status="failed",
        expected_replay_state_ref="missing:denied-tool-call",
        expected_blocking_loss_fields=("replay_handle", "replay.state_ref"),
    ),
}


def scenario_names() -> tuple[str, ...]:
    return tuple(SCENARIOS)


def get_scenario(name: str) -> ScenarioArtifacts:
    try:
        return SCENARIOS[name]
    except KeyError as exc:
        raise KeyError(f"unknown scenario {name!r}; known: {sorted(SCENARIOS)}") from exc


__all__ = [
    "CANONICAL_STATE_REF",
    "REPO_ROOT",
    "SCENARIOS",
    "ScenarioArtifacts",
    "get_scenario",
    "scenario_names",
]
