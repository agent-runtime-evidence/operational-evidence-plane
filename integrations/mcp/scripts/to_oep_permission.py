#!/usr/bin/env python3
"""Project a synthetic MCP `tools/call` envelope into an OEP permission packet.

This adapter is documentation and mapping data, not a replacement for
MCP, OPA, LangSmith, or Bedrock. It shows one inspectable way to
translate a JSON-RPC `tools/call` envelope into the OEP
`tool_permission_packet.v0` schema, including the v0.2 replayable
permission trace fields.

Usage:
    python integrations/mcp/scripts/to_oep_permission.py \\
        --mcp-event integrations/mcp/examples/code_review_mcp_tool_call.v0.json \\
        --compare-with permissions/examples/code_review_tool_permission.v0.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from oep_verify.verify_support import load_json_object, validate_json_schema

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MCP_EVENT = REPO_ROOT / "integrations" / "mcp" / "examples" / "code_review_mcp_tool_call.v0.json"
DEFAULT_COMPARE = REPO_ROOT / "permissions" / "examples" / "code_review_tool_permission.v0.json"
DEFAULT_SCHEMA = REPO_ROOT / "permissions" / "schema" / "tool_permission_packet.v0.schema.json"

OEP_SCHEMA_VERSION = "oep.tool_permission_packet.v0"


def _required(value: Any, field: str) -> Any:
    if value is None:
        raise SystemExit(f"MCP envelope missing required field: {field}")
    return value


def project_to_oep_permission(mcp_event: dict[str, Any]) -> dict[str, Any]:
    """Translate an MCP tools/call envelope to an OEP permission packet."""

    session = _required(mcp_event.get("session"), "session")
    request = _required(mcp_event.get("request"), "request")
    response = _required(mcp_event.get("response"), "response")
    params = _required(request.get("params"), "request.params")
    result = _required(response.get("result"), "response.result")
    model_binding = session.get("model_binding") or {}

    arguments = params.get("arguments")
    if isinstance(arguments, dict):
        input_ref = arguments.get("uri") or arguments.get("input_ref")
    else:
        input_ref = arguments

    return {
        "schema_version": OEP_SCHEMA_VERSION,
        "packet_id": _required(session.get("packet_id"), "session.packet_id"),
        "decision_time": _required(session.get("decision_time"), "session.decision_time"),
        "release_manifest_id": _required(
            session.get("release_manifest_id"), "session.release_manifest_id"
        ),
        "event_id": _required(session.get("event_id"), "session.event_id"),
        "tool_call_id": _required(request.get("id"), "request.id"),
        "trace_id": _required(session.get("trace_id"), "session.trace_id"),
        "span_id": _required(session.get("span_id"), "session.span_id"),
        "actor": _required(mcp_event.get("actor"), "actor"),
        "requested_action": {
            "action_type": _required(params.get("action_type"), "request.params.action_type"),
            "name": _required(params.get("action_name"), "request.params.action_name"),
            "input_ref": _required(input_ref, "request.params.arguments"),
        },
        "tool": {
            "name": _required(params.get("name"), "request.params.name"),
            "version": _required(params.get("tool_version"), "request.params.tool_version"),
            "operation": _required(params.get("operation"), "request.params.operation"),
        },
        "resource": _required(params.get("resource"), "request.params.resource"),
        "policy": _required(result.get("policy_ref"), "response.result.policy_ref"),
        "decision": _required(result.get("decision"), "response.result.decision"),
        "scoped_credential_lifetime": session.get("scoped_credential_lifetime"),
        "approval_capture": session.get("approval_capture"),
        "policy_bundle_version": session.get("policy_bundle_version"),
        "release_manifest_version": session.get("release_manifest_version"),
        "model_alias": model_binding.get("alias"),
        "resolved_model_version": model_binding.get("resolved_version"),
        "model_provider": model_binding.get("provider"),
        "links": _required(result.get("links"), "response.result.links"),
        "claim_boundary": _required(session.get("claim_boundary"), "session.claim_boundary"),
    }


def _stable_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2) + "\n"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise SystemExit(f"expected JSON object at {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mcp-event",
        type=Path,
        default=DEFAULT_MCP_EVENT,
        help="Path to a synthetic MCP tools/call envelope JSON file.",
    )
    parser.add_argument(
        "--compare-with",
        type=Path,
        default=DEFAULT_COMPARE,
        help=(
            "Optional path to a canonical OEP permission packet to compare the "
            "projection against. The script exits non-zero on drift."
        ),
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA,
        help=(
            "Path to the OEP tool permission packet JSON Schema. Used to "
            "validate the projection (and the canonical comparison file) "
            "as a defense-in-depth check before byte-comparing."
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional output path for the projected OEP permission packet.",
    )
    args = parser.parse_args()

    mcp_event = _load_json(args.mcp_event)
    projected = project_to_oep_permission(mcp_event)

    schema = load_json_object(args.schema)
    validate_json_schema(schema, projected, instance_path=args.mcp_event)

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_stable_json(projected), encoding="utf-8")

    if args.compare_with is not None:
        canonical = _load_json(args.compare_with)
        validate_json_schema(schema, canonical, instance_path=args.compare_with)
        if projected != canonical:
            raise SystemExit(
                "MCP -> OEP projection drift: projected packet does not match "
                f"{args.compare_with.relative_to(REPO_ROOT) if args.compare_with.is_absolute() else args.compare_with}"
            )

    print("MCP -> OEP permission packet projection checks passed")


if __name__ == "__main__":
    main()
