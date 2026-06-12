"""Check the local tool permission packet against OPA and joined artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from oep_permissions.paths import EXPECTED_SCHEMA_TITLE

from oep_verify.verify_support import (
    eval_opa_decision,
    load_json_object,
    require,
    require_datetime_not_after,
    require_json_object,
    validate_json_schema,
)

ROOT = Path(__file__).resolve().parents[2]

PACKET_SCHEMA_PATH = ROOT / "permissions" / "schema" / "tool_permission_packet.v0.schema.json"
PACKET_EXAMPLE_PATH = ROOT / "permissions" / "examples" / "code_review_tool_permission.v0.json"
POLICY_PATH = ROOT / "permissions" / "policy" / "tool_permissions.rego"
INPUT_PATH = ROOT / "permissions" / "policy" / "input" / "code_review_read_diff.json"
EVENT_EXAMPLE_PATH = ROOT / "events" / "examples" / "code_review_agent_step.v0.json"
MANIFEST_EXAMPLE_PATH = ROOT / "manifest" / "examples" / "code_review_agent_release.v0.json"


def opa_decision() -> dict[str, Any]:
    return eval_opa_decision(POLICY_PATH, INPUT_PATH, "permission packet validation")


def main() -> None:
    schema = load_json_object(PACKET_SCHEMA_PATH)
    packet = load_json_object(PACKET_EXAMPLE_PATH)
    validate_json_schema(schema, packet, instance_path=PACKET_EXAMPLE_PATH)
    policy_input = load_json_object(INPUT_PATH)
    event = load_json_object(EVENT_EXAMPLE_PATH)
    manifest = load_json_object(MANIFEST_EXAMPLE_PATH)

    require(schema.get("title") == EXPECTED_SCHEMA_TITLE, "bad schema")
    require(packet.get("schema_version") == "oep.tool_permission_packet.v0", "bad packet schema_version")
    require(packet.get("release_manifest_id") == manifest.get("manifest_id"), "manifest join mismatch")
    require(packet.get("release_manifest_id") == event.get("release_manifest_id"), "event manifest mismatch")
    require(packet.get("event_id") == event.get("event_id"), "event_id join mismatch")
    require(packet.get("tool_call_id") == event.get("tool_call_id"), "tool_call_id join mismatch")
    require(packet.get("trace_id") == event.get("trace_id"), "trace_id join mismatch")
    require(packet.get("span_id") == event.get("span_id"), "span_id join mismatch")
    require(event.get("permission_packet_ref") == packet.get("packet_id"), "event packet ref mismatch")
    require_datetime_not_after(
        manifest.get("created_at"),
        packet.get("decision_time"),
        "manifest.created_at",
        "permission.decision_time",
    )
    require_datetime_not_after(
        packet.get("decision_time"),
        event.get("event_time"),
        "permission.decision_time",
        "event.event_time",
    )

    for key in ("release_manifest_id", "event_id", "tool_call_id", "trace_id", "span_id"):
        require(packet.get(key) == policy_input.get(key), f"policy input mismatch for {key}")
    require(packet.get("actor") == policy_input.get("actor"), "policy input actor mismatch")
    require(packet.get("tool") == policy_input.get("tool"), "policy input tool mismatch")
    require(packet.get("resource") == policy_input.get("resource"), "policy input resource mismatch")

    requested_action = require_json_object(packet.get("requested_action"), "packet requested_action must be an object")
    input_action = require_json_object(policy_input.get("action"), "policy input action must be an object")
    event_action = require_json_object(event.get("action"), "event action must be an object")
    for key in ("action_type", "name", "input_ref"):
        require(requested_action.get(key) == input_action.get(key), f"policy input action mismatch for {key}")
        require(requested_action.get(key) == event_action.get(key), f"event action mismatch for {key}")

    decision = require_json_object(packet.get("decision"), "packet decision must be an object")
    policy = require_json_object(packet.get("policy"), "packet policy must be an object")

    opa = opa_decision()
    require(decision.get("allow") == opa.get("allow"), "OPA allow mismatch")
    require(decision.get("reason") == opa.get("reason"), "OPA reason mismatch")
    require(decision.get("matched_rule") == opa.get("matched_rule"), "OPA matched_rule mismatch")
    require(policy.get("policy_id") == opa.get("policy_id"), "OPA policy_id mismatch")
    require(policy.get("policy_version") == opa.get("policy_version"), "OPA policy_version mismatch")

    print("Tool permission packet checks passed")


if __name__ == "__main__":
    main()
