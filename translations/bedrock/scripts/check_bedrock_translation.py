"""Check the Bedrock translation example against core artifact IDs."""

from __future__ import annotations

from pathlib import Path

from oep_verify.verify_support import (
    load_json_object,
    require,
    require_json_list,
    require_json_object,
    validate_json_schema,
)

ROOT = Path(__file__).resolve().parents[3]

TRANSLATION_PATH = ROOT / "translations" / "bedrock" / "examples" / "code_review_bedrock_translation.v0.json"
SCHEMA_PATH = ROOT / "translations" / "bedrock" / "schema" / "bedrock_translation.v0.schema.json"
MANIFEST_PATH = ROOT / "manifest" / "examples" / "code_review_agent_release.v0.json"
EVENT_PATH = ROOT / "events" / "examples" / "code_review_agent_step.v0.json"
PERMISSION_PATH = ROOT / "permissions" / "examples" / "code_review_tool_permission.v0.json"
TRACE_PATH = ROOT / "traces" / "examples" / "code_review_agent_trace.v0.json"
EVAL_PATH = ROOT / "traces" / "examples" / "code_review_agent_eval.v0.json"
RECONSTRUCTION_PATH = ROOT / "playbooks" / "examples" / "code_review_reconstruction_packet.v0.json"

EXPECTED_LAYERS = {
    "model",
    "prompt",
    "tool_schema",
    "policy",
    "workflow",
    "rollout",
    "eval",
    "data_state",
}


def main() -> None:
    schema = load_json_object(SCHEMA_PATH)
    translation = load_json_object(TRANSLATION_PATH)
    validate_json_schema(schema, translation, instance_path=TRANSLATION_PATH)
    manifest = load_json_object(MANIFEST_PATH)
    event = load_json_object(EVENT_PATH)
    permission = load_json_object(PERMISSION_PATH)
    trace = load_json_object(TRACE_PATH)
    eval_result = load_json_object(EVAL_PATH)
    reconstruction = load_json_object(RECONSTRUCTION_PATH)

    require(schema.get("title") == "Operational Evidence Plane Bedrock Translation v0", "bad schema")
    require(translation.get("schema_version") == "oep.bedrock_translation.v0", "bad schema_version")
    require(translation.get("source_checked_at") == "2026-05-04", "source date mismatch")

    core_refs = require_json_object(translation.get("core_refs"), "core_refs must be an object")
    require(core_refs.get("release_manifest_id") == manifest.get("manifest_id"), "manifest ref mismatch")
    require(core_refs.get("event_id") == event.get("event_id"), "event ref mismatch")
    require(core_refs.get("permission_packet_id") == permission.get("packet_id"), "permission ref mismatch")
    require(core_refs.get("trace_id") == trace.get("trace_id"), "trace ref mismatch")
    require(core_refs.get("eval_id") == eval_result.get("eval_id"), "eval ref mismatch")
    require(core_refs.get("reconstruction_packet_id") == reconstruction.get("packet_id"), "reconstruction ref mismatch")

    layer_mapping = require_json_list(translation.get("layer_mapping"), "layer_mapping must be a list")
    layers = {item.get("oep_layer") for item in layer_mapping if isinstance(item, dict)}
    require(layers == EXPECTED_LAYERS, "layer mapping mismatch")

    source_urls = require_json_list(translation.get("source_urls"), "source_urls must be a list")
    require(len(source_urls) > 0, "source_urls must be a non-empty list")
    require(
        all(isinstance(url, str) and url.startswith("https://docs.aws.amazon.com/") for url in source_urls),
        "sources must be official AWS docs",
    )

    non_goals = require_json_list(translation.get("non_goals"), "non_goals must be a list")
    require(any("No AWS calls" in item for item in non_goals), "translation must stay non-executable")

    print("Bedrock translation checks passed")


if __name__ == "__main__":
    main()
