"""Check the local agent step event example against schema and joins."""

from __future__ import annotations

from pathlib import Path

from oep_verify.verify_support import (
    load_json_object,
    require,
    require_datetime_not_after,
    require_json_list,
    require_json_object,
    require_string,
    validate_json_schema,
)

ROOT = Path(__file__).resolve().parents[2]

EVENT_SCHEMA_PATH = ROOT / "events" / "schema" / "agent_step_event.v0.schema.json"
EVENT_EXAMPLE_PATH = ROOT / "events" / "examples" / "code_review_agent_step.v0.json"
MANIFEST_EXAMPLE_PATH = ROOT / "manifest" / "examples" / "code_review_agent_release.v0.json"
PERMISSION_EXAMPLE_PATH = ROOT / "permissions" / "examples" / "code_review_tool_permission.v0.json"

EXPECTED_EVIDENCE_KEYS = {
    "release_manifest",
    "trace",
    "permission",
    "replay",
    "eval",
}


def main() -> None:
    schema = load_json_object(EVENT_SCHEMA_PATH)
    event = load_json_object(EVENT_EXAMPLE_PATH)
    validate_json_schema(schema, event, instance_path=EVENT_EXAMPLE_PATH)
    manifest = load_json_object(MANIFEST_EXAMPLE_PATH)
    permission_packet = load_json_object(PERMISSION_EXAMPLE_PATH)

    require(schema.get("title") == "Operational Evidence Plane Agent Step Event v0", "bad schema")
    require(event.get("schema_version") == "oep.agent_step_event.v0", "bad event schema_version")
    require(event.get("release_manifest_id") == manifest.get("manifest_id"), "manifest join mismatch")
    require_datetime_not_after(
        manifest.get("created_at"),
        event.get("event_time"),
        "manifest.created_at",
        "event.event_time",
    )

    runtime_rules = require_json_object(
        manifest.get("runtime_join_rules"),
        "manifest runtime_join_rules must be an object",
    )
    for manifest_field in (
        "release_manifest_id_field",
        "trace_id_field",
        "span_id_field",
        "tool_call_id_field",
        "replay_handle_field",
    ):
        event_field = require_string(runtime_rules[manifest_field], f"{manifest_field} must resolve to a field name")
        require(event_field in event, f"event missing manifest-reserved field {event_field}")

    permission_schema_ref = require_string(
        runtime_rules["permission_packet_ref"],
        "permission_packet_ref must resolve to a schema ref",
    )
    require(permission_schema_ref.startswith("permissions/schema/"), "bad permission schema ref")
    require("permission_packet_ref" in event, "event missing permission_packet_ref field")

    evidence_status = require_json_object(event.get("evidence_status"), "evidence_status must be an object")
    require(set(evidence_status) == EXPECTED_EVIDENCE_KEYS, "evidence_status key mismatch")

    permission_ref = event.get("permission_packet_ref")
    require(permission_ref == permission_packet.get("packet_id"), "permission packet join mismatch")
    require(evidence_status.get("permission") == "present", "permission must be present")

    evidence_loss = require_json_list(event.get("evidence_loss"), "evidence_loss must be a list")
    require(
        not any(isinstance(item, dict) and item.get("field") == "permission_packet_ref" for item in evidence_loss),
        "present permission ref must not have a permission evidence-loss note",
    )

    print("Agent step event checks passed")


if __name__ == "__main__":
    main()
