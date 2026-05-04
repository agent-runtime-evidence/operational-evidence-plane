"""Check committed reconstruction packets against scenario artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

from oep_verify.scenarios import (
    CANONICAL_STATE_REF,
    REPO_ROOT,
    ScenarioArtifacts,
    get_scenario,
    scenario_names,
)
from oep_verify.verify_support import (
    load_json_object,
    path_from_env,
    relative_path,
    require,
    require_datetime_not_after,
    require_json_list,
    require_json_object,
    require_resolved_layer_bindings,
    scalar,
    validate_json_schema,
)

EVENT_SCHEMA_PATH = REPO_ROOT / "events" / "schema" / "agent_step_event.v0.schema.json"
PERMISSION_SCHEMA_PATH = REPO_ROOT / "permissions" / "schema" / "tool_permission_packet.v0.schema.json"
POLICY_PATH = REPO_ROOT / "permissions" / "policy" / "tool_permissions.rego"
TRACE_SCHEMA_PATH = REPO_ROOT / "traces" / "schema" / "operational_trace.v0.schema.json"
EVAL_SCHEMA_PATH = REPO_ROOT / "traces" / "schema" / "eval_result.v0.schema.json"
PACKET_SCHEMA_PATH = REPO_ROOT / "playbooks" / "schema" / "reconstruction_packet.v0.schema.json"
STATE_PATH = path_from_env(
    REPO_ROOT,
    "OEP_DEMO_STATE_PATH",
    REPO_ROOT / "demo" / "state" / "code_review_agent.sqlite",
)


def rel(path: Path) -> str:
    return relative_path(REPO_ROOT, path)


def opa_decision(policy_input_path: Path) -> dict[str, Any]:
    opa = shutil.which("opa")
    if opa is None:
        raise AssertionError("opa executable is required for reconstruction validation")
    result = subprocess.run(
        [
            opa,
            "eval",
            "--format",
            "json",
            "--data",
            str(POLICY_PATH),
            "--input",
            str(policy_input_path),
            "data.oep.permissions.decision",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    value = payload["result"][0]["expressions"][0]["value"]
    require(isinstance(value, dict), "OPA decision must be an object")
    return value


def has_blocking_loss(losses: list[Any], field: str) -> bool:
    return any(
        isinstance(item, dict) and item.get("field") == field and item.get("severity") == "blocking"
        for item in losses
    )


def check_scenario(scenario: ScenarioArtifacts, *, state_path: Path = STATE_PATH) -> None:
    manifest_path = scenario.path(scenario.manifest)
    event_path = scenario.path(scenario.event)
    permission_path = scenario.path(scenario.permission)
    trace_path = scenario.path(scenario.trace)
    eval_path = scenario.path(scenario.eval_result)
    packet_path = scenario.path(scenario.reconstruction)
    policy_input_path = scenario.path(scenario.policy_input)

    manifest = load_json_object(manifest_path)

    event_schema = load_json_object(EVENT_SCHEMA_PATH)
    event = load_json_object(event_path)
    validate_json_schema(event_schema, event, instance_path=event_path)

    permission_schema = load_json_object(PERMISSION_SCHEMA_PATH)
    permission = load_json_object(permission_path)
    validate_json_schema(permission_schema, permission, instance_path=permission_path)

    trace_schema = load_json_object(TRACE_SCHEMA_PATH)
    trace = load_json_object(trace_path)
    validate_json_schema(trace_schema, trace, instance_path=trace_path)

    eval_schema = load_json_object(EVAL_SCHEMA_PATH)
    eval_result = load_json_object(eval_path)
    validate_json_schema(eval_schema, eval_result, instance_path=eval_path)

    packet_schema = load_json_object(PACKET_SCHEMA_PATH)
    packet = load_json_object(packet_path)
    validate_json_schema(packet_schema, packet, instance_path=packet_path)

    require(packet_schema.get("title") == "Operational Evidence Plane Reconstruction Packet v0", "bad schema")
    require(packet.get("schema_version") == "oep.reconstruction_packet.v0", "bad packet schema_version")
    require(packet.get("reconstruction_status") == scenario.expected_reconstruction_status, "bad reconstruction status")
    if packet.get("reconstruction_status") == "ready":
        require_resolved_layer_bindings(manifest, f"{scenario.name} ready reconstruction")
    require(event.get("event_type") == scenario.expected_event_type, "bad event type")
    outcome = require_json_object(event.get("outcome"), "event outcome must be an object")
    require(outcome.get("status") == scenario.expected_event_outcome_status, "bad event outcome status")

    check_identity_joins(scenario, manifest, event, permission, trace, eval_result, packet)
    check_temporal_order(manifest, event, permission, trace, packet)
    check_policy_decision(scenario, event, permission, policy_input_path)
    check_trace_links(scenario, trace, event, permission, event_path, permission_path, trace_path)
    check_reconstruction_summary(
        scenario,
        packet,
        trace,
        eval_result,
        manifest_path,
        event_path,
        permission_path,
        trace_path,
        eval_path,
    )
    check_replay_semantics(scenario, event, trace, packet, state_path)


def check_identity_joins(
    scenario: ScenarioArtifacts,
    manifest: dict[str, Any],
    event: dict[str, Any],
    permission: dict[str, Any],
    trace: dict[str, Any],
    eval_result: dict[str, Any],
    packet: dict[str, Any],
) -> None:
    require(packet.get("release_manifest_id") == manifest.get("manifest_id"), "packet manifest mismatch")
    require(packet.get("release_manifest_id") == event.get("release_manifest_id"), "event manifest mismatch")
    require(permission.get("release_manifest_id") == manifest.get("manifest_id"), "permission manifest mismatch")
    require(trace.get("release_manifest_id") == manifest.get("manifest_id"), "trace manifest mismatch")
    require(eval_result.get("release_manifest_id") == manifest.get("manifest_id"), "eval manifest mismatch")

    for key in ("event_id", "tool_call_id", "trace_id", "span_id"):
        require(permission.get(key) == event.get(key), f"permission/event join mismatch for {key}")
    require(trace.get("trace_id") == event.get("trace_id"), "trace/event trace_id mismatch")
    require(eval_result.get("trace_id") == trace.get("trace_id"), "eval trace_id mismatch")
    require(packet.get("event_id") == event.get("event_id"), "packet event mismatch")
    require(packet.get("tool_call_id") == event.get("tool_call_id"), "packet tool call mismatch")
    require(packet.get("permission_packet_id") == permission.get("packet_id"), "packet permission mismatch")
    require(packet.get("trace_id") == trace.get("trace_id"), "packet trace mismatch")
    require(packet.get("eval_id") == eval_result.get("eval_id"), "packet eval mismatch")
    require(event.get("permission_packet_ref") == permission.get("packet_id"), "event packet ref mismatch")
    require(trace.get("scenario") == packet.get("scenario"), f"{scenario.name} trace/packet scenario mismatch")


def check_temporal_order(
    manifest: dict[str, Any],
    event: dict[str, Any],
    permission: dict[str, Any],
    trace: dict[str, Any],
    packet: dict[str, Any],
) -> None:
    require_datetime_not_after(
        manifest.get("created_at"),
        event.get("event_time"),
        "manifest.created_at",
        "event.event_time",
    )
    require_datetime_not_after(
        permission.get("decision_time"),
        event.get("event_time"),
        "permission.decision_time",
        "event.event_time",
    )
    require_datetime_not_after(trace.get("started_at"), trace.get("ended_at"), "trace.started_at", "trace.ended_at")
    require_datetime_not_after(event.get("event_time"), trace.get("ended_at"), "event.event_time", "trace.ended_at")
    require_datetime_not_after(trace.get("ended_at"), packet.get("created_at"), "trace.ended_at", "packet.created_at")


def check_policy_decision(
    scenario: ScenarioArtifacts,
    event: dict[str, Any],
    permission: dict[str, Any],
    policy_input_path: Path,
) -> None:
    policy_input = load_json_object(policy_input_path)
    for key in ("release_manifest_id", "event_id", "tool_call_id", "trace_id", "span_id"):
        require(permission.get(key) == policy_input.get(key), f"policy input mismatch for {key}")

    requested_action = require_json_object(permission.get("requested_action"), "permission action must be an object")
    event_action = require_json_object(event.get("action"), "event action must be an object")
    input_action = require_json_object(policy_input.get("action"), "policy input action must be an object")
    for key in ("action_type", "name", "input_ref"):
        require(requested_action.get(key) == input_action.get(key), f"policy action mismatch for {key}")
        require(requested_action.get(key) == event_action.get(key), f"event action mismatch for {key}")

    decision = require_json_object(permission.get("decision"), "permission decision must be an object")
    opa = opa_decision(policy_input_path)
    require(decision.get("allow") is scenario.expected_permission_allow, "permission allow mismatch")
    require(decision.get("allow") == opa.get("allow"), "OPA allow mismatch")
    require(decision.get("reason") == opa.get("reason"), "OPA reason mismatch")
    require(decision.get("matched_rule") == opa.get("matched_rule"), "OPA matched_rule mismatch")
    policy = require_json_object(permission.get("policy"), "permission policy must be an object")
    require(policy.get("policy_id") == opa.get("policy_id"), "OPA policy_id mismatch")
    require(policy.get("policy_version") == opa.get("policy_version"), "OPA policy_version mismatch")


def check_trace_links(
    scenario: ScenarioArtifacts,
    trace: dict[str, Any],
    event: dict[str, Any],
    permission: dict[str, Any],
    event_path: Path,
    permission_path: Path,
    trace_path: Path,
) -> None:
    require(trace.get("status") == scenario.expected_trace_status, "trace status mismatch")
    joins = require_json_object(trace.get("joins"), "trace joins must be an object")
    require(joins.get("release_manifest_ref") == scenario.manifest, "trace manifest ref mismatch")
    require(joins.get("event_refs") == [rel(event_path)], "trace event refs mismatch")
    require(joins.get("permission_packet_refs") == [rel(permission_path)], "trace permission refs mismatch")

    spans = require_json_list(trace.get("spans"), "trace spans must be a list")
    require(len(spans) == 1, "expected one trace span")
    span = require_json_object(spans[0], "trace span must be an object")
    require(span.get("span_id") == event.get("span_id"), "span_id mismatch")
    require(span.get("event_ref") == rel(event_path), "span event_ref mismatch")
    require(span.get("permission_packet_ref") == rel(permission_path), "span permission ref mismatch")
    require(span.get("tool_call_id") == permission.get("tool_call_id"), "span tool_call_id mismatch")

    event_links = require_json_object(event.get("links"), "event links must be an object")
    permission_links = require_json_object(permission.get("links"), "permission links must be an object")
    require(event_links.get("trace_ref") == rel(trace_path), "event trace_ref mismatch")
    require(permission_links.get("trace_ref") == rel(trace_path), "permission trace_ref mismatch")


def check_reconstruction_summary(
    scenario: ScenarioArtifacts,
    packet: dict[str, Any],
    trace: dict[str, Any],
    eval_result: dict[str, Any],
    manifest_path: Path,
    event_path: Path,
    permission_path: Path,
    trace_path: Path,
    eval_path: Path,
) -> None:
    join_order = require_json_list(packet.get("join_order"), "join_order must be a list")
    require(len(join_order) == 6, "expected six join steps")
    require(
        [step["step"] for step in join_order if isinstance(step, dict)] == [1, 2, 3, 4, 5, 6],
        "bad join step ordering",
    )

    evidence_summary = require_json_object(packet.get("evidence_summary"), "packet evidence_summary must be an object")
    refs = {
        "manifest": rel(manifest_path),
        "event": rel(event_path),
        "permission": rel(permission_path),
        "trace": rel(trace_path),
        "replay_state": scenario.expected_replay_state_ref,
        "eval": rel(eval_path),
    }
    statuses = {
        "permission": scenario.expected_permission_evidence_status,
        "trace": scenario.expected_trace_evidence_status,
        "replay_state": scenario.expected_replay_state_evidence_status,
        "eval": scenario.expected_eval_evidence_status,
    }
    for key, expected_ref in refs.items():
        evidence = require_json_object(evidence_summary[key], f"{key} evidence must be an object")
        ref_message = "replay state ref mismatch" if key == "replay_state" else f"{key} evidence ref mismatch"
        require(evidence.get("ref") == expected_ref, ref_message)
        if key in statuses:
            require(evidence.get("status") == statuses[key], f"{key} evidence status mismatch")

    eval_summary = require_json_object(packet.get("eval_summary"), "packet eval_summary must be an object")
    metrics = require_json_object(eval_result.get("metrics"), "eval metrics must be an object")
    for key in ("expected_findings", "actual_findings", "blocking_evidence_loss_count"):
        require(eval_summary.get(key) == metrics.get(key), f"eval summary mismatch for {key}")
    require(eval_summary.get("status") == eval_result.get("status"), "eval summary status mismatch")
    require(eval_result.get("status") == scenario.expected_eval_status, "eval status mismatch")

    replay = require_json_object(trace.get("replay"), "trace replay must be an object")
    replay_summary = require_json_object(packet.get("replay_summary"), "packet replay_summary must be an object")
    require(replay_summary.get("deterministic") == replay.get("deterministic"), "replay deterministic mismatch")


def check_replay_semantics(
    scenario: ScenarioArtifacts,
    event: dict[str, Any],
    trace: dict[str, Any],
    packet: dict[str, Any],
    state_path: Path,
) -> None:
    replay = require_json_object(trace.get("replay"), "trace replay must be an object")
    replay_summary = require_json_object(packet.get("replay_summary"), "packet replay_summary must be an object")
    require(replay.get("status") == scenario.expected_replay_status, "trace replay status mismatch")

    if scenario.requires_sqlite_state:
        require(packet.get("replay_handle") == replay.get("handle"), "replay handle mismatch")
        require(replay_summary.get("state_ref") == replay.get("state_ref"), "replay state_ref mismatch")
        require(
            scenario.expected_replay_state_ref == CANONICAL_STATE_REF,
            "ready scenario must use canonical state ref",
        )
        require(state_path.exists(), "generated SQLite state is required")
        check_sqlite_state(scenario, event, packet, state_path)
        return

    require(packet.get("replay_handle") is None, "blocked reconstruction must not claim a replay handle")
    require(event.get("replay_handle") is None, "blocked event must not claim a replay handle")
    require(replay_summary.get("state_ref") is None, "blocked replay_summary state_ref must be null")
    for field in scenario.expected_blocking_loss_fields:
        if field == "replay_handle":
            event_loss = require_json_list(event.get("evidence_loss"), "event evidence_loss must be a list")
            require(has_blocking_loss(event_loss, field), "event must record replay_handle evidence loss")
        elif field == "replay.state_ref":
            trace_loss = require_json_list(trace.get("evidence_loss"), "trace evidence_loss must be a list")
            require(has_blocking_loss(trace_loss, field), "trace must record replay.state_ref evidence loss")


def check_sqlite_state(
    scenario: ScenarioArtifacts,
    event: dict[str, Any],
    packet: dict[str, Any],
    state_path: Path,
) -> None:
    connection = sqlite3.connect(state_path)
    try:
        finding_count = scalar(
            connection,
            "SELECT COUNT(*) FROM findings WHERE trace_id = ? AND event_id = ?",
            (event["trace_id"], event["event_id"]),
        )
        replay_summary = require_json_object(packet.get("replay_summary"), "replay_summary must be an object")
        require(replay_summary.get("finding_count") == finding_count, "replay finding count mismatch")

        event_count = scalar(
            connection,
            "SELECT COUNT(*) FROM events WHERE event_id = ? AND trace_id = ?",
            (event["event_id"], event["trace_id"]),
        )
        require(event_count == 1, f"{scenario.name} event missing in SQLite state")

        eval_count = scalar(
            connection,
            "SELECT COUNT(*) FROM evals WHERE eval_id = ? AND status = ?",
            (packet["eval_id"], "passed"),
        )
        require(eval_count == 1, f"{scenario.name} eval missing in SQLite state")
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        action="append",
        choices=scenario_names(),
        help="Scenario to validate. May be passed more than once. Defaults to all scenarios.",
    )
    args = parser.parse_args()

    names = tuple(args.scenario) if args.scenario else scenario_names()
    for name in names:
        check_scenario(get_scenario(name))

    print("Reconstruction packet checks passed")


if __name__ == "__main__":
    main()
