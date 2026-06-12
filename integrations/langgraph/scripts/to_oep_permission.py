#!/usr/bin/env python3
"""Project a synthetic LangGraph checkpoint envelope into an OEP permission packet.

This adapter is documentation and mapping data, not a replacement for
LangGraph, LangSmith, OPA, OTel, or any agent framework. It shows one
inspectable way to translate a LangGraph checkpoint event (extended by a
thin wrapper layer with the operational evidence fields LangGraph does
not natively bind) into the OEP `tool_permission_packet.v0` schema,
including the v0.2 replayable permission trace fields and the v0.3
`decision_id` metadata.

The point made in code: LangGraph's StateSnapshot captures `values`,
`next`, `metadata`, `created_at`, and `parent_config`. It does not
natively bind model alias / resolved version, policy bundle version,
scoped credential lifetime, cache hit metadata, or release manifest
version. Substitution-class counterfactual replay against a stored
decision (OEP's `counterfactual_replay.v0` primitive) requires those
fields. The wrapper layer represented by the `wrapper` section in the
synthetic envelope is what injects them at checkpoint write time.

Usage:
    python integrations/langgraph/scripts/to_oep_permission.py \\
        --langgraph-event integrations/langgraph/examples/code_review_langgraph_checkpoint.v0.json \\
        --compare-with permissions/examples/code_review_tool_permission.v0.json
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from oep_verify.verify_support import (
    load_json_object,
    load_json_object_or_exit,
    required_field,
    stable_json,
    validate_json_schema,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LG_EVENT = REPO_ROOT / "integrations" / "langgraph" / "examples" / "code_review_langgraph_checkpoint.v0.json"
DEFAULT_COMPARE = REPO_ROOT / "permissions" / "examples" / "code_review_tool_permission.v0.json"
DEFAULT_SCHEMA = REPO_ROOT / "permissions" / "schema" / "tool_permission_packet.v0.schema.json"

OEP_SCHEMA_VERSION = "oep.tool_permission_packet.v0"


def _required(value: Any, field: str) -> Any:
    return required_field(value, field, "LangGraph envelope")


def project_to_oep_permission(lg_event: dict[str, Any]) -> dict[str, Any]:
    """Translate a LangGraph checkpoint envelope to an OEP permission packet.

    The synthetic envelope carries two top-level sections:

    * `langgraph.state_snapshot.values.*` — state channel values bound
      by LangGraph at checkpoint time (tool, requested_action, resource).
      These project directly to the OEP tool-call surface.

    * `wrapper.*` — operational evidence fields the wrapper injects at
      checkpoint write time because LangGraph's StateSnapshot does not
      bind them natively (actor, session metadata including identifiers,
      version bindings, scoped credential lifetime, approval capture,
      claim boundary, decision_id composite, and the captured OPA
      policy response). These provide the rest of the OEP record.
    """

    langgraph = _required(lg_event.get("langgraph"), "langgraph")
    state_snapshot = _required(langgraph.get("state_snapshot"), "langgraph.state_snapshot")
    values = _required(state_snapshot.get("values"), "langgraph.state_snapshot.values")
    tool = _required(values.get("tool"), "langgraph.state_snapshot.values.tool")
    requested_action = _required(values.get("requested_action"), "langgraph.state_snapshot.values.requested_action")
    resource = _required(values.get("resource"), "langgraph.state_snapshot.values.resource")

    wrapper = _required(lg_event.get("wrapper"), "wrapper")
    actor = _required(wrapper.get("actor"), "wrapper.actor")
    session = _required(wrapper.get("session"), "wrapper.session")
    policy_response = _required(wrapper.get("policy_response"), "wrapper.policy_response")
    model_binding = session.get("model_binding") or {}

    return {
        "schema_version": OEP_SCHEMA_VERSION,
        "packet_id": _required(session.get("packet_id"), "wrapper.session.packet_id"),
        "decision_time": _required(session.get("decision_time"), "wrapper.session.decision_time"),
        "release_manifest_id": _required(session.get("release_manifest_id"), "wrapper.session.release_manifest_id"),
        "event_id": _required(session.get("event_id"), "wrapper.session.event_id"),
        "tool_call_id": _required(session.get("tool_call_id"), "wrapper.session.tool_call_id"),
        "trace_id": _required(session.get("trace_id"), "wrapper.session.trace_id"),
        "span_id": _required(session.get("span_id"), "wrapper.session.span_id"),
        "actor": actor,
        "requested_action": {
            "action_type": _required(
                requested_action.get("action_type"),
                "langgraph.state_snapshot.values.requested_action.action_type",
            ),
            "name": _required(
                requested_action.get("name"),
                "langgraph.state_snapshot.values.requested_action.name",
            ),
            "input_ref": _required(
                requested_action.get("input_ref"),
                "langgraph.state_snapshot.values.requested_action.input_ref",
            ),
        },
        "tool": {
            "name": _required(tool.get("name"), "langgraph.state_snapshot.values.tool.name"),
            "version": _required(tool.get("version"), "langgraph.state_snapshot.values.tool.version"),
            "operation": _required(tool.get("operation"), "langgraph.state_snapshot.values.tool.operation"),
        },
        "resource": resource,
        "policy": _required(policy_response.get("policy_ref"), "wrapper.policy_response.policy_ref"),
        "decision": _required(policy_response.get("decision"), "wrapper.policy_response.decision"),
        "scoped_credential_lifetime": session.get("scoped_credential_lifetime"),
        "approval_capture": session.get("approval_capture"),
        "policy_bundle_version": session.get("policy_bundle_version"),
        "release_manifest_version": session.get("release_manifest_version"),
        "model_alias": model_binding.get("alias"),
        "resolved_model_version": model_binding.get("resolved_version"),
        "model_provider": model_binding.get("provider"),
        "decision_id": session.get("decision_id"),
        "links": _required(policy_response.get("links"), "wrapper.policy_response.links"),
        "claim_boundary": _required(session.get("claim_boundary"), "wrapper.session.claim_boundary"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--langgraph-event",
        type=Path,
        default=DEFAULT_LG_EVENT,
        help="Path to a synthetic LangGraph checkpoint envelope JSON file.",
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

    lg_event = load_json_object_or_exit(args.langgraph_event)
    projected = project_to_oep_permission(lg_event)

    schema = load_json_object(args.schema)
    validate_json_schema(schema, projected, instance_path=args.langgraph_event)

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(stable_json(projected), encoding="utf-8")

    if args.compare_with is not None:
        canonical = load_json_object_or_exit(args.compare_with)
        validate_json_schema(schema, canonical, instance_path=args.compare_with)
        if projected != canonical:
            raise SystemExit(
                "LangGraph -> OEP projection drift: projected packet does not match "
                f"{args.compare_with.relative_to(REPO_ROOT) if args.compare_with.is_absolute() else args.compare_with}"
            )

    print("LangGraph -> OEP permission packet projection checks passed")


if __name__ == "__main__":
    main()
