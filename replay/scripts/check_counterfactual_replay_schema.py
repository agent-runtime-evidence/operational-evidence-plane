"""Validate the counterfactual replay schema and additive permission cache field."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from oep_verify.verify_support import load_json_object, validate_json_schema

ROOT = Path(__file__).resolve().parents[2]

COUNTERFACTUAL_SCHEMA_PATH = ROOT / "replay" / "counterfactual_replay.v0.schema.json"
PERMISSION_SCHEMA_PATH = ROOT / "permissions" / "schema" / "tool_permission_packet.v0.schema.json"
PERMISSION_EXAMPLE_PATHS = (
    ROOT / "permissions" / "examples" / "code_review_tool_permission.v0.json",
    ROOT / "permissions" / "examples" / "code_review_tool_permission_denied.v0.json",
)


def counterfactual_replay_example() -> dict[str, Any]:
    return {
        "schema_version": "oep.counterfactual_replay.v0",
        "decision_id": "pder_code_review_read_diff_0001",
        "replay_mode": "counterfactual",
        "original": {
            "policy_bundle_version": "sha256:e0d5563e9e046960f5435ab1e00f26df8925e16ca7a207ee37df65b7151bcb27",
            "decision": "allow",
            "rationale": "reference code review agent may inspect an immutable synthetic diff",
            "matched_rules": ["allow_reference_code_review_diff_read"],
        },
        "counterfactual": {
            "policy_bundle_version": "counterfactual_policy_bundle_v0_3_demo",
            "decision": "deny",
            "rationale": "counterfactual policy blocks the stored decision after substitution",
            "matched_rules": ["deny_counterfactual_policy_substitution"],
            "decision_code": "COUNTERFACTUAL_POLICY_DENY",
        },
        "diff": {
            "decision_changed": True,
            "rationale_changed": True,
            "rule_set_delta": {
                "added": ["deny_counterfactual_policy_substitution"],
                "removed": ["allow_reference_code_review_diff_read"],
                "unchanged": [],
            },
            "workflow_delta": None,
            "budget_delta": None,
            "approval_delta": None,
        },
        "replay_metadata": {
            "oep_replay_mode": "counterfactual",
            "nd_builtin_cache_entries_used": 1,
            "replay_timestamp_utc": "2026-05-23T00:00:00Z",
            "determinism_exclusions": ["replay_metadata.replay_timestamp_utc"],
        },
        "claim_boundary": (
            "This record is an inspectable counterfactual policy replay output for the reference demo. "
            "It is not a production-grade replay engine, compliance certification, or legal/regulatory "
            "adequacy claim."
        ),
    }


def main() -> None:
    counterfactual_schema = load_json_object(COUNTERFACTUAL_SCHEMA_PATH)
    permission_schema = load_json_object(PERMISSION_SCHEMA_PATH)

    validate_json_schema(
        counterfactual_schema,
        counterfactual_replay_example(),
        instance_path=COUNTERFACTUAL_SCHEMA_PATH,
    )

    for example_path in PERMISSION_EXAMPLE_PATHS:
        packet = load_json_object(example_path)
        validate_json_schema(permission_schema, packet, instance_path=example_path)

        packet_with_cache = copy.deepcopy(packet)
        packet_with_cache["nd_builtin_cache"] = {
            "time.now_ns": {
                "[]": 1777852800000000000,
            }
        }
        validate_json_schema(permission_schema, packet_with_cache, instance_path=example_path)

    print("Counterfactual replay schema checks passed")


if __name__ == "__main__":
    main()
