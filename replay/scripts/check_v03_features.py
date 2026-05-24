"""Validate v0.3 replay, diff, budget, cache, and identity primitives."""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from oep_demo import run_demo
from oep_permissions.replay import (
    decision_surface_presence,
    diff_decision_surfaces,
    project_pre_session_cost,
    replay_decision_with_substitutions,
    simulate_reserve_commit_release,
)

from oep_verify.verify_support import (
    load_json_object,
    require,
    require_json_object,
    validate_json_schema_from_path,
)

ROOT = Path(__file__).resolve().parents[2]
DECISION_ID = "pder_code_review_read_diff_0001"
Q1_DECISION_ID = "pder_code_review_q1_diff_0001"
FIXED_REPLAY_TIMESTAMP = "2026-05-23T00:00:00Z"
PERMISSION_SCHEMA_PATH = ROOT / "permissions" / "schema" / "tool_permission_packet.v0.schema.json"
PERMISSION_EXAMPLE_PATH = ROOT / "permissions" / "examples" / "code_review_tool_permission.v0.json"


Check = Callable[[Path], None]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="append",
        choices=tuple(sorted(CHECKS)),
        default=None,
        help="Specific v0.3 check to run. Defaults to all checks.",
    )
    args = parser.parse_args()

    selected = args.check or tuple(sorted(CHECKS))
    with tempfile.TemporaryDirectory(prefix="oep-v03-features-") as temp_root:
        temp_path = Path(temp_root)
        for check_name in selected:
            CHECKS[check_name](temp_path / check_name)
    print(f"v0.3 feature checks passed: {', '.join(selected)}")


def check_backward_compat(root: Path) -> None:
    root.mkdir(parents=True)
    state_path = root / "state.sqlite"
    run_demo(state_path)
    _update_permission_payload(state_path, DECISION_ID, lambda packet: packet.pop("decision_id", None))

    presence = decision_surface_presence(state_path, DECISION_ID)
    require(presence["replayable"] is True, "v0.2-style record must replay")
    require(
        presence["absent_surfaces"] == ["permission", "cost", "drift", "cache", "identity"],
        "v0.2-style record must report absent v0.3 surfaces",
    )


def check_5surface_diff(root: Path) -> None:
    root.mkdir(parents=True)
    state_path = root / "state.sqlite"
    run_demo(state_path)
    _insert_q1_decision(state_path)

    diff = diff_decision_surfaces(
        state_path,
        DECISION_ID,
        Q1_DECISION_ID,
        surfaces=("model,policy,prompt,tool,corpus",),
    )
    require(diff["replay_class"] == "deterministic", "surface diff must be deterministic")
    require(
        diff["changed_surfaces"] == ["model", "policy", "prompt", "tool", "corpus"],
        "surface diff must identify all five changed surfaces",
    )
    surfaces = require_json_object(diff["surfaces"], "diff surfaces must be an object")
    require(surfaces["model"]["change_class"] == "alias_resolution", "model surface change class mismatch")
    require(surfaces["policy"]["change_class"] == "policy_update", "policy surface change class mismatch")
    require(surfaces["prompt"]["change_class"] == "prompt_edit", "prompt surface change class mismatch")
    require(surfaces["tool"]["change_class"] == "tool_added_removed", "tool surface change class mismatch")
    require(surfaces["corpus"]["change_class"] == "corpus_indexed", "corpus surface change class mismatch")

    replay = replay_decision_with_substitutions(
        state_path,
        DECISION_ID,
        substitutions={
            "prompt": "code-review-agent-prompt@0.2.0",
            "tool": "code-review-tool-registry@0.2.0",
            "corpus": "retrieval-corpus@2026-q1",
        },
        replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
    )
    surface_delta = require_json_object(replay["diff"].get("surface_delta"), "surface_delta must be present")
    require(
        surface_delta["changed_surfaces"] == ["prompt", "tool", "corpus"],
        "deterministic surface substitution must attribute prompt/tool/corpus changes",
    )
    require(replay["replay_metadata"]["replay_class"] == "deterministic", "prompt/tool/corpus replay is deterministic")


def check_cost_counterfactual(root: Path) -> None:
    root.mkdir(parents=True)
    state_path = root / "state.sqlite"
    run_demo(state_path)
    replay = replay_decision_with_substitutions(
        state_path,
        DECISION_ID,
        budget_policy="per_run_cap_usd=0.005",
        replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
    )
    require(replay["counterfactual"]["decision"] == "deny", "stricter budget must deny the recorded step")
    budget_delta = require_json_object(replay["diff"].get("budget_delta"), "budget_delta must be present")
    require(budget_delta["termination_step"] == 1, "budget replay must identify the terminating step")
    require(budget_delta["termination_code"] == "BUDGET_EXCEEDED", "budget denial code mismatch")


def check_reserve_commit_release(root: Path) -> None:
    _ = root
    result = simulate_reserve_commit_release(
        [
            {
                "budget_reservation_id": "bres_0001",
                "reservation_estimated_cost_usd": 6,
                "reservation_committed_cost_usd": 4,
            },
            {
                "budget_reservation_id": "bres_0002",
                "reservation_estimated_cost_usd": 8,
                "reservation_committed_cost_usd": 7,
            },
        ],
        budget_cap_usd=10,
    )
    require(result["first_denied_reservation_id"] == "bres_0002", "reserve lifecycle must deny the exhausting step")
    first = result["reservation_outcomes"][0]
    require(first["reservation_outcome"] == "committed", "first reservation should commit")
    require(first["reservation_excess_released_usd"] == 2, "excess release math mismatch")

    projection = project_pre_session_cost(
        projected_min_usd=4,
        projected_max_usd=9,
        budget_cap_usd=10,
        approver_identity={"type": "human", "id": "human_budget_owner", "display_name": "budget owner"},
        approve=True,
    )
    require(projection["replay_class"] == "evaluative", "projection must be labelled evaluative")
    require(projection["approval_outcome"] == "approved", "projection approval outcome mismatch")


def check_cross_provider_drift(root: Path) -> None:
    root.mkdir(parents=True)
    state_path = root / "state.sqlite"
    run_demo(state_path)
    replay = replay_decision_with_substitutions(
        state_path,
        DECISION_ID,
        model_substitute="bedrock:anthropic.claude-opus-4-6",
        replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
    )
    require(replay["replay_metadata"]["replay_class"] == "evaluative", "model substitution must be evaluative")
    model_delta = require_json_object(replay["diff"].get("model_delta"), "model_delta must be present")
    require(model_delta["counterfactual_label"] == "counterfactual estimate", "model replay label mismatch")
    require(model_delta["substituted_provider"] == "bedrock", "provider substitution mismatch")


def check_cache_substitution(root: Path) -> None:
    root.mkdir(parents=True)
    state_path = root / "state.sqlite"
    run_demo(state_path)
    _update_permission_payload(state_path, DECISION_ID, _mark_cache_stale)
    replay = replay_decision_with_substitutions(
        state_path,
        DECISION_ID,
        cache_policy="staleness",
        replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
    )
    cache_delta = require_json_object(replay["diff"].get("cache_delta"), "cache_delta must be present")
    require(cache_delta["would_reject_cached_hit"] is True, "stale cache hit must be rejected")
    require(cache_delta["fresh_call_required"] is True, "stale cache hit must require a fresh call")
    require(replay["replay_metadata"]["replay_class"] == "deterministic", "staleness policy replay is deterministic")

    evaluative = replay_decision_with_substitutions(
        state_path,
        DECISION_ID,
        cache_policy="embedding_version=different-embedding-model",
        replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
    )
    require(evaluative["replay_metadata"]["replay_class"] == "evaluative", "embedding substitution must be evaluative")


def check_identity_binding(root: Path) -> None:
    _ = root
    schema = load_json_object(PERMISSION_SCHEMA_PATH)
    packet = load_json_object(PERMISSION_EXAMPLE_PATH)
    validate_json_schema_from_path(PERMISSION_SCHEMA_PATH, packet, instance_path=PERMISSION_EXAMPLE_PATH)
    validate_json_schema_from_path(PERMISSION_SCHEMA_PATH, _v02_packet(packet), instance_path=PERMISSION_EXAMPLE_PATH)
    corrupted_packet = json.loads(json.dumps(packet, sort_keys=True))
    corrupted_decision_id = require_json_object(corrupted_packet.get("decision_id"), "decision_id must be present")
    corrupted_cost = require_json_object(corrupted_decision_id.get("cost"), "decision_id.cost must be present")
    corrupted_cost["budget_reservation_id"] = "bad-prefix-0001"
    try:
        validate_json_schema_from_path(PERMISSION_SCHEMA_PATH, corrupted_packet, instance_path=PERMISSION_EXAMPLE_PATH)
    except ValueError:
        pass
    else:
        raise ValueError("v0.3 schema must reject malformed budget reservation identifiers")

    decision_id = require_json_object(packet.get("decision_id"), "packet decision_id must be an object")
    identity = require_json_object(decision_id.get("identity"), "decision_id.identity must be an object")
    require(identity["agent_identity"] == packet["actor"], "agent identity must bind to the permission actor")
    require(identity["policy_version"] == packet["policy"]["policy_version"], "identity must carry policy version")
    require("id_jag_binding" in identity, "identity must include an ID-JAG binding")
    require(schema["properties"]["decision_id"]["oneOf"][1]["$ref"] == "#/$defs/decision_id_metadata", "bad schema")


def check_composite(root: Path) -> None:
    root.mkdir(parents=True)
    state_path = root / "state.sqlite"
    run_demo(state_path)
    deny_policy_path = _write_deny_policy(root)
    replay = replay_decision_with_substitutions(
        state_path,
        DECISION_ID,
        substitutions={"policy": str(deny_policy_path)},
        budget_policy="per_run_cap_usd=0.005",
        model_substitute="bedrock:anthropic.claude-opus-4-6",
        replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
    )
    require(replay["replay_metadata"]["replay_class"] == "evaluative", "composite replay must be evaluative")
    substituted = require_json_object(
        replay["replay_metadata"].get("substituted_surfaces"),
        "substituted surfaces must be present",
    )
    require(set(substituted) == {"policy", "budget", "model"}, "composite replay must record all substitutions")
    require(replay["counterfactual"]["decision"] == "deny", "composite replay must produce a coherent denial")
    require("surface_delta" in replay["diff"], "composite replay must include surface attribution")
    require("budget_delta" in replay["diff"], "composite replay must include budget attribution")
    require("model_delta" in replay["diff"], "composite replay must include model attribution")


def _insert_q1_decision(state_path: Path) -> None:
    with sqlite3.connect(state_path) as connection:
        connection.row_factory = sqlite3.Row
        permission_row = connection.execute(
            "SELECT * FROM permissions WHERE packet_id = ?",
            (DECISION_ID,),
        ).fetchone()
        event_row = connection.execute(
            "SELECT * FROM events WHERE event_id = ?",
            (permission_row["event_id"],),
        ).fetchone()
        packet = json.loads(permission_row["payload_json"])
        event = json.loads(event_row["payload_json"])

        packet["packet_id"] = Q1_DECISION_ID
        packet["event_id"] = "evt_code_review_q1_step_0001"
        packet["tool_call_id"] = "tool_q1_read_diff_0001"
        packet["span_id"] = "3333333333333333"
        packet["decision_time"] = "2026-05-04T00:00:02Z"
        packet["decision_id"]["drift"] = _q1_drift()
        packet["decision_id"]["permission"]["permission_packet_ref"] = Q1_DECISION_ID
        packet["decision_id"]["permission"]["tool_call_id"] = "tool_q1_read_diff_0001"

        event["event_id"] = "evt_code_review_q1_step_0001"
        event["tool_call_id"] = "tool_q1_read_diff_0001"
        event["span_id"] = "3333333333333333"
        event["permission_packet_ref"] = Q1_DECISION_ID

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
                json.dumps(event, sort_keys=True, separators=(",", ":")),
            ),
        )
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
                packet["packet_id"],
                packet["event_id"],
                packet["tool_call_id"],
                packet["trace_id"],
                packet["span_id"],
                int(packet["decision"]["allow"]),
                packet["decision"]["reason"],
                json.dumps(packet, sort_keys=True, separators=(",", ":")),
            ),
        )


def _q1_drift() -> dict[str, Any]:
    return {
        "model_version": {
            "before_version": "deterministic-mock-reviewer@0.1.0",
            "after_version": "deterministic-mock-reviewer@0.2.0",
            "change_class": "alias_resolution",
            "attribution_confidence": 1,
        },
        "policy_bundle": {
            "before_version": "sha256:e0d5563e9e046960f5435ab1e00f26df8925e16ca7a207ee37df65b7151bcb27",
            "after_version": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
            "change_class": "policy_update",
            "attribution_confidence": 1,
        },
        "prompt_template": {
            "before_version": "code-review-agent-prompt@0.1.0",
            "after_version": "code-review-agent-prompt@0.2.0",
            "change_class": "prompt_edit",
            "attribution_confidence": 1,
        },
        "tool_registry": {
            "before_version": "code-review-tool-registry@0.1.0",
            "after_version": "code-review-tool-registry@0.2.0",
            "change_class": "tool_added_removed",
            "attribution_confidence": 1,
        },
        "retrieval_corpus": {
            "before_version": "no-retrieval-corpus@0.1.0",
            "after_version": "retrieval-corpus@2026-q1",
            "change_class": "corpus_indexed",
            "attribution_confidence": 1,
        },
    }


def _update_permission_payload(state_path: Path, packet_id: str, update: Callable[[dict[str, Any]], object]) -> None:
    with sqlite3.connect(state_path) as connection:
        row = connection.execute(
            "SELECT payload_json FROM permissions WHERE packet_id = ?",
            (packet_id,),
        ).fetchone()
        if row is None:
            raise AssertionError(f"missing permission packet in fixture: {packet_id}")
        packet = json.loads(row[0])
        update(packet)
        payload = json.dumps(packet, sort_keys=True, separators=(",", ":"))
        connection.execute("UPDATE permissions SET payload_json = ? WHERE packet_id = ?", (payload, packet_id))
        connection.execute(
            """
            UPDATE artifacts
            SET payload_json = ?
            WHERE kind = 'tool_permission_packet' AND artifact_id = ?
            """,
            (payload, packet_id),
        )


def _mark_cache_stale(packet: dict[str, Any]) -> None:
    decision_id = require_json_object(packet.get("decision_id"), "decision_id must be present")
    cache = require_json_object(decision_id.get("cache"), "cache surface must be present")
    cache["cache_hit_id"] = "cache_code_review_hit_stale_0001"
    cache["cache_correctness_status"] = "stale"
    cache["staleness_flag"] = True
    cache["similarity_score"] = 0.91


def _v02_packet(packet: dict[str, Any]) -> dict[str, Any]:
    copy = json.loads(json.dumps(packet, sort_keys=True))
    copy.pop("decision_id", None)
    return copy


def _write_deny_policy(root: Path) -> Path:
    policy_path = root / "deny_policy.rego"
    policy_path.write_text(
        """
package oep.permissions

decision := {
    "allow": false,
    "matched_rule": "deny_v03_composite_policy_substitution",
    "policy_id": "opa-tool-permission-policy",
    "policy_version": "0.3-composite-test",
    "reason": "counterfactual policy blocks the stored decision after substitution",
    "decision_code": "COUNTERFACTUAL_POLICY_DENY",
}
""",
        encoding="utf-8",
    )
    return policy_path


CHECKS: dict[str, Check] = {
    "5surface": check_5surface_diff,
    "backward-compat": check_backward_compat,
    "cache": check_cache_substitution,
    "composite": check_composite,
    "cost": check_cost_counterfactual,
    "cross-provider": check_cross_provider_drift,
    "identity": check_identity_binding,
    "reserve": check_reserve_commit_release,
}


if __name__ == "__main__":
    main()
