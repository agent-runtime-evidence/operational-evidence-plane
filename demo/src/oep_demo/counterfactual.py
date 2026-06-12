"""Counterfactual replay demos over the deterministic code-review fixture."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from oep_permissions.paths import (
    COUNTERFACTUAL_APPROVAL_PER_STEP_POLICY_PATH,
    COUNTERFACTUAL_BUDGET_PER_RUN_POLICY_PATH,
    COUNTERFACTUAL_COMPOUND_RELIABILITY_POLICY_PATH,
)
from oep_permissions.replay import CounterfactualReplayRecord, counterfactual_replay_decisions

from oep_demo.paths import DEMO_ROOT, MANIFEST_PATH, PERMISSION_PATH, TRACE_PATH
from oep_demo.runner import atomic_state_connection, create_schema, insert_artifact, load_json, stable_json

COMPOUND_RELIABILITY_STEP_COUNT = 10
COMPOUND_RELIABILITY_STEP_BOUND = 4
COMPOUND_RELIABILITY_TRACE_ID = "55555555555555555555555555555555"
COMPOUND_RELIABILITY_TIMESTAMP = "2026-05-23T00:00:00Z"
DEFAULT_COUNTERFACTUAL_DIR = DEMO_ROOT / "counterfactual"
COMPOUND_RELIABILITY_JSON_NAME = "compound_reliability_counterfactual.v0.json"
COMPOUND_RELIABILITY_JSONL_NAME = "compound_reliability_counterfactual.v0.jsonl"
COMPOUND_RELIABILITY_STATE_NAME = "compound_reliability.sqlite"
BUDGET_PER_RUN_STEP_COUNT = 47
BUDGET_PER_RUN_STEP_USD = 1000
BUDGET_PER_RUN_CAP_USD = 5000
BUDGET_PER_RUN_TRACE_ID = "66666666666666666666666666666666"
BUDGET_PER_RUN_TIMESTAMP = "2026-05-23T00:00:00Z"
BUDGET_PER_RUN_JSON_NAME = "budget_per_run_counterfactual.v0.json"
BUDGET_PER_RUN_JSONL_NAME = "budget_per_run_counterfactual.v0.jsonl"
BUDGET_PER_RUN_STATE_NAME = "budget_per_run.sqlite"
APPROVAL_ESCALATION_STEP_COUNT = 6
APPROVAL_ESCALATION_WRITE_STEPS = (2, 4, 5)
APPROVAL_ESCALATION_TRACE_ID = "77777777777777777777777777777777"
APPROVAL_ESCALATION_TIMESTAMP = "2026-05-23T00:00:00Z"
APPROVAL_ESCALATION_JSON_NAME = "approval_escalation_counterfactual.v0.json"
APPROVAL_ESCALATION_JSONL_NAME = "approval_escalation_counterfactual.v0.jsonl"
APPROVAL_ESCALATION_STATE_NAME = "approval_escalation.sqlite"


@dataclass(frozen=True)
class CompoundReliabilityResult:
    """Generated artifact paths and compact verdict for the compound reliability demo."""

    json_path: Path
    jsonl_path: Path
    state_path: Path
    total_steps: int
    first_divergent_step: int
    original_status: str
    counterfactual_status: str


@dataclass(frozen=True)
class BudgetPerRunResult:
    """Generated artifact paths and compact verdict for the budget-per-run demo."""

    json_path: Path
    jsonl_path: Path
    state_path: Path
    total_steps: int
    termination_step: int
    original_total_usd: int
    counterfactual_total_usd: int


@dataclass(frozen=True)
class ApprovalEscalationResult:
    """Generated artifact paths and compact verdict for the approval escalation demo."""

    json_path: Path
    jsonl_path: Path
    state_path: Path
    total_steps: int
    added_approval_steps: tuple[str, ...]


def run_compound_reliability_counterfactual(
    output_dir: Path = DEFAULT_COUNTERFACTUAL_DIR,
    *,
    state_path: Path | None = None,
) -> CompoundReliabilityResult:
    """Generate the v0.3 compound reliability counterfactual demo outputs."""

    output_dir.mkdir(parents=True, exist_ok=True)
    replay_state_path = state_path or output_dir / COMPOUND_RELIABILITY_STATE_NAME
    json_path = output_dir / COMPOUND_RELIABILITY_JSON_NAME
    jsonl_path = output_dir / COMPOUND_RELIABILITY_JSONL_NAME
    _materialize_compound_reliability_state(replay_state_path, json_path)

    step_outputs = [
        record.to_dict()
        for record in counterfactual_replay_decisions(
            replay_state_path,
            [_decision_id(index) for index in range(1, COMPOUND_RELIABILITY_STEP_COUNT + 1)],
            COUNTERFACTUAL_COMPOUND_RELIABILITY_POLICY_PATH,
            replay_timestamp_utc=COMPOUND_RELIABILITY_TIMESTAMP,
        )
    ]
    first_divergent_step = _first_denied_step(step_outputs)
    summary = {
        "schema_version": "oep.counterfactual_demo.compound_reliability.v0",
        "scenario_id": "code_review_agent_compound_reliability",
        "question": "Would this 10-step workflow have succeeded under a stricter 4-step bounded policy?",
        "workflow": {
            "original_status": "succeeded",
            "counterfactual_status": "failed",
            "total_steps": COMPOUND_RELIABILITY_STEP_COUNT,
            "counterfactual_step_bound": COMPOUND_RELIABILITY_STEP_BOUND,
            "first_divergent_step": first_divergent_step,
            "failure_decision_id": _decision_id(first_divergent_step),
        },
        "step_outputs": step_outputs,
        "claim_boundary": (
            "This is a deterministic counterfactual policy replay demonstration over the existing "
            "code-review fixture. It is not a production-grade replay engine, compliance certification, "
            "or legal/regulatory adequacy claim."
        ),
    }

    json_path.write_text(_stable_pretty_json(summary), encoding="utf-8")
    jsonl_path.write_text("".join(_stable_jsonl_line(step) for step in step_outputs), encoding="utf-8")

    return CompoundReliabilityResult(
        json_path=json_path,
        jsonl_path=jsonl_path,
        state_path=replay_state_path,
        total_steps=COMPOUND_RELIABILITY_STEP_COUNT,
        first_divergent_step=first_divergent_step,
        original_status="succeeded",
        counterfactual_status="failed",
    )


def run_approval_escalation_counterfactual(
    output_dir: Path = DEFAULT_COUNTERFACTUAL_DIR,
    *,
    state_path: Path | None = None,
) -> ApprovalEscalationResult:
    """Generate the v0.3 approval-per-step escalation counterfactual demo outputs."""

    output_dir.mkdir(parents=True, exist_ok=True)
    replay_state_path = state_path or output_dir / APPROVAL_ESCALATION_STATE_NAME
    json_path = output_dir / APPROVAL_ESCALATION_JSON_NAME
    jsonl_path = output_dir / APPROVAL_ESCALATION_JSONL_NAME
    _materialize_approval_escalation_state(replay_state_path, json_path)

    step_outputs = [
        record.with_diff_updates({"approval_delta": _approval_delta(record, index)}).to_dict()
        for index, record in enumerate(
            counterfactual_replay_decisions(
                replay_state_path,
                [_approval_decision_id(index) for index in range(1, APPROVAL_ESCALATION_STEP_COUNT + 1)],
                COUNTERFACTUAL_APPROVAL_PER_STEP_POLICY_PATH,
                replay_timestamp_utc=APPROVAL_ESCALATION_TIMESTAMP,
            ),
            start=1,
        )
    ]

    added_approval_steps = tuple(_approval_step_label(index) for index in APPROVAL_ESCALATION_WRITE_STEPS)
    summary = {
        "schema_version": "oep.counterfactual_demo.approval_escalation.v0",
        "scenario_id": "code_review_agent_approval_escalation",
        "question": "Would this approval-gated workflow have escalated differently under per-step write approval?",
        "approval": {
            "original_policy": "approval required only for production deploy actions",
            "counterfactual_policy": "approval required for every write operation",
            "added_approval_steps": list(added_approval_steps),
            "counterfactual_approval_type": "human_write_approval_required",
        },
        "step_outputs": step_outputs,
        "claim_boundary": (
            "This is a deterministic approval-per-step counterfactual replay demonstration over the existing "
            "code-review fixture. It is not a production authorization system, production-grade replay engine, "
            "compliance certification, or legal/regulatory adequacy claim."
        ),
    }

    json_path.write_text(_stable_pretty_json(summary), encoding="utf-8")
    jsonl_path.write_text("".join(_stable_jsonl_line(step) for step in step_outputs), encoding="utf-8")

    return ApprovalEscalationResult(
        json_path=json_path,
        jsonl_path=jsonl_path,
        state_path=replay_state_path,
        total_steps=APPROVAL_ESCALATION_STEP_COUNT,
        added_approval_steps=added_approval_steps,
    )


def run_budget_per_run_counterfactual(
    output_dir: Path = DEFAULT_COUNTERFACTUAL_DIR,
    *,
    state_path: Path | None = None,
) -> BudgetPerRunResult:
    """Generate the v0.3 budget-per-run cross-over counterfactual demo outputs."""

    output_dir.mkdir(parents=True, exist_ok=True)
    replay_state_path = state_path or output_dir / BUDGET_PER_RUN_STATE_NAME
    json_path = output_dir / BUDGET_PER_RUN_JSON_NAME
    jsonl_path = output_dir / BUDGET_PER_RUN_JSONL_NAME
    _materialize_budget_per_run_state(replay_state_path, json_path)

    step_outputs = [
        record.with_diff_updates({"budget_delta": _budget_delta(record, index)}).to_dict()
        for index, record in enumerate(
            counterfactual_replay_decisions(
                replay_state_path,
                [_budget_decision_id(index) for index in range(1, BUDGET_PER_RUN_STEP_COUNT + 1)],
                COUNTERFACTUAL_BUDGET_PER_RUN_POLICY_PATH,
                replay_timestamp_utc=BUDGET_PER_RUN_TIMESTAMP,
            ),
            start=1,
        )
    ]

    termination_step = _first_denied_step(step_outputs)
    counterfactual_total = (termination_step - 1) * BUDGET_PER_RUN_STEP_USD
    summary = {
        "schema_version": "oep.counterfactual_demo.budget_per_run.v0",
        "scenario_id": "code_review_agent_budget_per_run",
        "question": "Would this synthetic runaway loop have triggered under a stricter budget-per-run policy?",
        "budget": {
            "original_total_usd": BUDGET_PER_RUN_STEP_COUNT * BUDGET_PER_RUN_STEP_USD,
            "counterfactual_budget_cap_usd": BUDGET_PER_RUN_CAP_USD,
            "counterfactual_total_usd": counterfactual_total,
            "termination_step": termination_step,
            "termination_code": "BUDGET_EXCEEDED",
            "budget_cap_active_at_termination": True,
        },
        "cost_trace": [
            _budget_cost_trace_row(index, termination_step) for index in range(1, BUDGET_PER_RUN_STEP_COUNT + 1)
        ],
        "step_outputs": step_outputs,
        "claim_boundary": (
            "This is a deterministic synthetic budget-per-run counterfactual replay demonstration "
            "over the existing code-review fixture. It is not a production incident record, production-grade "
            "replay engine, compliance certification, or legal/regulatory adequacy claim."
        ),
    }

    json_path.write_text(_stable_pretty_json(summary), encoding="utf-8")
    jsonl_path.write_text("".join(_stable_jsonl_line(step) for step in step_outputs), encoding="utf-8")

    return BudgetPerRunResult(
        json_path=json_path,
        jsonl_path=jsonl_path,
        state_path=replay_state_path,
        total_steps=BUDGET_PER_RUN_STEP_COUNT,
        termination_step=termination_step,
        original_total_usd=BUDGET_PER_RUN_STEP_COUNT * BUDGET_PER_RUN_STEP_USD,
        counterfactual_total_usd=counterfactual_total,
    )


def _materialize_compound_reliability_state(state_path: Path, output_path: Path) -> None:
    _materialize_counterfactual_state(
        state_path,
        output_path,
        step_count=COMPOUND_RELIABILITY_STEP_COUNT,
        trace_factory=_compound_trace,
        event_factory=_compound_event,
        permission_factory=_compound_permission,
    )


def _materialize_approval_escalation_state(state_path: Path, output_path: Path) -> None:
    _materialize_counterfactual_state(
        state_path,
        output_path,
        step_count=APPROVAL_ESCALATION_STEP_COUNT,
        trace_factory=_approval_trace,
        event_factory=_approval_event,
        permission_factory=_approval_permission,
    )


def _materialize_budget_per_run_state(state_path: Path, output_path: Path) -> None:
    _materialize_counterfactual_state(
        state_path,
        output_path,
        step_count=BUDGET_PER_RUN_STEP_COUNT,
        trace_factory=_budget_trace,
        event_factory=_budget_event,
        permission_factory=_budget_permission,
    )


def _materialize_counterfactual_state(
    state_path: Path,
    output_path: Path,
    *,
    step_count: int,
    trace_factory: Callable[[dict[str, Any]], dict[str, Any]],
    event_factory: Callable[[int, dict[str, Any], str, str], dict[str, Any]],
    permission_factory: Callable[[int, dict[str, Any], dict[str, Any], str], dict[str, Any]],
) -> None:
    manifest = load_json(MANIFEST_PATH)
    base_permission = load_json(PERMISSION_PATH)
    trace = trace_factory(manifest)
    output_ref = _stable_artifact_ref(output_path, output_path.parent)
    state_ref = _stable_artifact_ref(state_path, output_path.parent)
    artifact_path = Path(output_ref)

    with atomic_state_connection(state_path) as connection:
        with connection:
            create_schema(connection)
            insert_artifact(
                connection,
                kind="release_manifest",
                artifact_id=manifest["manifest_id"],
                path=MANIFEST_PATH,
                payload=manifest,
            )
            insert_artifact(
                connection,
                kind="operational_trace",
                artifact_id=trace["trace_id"],
                path=TRACE_PATH,
                payload=trace,
            )
            connection.execute(
                "INSERT INTO traces (trace_id, release_manifest_id, status, payload_json) VALUES (?, ?, ?, ?)",
                (
                    trace["trace_id"],
                    trace["release_manifest_id"],
                    trace["status"],
                    stable_json(trace),
                ),
            )
            for index in range(1, step_count + 1):
                event = event_factory(index, manifest, output_ref, state_ref)
                permission = permission_factory(index, base_permission, event, output_ref)
                insert_artifact(
                    connection,
                    kind="agent_step_event",
                    artifact_id=event["event_id"],
                    path=artifact_path,
                    payload=event,
                )
                insert_artifact(
                    connection,
                    kind="tool_permission_packet",
                    artifact_id=permission["packet_id"],
                    path=artifact_path,
                    payload=permission,
                )
                _insert_event(connection, event)
                _insert_permission(connection, permission)


def _stable_artifact_ref(path: Path, output_dir: Path) -> str:
    resolved = path.resolve()
    try:
        return Path(os.path.relpath(resolved, output_dir.resolve())).as_posix()
    except ValueError:
        return resolved.as_posix()


def _compound_trace(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "oep.operational_trace.v0",
        "trace_id": COMPOUND_RELIABILITY_TRACE_ID,
        "release_manifest_id": manifest["manifest_id"],
        "status": "succeeded",
        "summary": "Synthetic 10-step code-review workflow for compound reliability counterfactual replay.",
        "permission_packet_refs": [_decision_id(index) for index in range(1, COMPOUND_RELIABILITY_STEP_COUNT + 1)],
    }


def _approval_trace(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "oep.operational_trace.v0",
        "trace_id": APPROVAL_ESCALATION_TRACE_ID,
        "release_manifest_id": manifest["manifest_id"],
        "status": "succeeded",
        "summary": "Synthetic code-review workflow for approval-per-step counterfactual replay.",
        "permission_packet_refs": [
            _approval_decision_id(index) for index in range(1, APPROVAL_ESCALATION_STEP_COUNT + 1)
        ],
    }


def _budget_trace(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "oep.operational_trace.v0",
        "trace_id": BUDGET_PER_RUN_TRACE_ID,
        "release_manifest_id": manifest["manifest_id"],
        "status": "succeeded",
        "summary": "Synthetic 47-step code-review loop for budget-per-run counterfactual replay.",
        "permission_packet_refs": [_budget_decision_id(index) for index in range(1, BUDGET_PER_RUN_STEP_COUNT + 1)],
    }


def _compound_event(index: int, manifest: dict[str, Any], output_ref: str, state_ref: str) -> dict[str, Any]:
    return {
        "schema_version": "oep.agent_step_event.v0",
        "event_id": _event_id(index),
        "event_time": f"2026-05-04T00:00:{index:02d}Z",
        "event_type": "agent_step.completed",
        "release_manifest_id": manifest["manifest_id"],
        "trace_id": COMPOUND_RELIABILITY_TRACE_ID,
        "span_id": _span_id(index),
        "parent_span_id": _span_id(index - 1) if index > 1 else None,
        "checkpoint": {
            "name": f"review.compound_reliability.step_{index:02d}",
            "sequence": index,
            "state": "after",
        },
        "actor": {
            "type": "agent",
            "id": "agent_code_review_reference_demo",
            "display_name": "code-review-agent-reference-demo",
        },
        "action": {
            "action_type": "inspect_diff",
            "name": f"inspect synthetic repository diff at workflow step {index}",
            "input_ref": "demo/fixtures/diff_synthetic_001.patch",
            "output_ref": output_ref,
        },
        "tool_call_id": _tool_call_id(index),
        "permission_packet_ref": _decision_id(index),
        "replay_handle": {
            "type": "sqlite",
            "id": f"replay_compound_reliability_step_{index:04d}",
            "state_ref": f"{state_ref}#events/{_event_id(index)}",
            "deterministic": True,
        },
        "outcome": {
            "status": "succeeded",
            "summary": f"Compound reliability workflow step {index} completed.",
            "error_ref": None,
        },
    }


def _approval_event(index: int, manifest: dict[str, Any], output_ref: str, state_ref: str) -> dict[str, Any]:
    write_step = index in APPROVAL_ESCALATION_WRITE_STEPS
    operation = "write" if write_step else "read"
    action_type = "write_diff" if write_step else "inspect_diff"
    return {
        "schema_version": "oep.agent_step_event.v0",
        "event_id": _approval_event_id(index),
        "event_time": f"2026-05-04T01:00:{index:02d}Z",
        "event_type": "agent_step.completed",
        "release_manifest_id": manifest["manifest_id"],
        "trace_id": APPROVAL_ESCALATION_TRACE_ID,
        "span_id": _approval_span_id(index),
        "parent_span_id": _approval_span_id(index - 1) if index > 1 else None,
        "checkpoint": {
            "name": f"review.approval_escalation.step_{index:02d}",
            "sequence": index,
            "state": "after",
        },
        "actor": {
            "type": "agent",
            "id": "agent_code_review_reference_demo",
            "display_name": "code-review-agent-reference-demo",
        },
        "action": {
            "action_type": action_type,
            "name": f"{operation} synthetic repository diff at approval workflow step {index}",
            "input_ref": "demo/fixtures/diff_synthetic_001.patch",
            "output_ref": output_ref,
        },
        "tool_call_id": _approval_tool_call_id(index),
        "permission_packet_ref": _approval_decision_id(index),
        "replay_handle": {
            "type": "sqlite",
            "id": f"replay_approval_escalation_step_{index:04d}",
            "state_ref": f"{state_ref}#events/{_approval_event_id(index)}",
            "deterministic": True,
        },
        "outcome": {
            "status": "succeeded",
            "summary": f"Approval workflow step {index} completed under the original permissive policy.",
            "error_ref": None,
        },
    }


def _budget_event(index: int, manifest: dict[str, Any], output_ref: str, state_ref: str) -> dict[str, Any]:
    return {
        "schema_version": "oep.agent_step_event.v0",
        "event_id": _budget_event_id(index),
        "event_time": f"2026-05-04T00:{index // 60:02d}:{index % 60:02d}Z",
        "event_type": "agent_step.completed",
        "release_manifest_id": manifest["manifest_id"],
        "trace_id": BUDGET_PER_RUN_TRACE_ID,
        "span_id": _budget_span_id(index),
        "parent_span_id": _budget_span_id(index - 1) if index > 1 else None,
        "checkpoint": {
            "name": f"review.budget_per_run.step_{index:02d}",
            "sequence": index,
            "state": "after",
        },
        "budget": {
            "step_cost_usd": BUDGET_PER_RUN_STEP_USD,
            "original_cumulative_usd": index * BUDGET_PER_RUN_STEP_USD,
            "counterfactual_budget_cap_usd": BUDGET_PER_RUN_CAP_USD,
        },
        "actor": {
            "type": "agent",
            "id": "agent_code_review_reference_demo",
            "display_name": "code-review-agent-reference-demo",
        },
        "action": {
            "action_type": "inspect_diff",
            "name": f"inspect synthetic repository diff in runaway-loop step {index}",
            "input_ref": "demo/fixtures/diff_synthetic_001.patch",
            "output_ref": output_ref,
        },
        "tool_call_id": _budget_tool_call_id(index),
        "permission_packet_ref": _budget_decision_id(index),
        "replay_handle": {
            "type": "sqlite",
            "id": f"replay_budget_per_run_step_{index:04d}",
            "state_ref": f"{state_ref}#events/{_budget_event_id(index)}",
            "deterministic": True,
        },
        "outcome": {
            "status": "succeeded",
            "summary": f"Synthetic runaway-loop workflow step {index} completed.",
            "error_ref": None,
        },
    }


def _compound_permission(
    index: int,
    base_permission: dict[str, Any],
    event: dict[str, Any],
    output_ref: str,
) -> dict[str, Any]:
    permission = {
        **base_permission,
        "packet_id": _decision_id(index),
        "decision_time": f"2026-05-04T00:00:{index:02d}Z",
        "event_id": event["event_id"],
        "tool_call_id": event["tool_call_id"],
        "trace_id": event["trace_id"],
        "span_id": event["span_id"],
        "requested_action": {
            "action_type": "inspect_diff",
            "name": f"inspect synthetic repository diff at workflow step {index}",
            "input_ref": "demo/fixtures/diff_synthetic_001.patch",
        },
        "links": {
            "event_ref": output_ref,
            "release_manifest_ref": "manifest/examples/code_review_agent_release.v0.json",
            "trace_ref": output_ref,
        },
        "claim_boundary": (
            "This packet records one allowed OPA-backed permission decision in a deterministic "
            "10-step code-review counterfactual replay demo. It does not create a production, "
            "compliance, audit, or model-quality claim."
        ),
    }
    return permission


def _approval_permission(
    index: int,
    base_permission: dict[str, Any],
    event: dict[str, Any],
    output_ref: str,
) -> dict[str, Any]:
    write_step = index in APPROVAL_ESCALATION_WRITE_STEPS
    operation = "write" if write_step else "read"
    action_type = "write_diff" if write_step else "inspect_diff"
    tool_name = "write_diff" if write_step else "read_diff"
    return {
        **base_permission,
        "packet_id": _approval_decision_id(index),
        "decision_time": f"2026-05-04T01:00:{index:02d}Z",
        "event_id": event["event_id"],
        "tool_call_id": event["tool_call_id"],
        "trace_id": event["trace_id"],
        "span_id": event["span_id"],
        "requested_action": {
            "action_type": action_type,
            "name": f"{operation} synthetic repository diff at approval workflow step {index}",
            "input_ref": "demo/fixtures/diff_synthetic_001.patch",
        },
        "tool": {
            "name": tool_name,
            "version": "0.1.0",
            "operation": operation,
        },
        "resource": {
            "type": "repository_diff",
            "id": "diff_synthetic_001",
            "uri": "demo/fixtures/diff_synthetic_001.patch",
            "mutable": write_step,
        },
        "decision": {
            "allow": True,
            "reason": "original permissive approval policy allows this code-review workflow step",
            "matched_rule": "allow_original_permissive_approval_policy",
            "opa_result_ref": "synthetic original approval policy: only production deploy actions require approval",
        },
        "approval_capture": None,
        "links": {
            "event_ref": output_ref,
            "release_manifest_ref": "manifest/examples/code_review_agent_release.v0.json",
            "trace_ref": output_ref,
        },
        "claim_boundary": (
            "This packet records one allowed original-policy decision in a deterministic "
            "approval-per-step counterfactual replay demo. It does not create a production, "
            "compliance, audit, or model-quality claim."
        ),
    }


def _budget_permission(
    index: int,
    base_permission: dict[str, Any],
    event: dict[str, Any],
    output_ref: str,
) -> dict[str, Any]:
    return {
        **base_permission,
        "packet_id": _budget_decision_id(index),
        "decision_time": f"2026-05-04T00:{index // 60:02d}:{index % 60:02d}Z",
        "event_id": event["event_id"],
        "tool_call_id": event["tool_call_id"],
        "trace_id": event["trace_id"],
        "span_id": event["span_id"],
        "requested_action": {
            "action_type": "inspect_diff",
            "name": f"inspect synthetic repository diff in runaway-loop step {index}",
            "input_ref": "demo/fixtures/diff_synthetic_001.patch",
        },
        "links": {
            "event_ref": output_ref,
            "release_manifest_ref": "manifest/examples/code_review_agent_release.v0.json",
            "trace_ref": output_ref,
        },
        "claim_boundary": (
            "This packet records one allowed OPA-backed permission decision in a deterministic "
            "synthetic budget-per-run counterfactual replay demo. It does not create a production, "
            "compliance, audit, or model-quality claim."
        ),
    }


def _insert_event(connection: sqlite3.Connection, event: dict[str, Any]) -> None:
    connection.execute(
        """
        INSERT INTO events (
            event_id,
            trace_id,
            span_id,
            release_manifest_id,
            tool_call_id,
            permission_packet_ref,
            payload_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event["event_id"],
            event["trace_id"],
            event["span_id"],
            event["release_manifest_id"],
            event["tool_call_id"],
            event["permission_packet_ref"],
            stable_json(event),
        ),
    )


def _insert_permission(connection: sqlite3.Connection, permission: dict[str, Any]) -> None:
    connection.execute(
        """
        INSERT INTO permissions (
            packet_id,
            event_id,
            tool_call_id,
            trace_id,
            span_id,
            allow,
            reason,
            payload_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            permission["packet_id"],
            permission["event_id"],
            permission["tool_call_id"],
            permission["trace_id"],
            permission["span_id"],
            int(permission["decision"]["allow"]),
            permission["decision"]["reason"],
            stable_json(permission),
        ),
    )


def _first_denied_step(step_outputs: list[dict[str, Any]]) -> int:
    for index, step in enumerate(step_outputs, start=1):
        counterfactual = step.get("counterfactual")
        if isinstance(counterfactual, dict) and counterfactual.get("decision") == "deny":
            return index
    raise RuntimeError("compound reliability counterfactual did not produce a denied step")


def _budget_delta(record: CounterfactualReplayRecord, index: int) -> dict[str, Any]:
    counterfactual = record.counterfactual
    cumulative_usd = index * BUDGET_PER_RUN_STEP_USD
    denied = counterfactual.get("decision") == "deny"
    return {
        "budget_cap_active": denied,
        "cost_trace_changed": denied,
        "original_total_usd": cumulative_usd,
        "counterfactual_total_usd": min(cumulative_usd, BUDGET_PER_RUN_CAP_USD),
        "termination_step": index if denied else None,
        "termination_code": counterfactual.get("decision_code") if denied else None,
    }


def _budget_cost_trace_row(index: int, termination_step: int) -> dict[str, Any]:
    original_cumulative = index * BUDGET_PER_RUN_STEP_USD
    counterfactual_cumulative = min(original_cumulative, BUDGET_PER_RUN_CAP_USD)
    return {
        "step": index,
        "original_cumulative_usd": original_cumulative,
        "counterfactual_cumulative_usd": counterfactual_cumulative,
        "budget_cap_active": index >= termination_step,
        "termination_code": "BUDGET_EXCEEDED" if index == termination_step else None,
        "skipped_after_termination": index > termination_step,
    }


def _approval_delta(record: CounterfactualReplayRecord, index: int) -> Mapping[str, Any]:
    counterfactual = record.counterfactual
    required = counterfactual.get("decision_code") == "APPROVAL_REQUIRED"
    step_label = _approval_step_label(index)
    return {
        "approval_requirements_changed": required,
        "added_approval_steps": [step_label] if required else [],
        "removed_approval_steps": [],
        "counterfactual_approval_capture": (
            {
                "approval_type": "human_write_approval_required",
                "required_at_step": step_label,
                "approver": {
                    "type": "human",
                    "id": "human_code_owner",
                    "display_name": "code owner",
                },
            }
            if required
            else None
        ),
    }


def _approval_step_label(index: int) -> str:
    return f"approval_step_{index:02d}"


def _decision_id(index: int) -> str:
    return f"pder_code_review_compound_reliability_step_{index:04d}"


def _event_id(index: int) -> str:
    return f"evt_code_review_compound_reliability_step_{index:04d}"


def _tool_call_id(index: int) -> str:
    return f"tool_compound_reliability_step_{index:04d}"


def _span_id(index: int) -> str:
    return f"{index:016x}"


def _budget_decision_id(index: int) -> str:
    return f"pder_code_review_budget_per_run_step_{index:04d}"


def _budget_event_id(index: int) -> str:
    return f"evt_code_review_budget_per_run_step_{index:04d}"


def _budget_tool_call_id(index: int) -> str:
    return f"tool_budget_per_run_step_{index:04d}"


def _budget_span_id(index: int) -> str:
    return f"{index + 1000:016x}"


def _approval_decision_id(index: int) -> str:
    return f"pder_code_review_approval_escalation_step_{index:04d}"


def _approval_event_id(index: int) -> str:
    return f"evt_code_review_approval_escalation_step_{index:04d}"


def _approval_tool_call_id(index: int) -> str:
    return f"tool_approval_escalation_step_{index:04d}"


def _approval_span_id(index: int) -> str:
    return f"{index + 2000:016x}"


def _stable_pretty_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def _stable_jsonl_line(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n"


__all__ = [
    "APPROVAL_ESCALATION_JSONL_NAME",
    "APPROVAL_ESCALATION_JSON_NAME",
    "APPROVAL_ESCALATION_STATE_NAME",
    "APPROVAL_ESCALATION_STEP_COUNT",
    "APPROVAL_ESCALATION_WRITE_STEPS",
    "ApprovalEscalationResult",
    "BUDGET_PER_RUN_CAP_USD",
    "BUDGET_PER_RUN_JSONL_NAME",
    "BUDGET_PER_RUN_JSON_NAME",
    "BUDGET_PER_RUN_STATE_NAME",
    "BUDGET_PER_RUN_STEP_COUNT",
    "BUDGET_PER_RUN_STEP_USD",
    "BudgetPerRunResult",
    "COMPOUND_RELIABILITY_JSONL_NAME",
    "COMPOUND_RELIABILITY_JSON_NAME",
    "COMPOUND_RELIABILITY_STATE_NAME",
    "COMPOUND_RELIABILITY_STEP_BOUND",
    "COMPOUND_RELIABILITY_STEP_COUNT",
    "CompoundReliabilityResult",
    "run_approval_escalation_counterfactual",
    "run_budget_per_run_counterfactual",
    "run_compound_reliability_counterfactual",
]
