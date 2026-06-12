"""Counterfactual replay over the recorded decision: demos, substitution, schema."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import oep_permissions.replay as replay_module
import pytest
from helpers import (
    DECISION_ID,
    FIXED_REPLAY_TIMESTAMP,
    ROOT,
    _inject_nd_builtin_cache,
    _sha256,
    _sqlite_payload,
    _sqlite_row_counts,
    _sqlite_update_payload,
    _sqlite_values,
    _write_deny_policy,
)
from oep_demo.counterfactual import (
    run_approval_escalation_counterfactual,
    run_budget_per_run_counterfactual,
    run_compound_reliability_counterfactual,
)
from oep_permissions import (
    ReplayError,
    counterfactual_replay_decision,
    diff_decision_surfaces,
    project_pre_session_cost,
    replay_decision_with_substitutions,
    simulate_reserve_commit_release,
)

from oep_verify.verify_support import validate_json_schema


def test_counterfactual_replay_substitutes_policy_bundle(tmp_path: Path, state_path: Path) -> None:
    state_digest_before = _sha256(state_path)

    alt_policy_path = _write_deny_policy(tmp_path)

    result = counterfactual_replay_decision(
        state_path,
        DECISION_ID,
        alt_policy_path,
        replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
    )
    output = result.to_dict()

    assert _sha256(state_path) == state_digest_before
    assert output["schema_version"] == "oep.counterfactual_replay.v0"
    assert output["replay_mode"] == "counterfactual"
    assert output["original"]["decision"] == "allow"
    assert output["counterfactual"]["decision"] == "deny"
    assert output["counterfactual"]["decision_code"] == "COUNTERFACTUAL_POLICY_DENY"
    assert output["diff"]["decision_changed"] is True
    assert output["diff"]["rationale_changed"] is True
    assert output["diff"]["rule_set_delta"] == {
        "added": ["deny_replayed_model_alias"],
        "removed": ["allow_reference_code_review_diff_read"],
        "unchanged": [],
    }
    assert output["replay_metadata"] == {
        "oep_replay_mode": "counterfactual",
        "nd_builtin_cache_entries_used": 0,
        "replay_timestamp_utc": FIXED_REPLAY_TIMESTAMP,
        "determinism_exclusions": ["replay_metadata.replay_timestamp_utc"],
    }


def test_v03_replay_rejects_invalid_inputs_and_reports_missing_surfaces(state_path: Path) -> None:
    with pytest.raises(ReplayError, match="unknown diff surface"):
        diff_decision_surfaces(state_path, DECISION_ID, DECISION_ID, surfaces=("missing",))

    with pytest.raises(ReplayError, match="unknown substitution surface"):
        replay_decision_with_substitutions(state_path, DECISION_ID, substitutions={"unknown": "value"})

    with pytest.raises(ReplayError, match="must be non-empty"):
        replay_decision_with_substitutions(state_path, DECISION_ID, substitutions={"prompt": " "})

    with pytest.raises(ReplayError, match="provider:model_version"):
        replay_decision_with_substitutions(state_path, DECISION_ID, model_substitute="missing-separator")

    with pytest.raises(ReplayError, match="numeric cap"):
        replay_decision_with_substitutions(state_path, DECISION_ID, budget_policy="strictish")

    with pytest.raises(ReplayError, match="embedding_version=<version>"):
        replay_decision_with_substitutions(state_path, DECISION_ID, cache_policy="embedding_version=")

    with pytest.raises(ReplayError, match="staleness"):
        replay_decision_with_substitutions(state_path, DECISION_ID, cache_policy="other-cache-policy")

    with pytest.raises(ReplayError, match="budget_cap_usd"):
        simulate_reserve_commit_release([], budget_cap_usd=-1)

    with pytest.raises(ReplayError, match="budget_cap_source"):
        simulate_reserve_commit_release([], budget_cap_usd=1, budget_cap_source="per_org")

    with pytest.raises(ReplayError, match="budget_reservation_id"):
        simulate_reserve_commit_release(
            [{"reservation_estimated_cost_usd": 1, "reservation_committed_cost_usd": 1}],
            budget_cap_usd=1,
        )

    with pytest.raises(ReplayError, match="committed cost"):
        simulate_reserve_commit_release(
            [
                {
                    "budget_reservation_id": "bres_bad",
                    "reservation_estimated_cost_usd": 1,
                    "reservation_committed_cost_usd": -1,
                }
            ],
            budget_cap_usd=1,
        )

    with pytest.raises(ReplayError, match="non-negative"):
        project_pre_session_cost(
            projected_min_usd=-1,
            projected_max_usd=1,
            budget_cap_usd=1,
            approver_identity={"type": "human", "id": "human", "display_name": "Human"},
            approve=True,
        )

    with pytest.raises(ReplayError, match="must not exceed"):
        project_pre_session_cost(
            projected_min_usd=2,
            projected_max_usd=1,
            budget_cap_usd=3,
            approver_identity={"type": "human", "id": "human", "display_name": "Human"},
            approve=True,
        )

    packet = _sqlite_payload(
        state_path,
        "SELECT payload_json FROM permissions WHERE packet_id = ?",
        (DECISION_ID,),
    )
    packet.pop("decision_id")
    _sqlite_update_payload(
        state_path,
        "UPDATE permissions SET payload_json = ? WHERE packet_id = ?",
        packet,
        (DECISION_ID,),
    )
    missing_budget = replay_decision_with_substitutions(
        state_path,
        DECISION_ID,
        budget_policy="per_run_cap_usd=1",
        replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
    )
    assert missing_budget["diff"]["budget_delta"]["termination_code"] == "BUDGET_SURFACE_NOT_RECORDED"


def test_demo_1_compound_reliability_counterfactual(tmp_path: Path) -> None:
    first = run_compound_reliability_counterfactual(tmp_path / "first")
    second = run_compound_reliability_counterfactual(tmp_path / "second")

    assert first.total_steps == 10
    assert first.first_divergent_step == 5
    assert first.original_status == "succeeded"
    assert first.counterfactual_status == "failed"
    assert first.state_path.read_bytes() == second.state_path.read_bytes()
    assert first.json_path.read_bytes() == second.json_path.read_bytes()
    assert first.jsonl_path.read_bytes() == second.jsonl_path.read_bytes()

    summary = json.loads(first.json_path.read_text(encoding="utf-8"))
    assert summary["workflow"] == {
        "counterfactual_status": "failed",
        "counterfactual_step_bound": 4,
        "failure_decision_id": "pder_code_review_compound_reliability_step_0005",
        "first_divergent_step": 5,
        "original_status": "succeeded",
        "total_steps": 10,
    }
    assert len(summary["step_outputs"]) == 10
    assert [step["counterfactual"]["decision"] for step in summary["step_outputs"][:4]] == [
        "allow",
        "allow",
        "allow",
        "allow",
    ]
    assert summary["step_outputs"][4]["counterfactual"]["decision"] == "deny"
    assert summary["step_outputs"][4]["diff"]["decision_changed"] is True

    jsonl_records = [json.loads(line) for line in first.jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert jsonl_records == summary["step_outputs"]


def test_counterfactual_demo_state_refs_are_local_to_output_dir(tmp_path: Path) -> None:
    result = run_compound_reliability_counterfactual(tmp_path / "nested" / "compound_reliability")
    event = _sqlite_payload(
        result.state_path,
        "SELECT payload_json FROM events WHERE event_id = ?",
        ("evt_code_review_compound_reliability_step_0001",),
    )

    assert event["action"]["output_ref"] == result.json_path.name
    assert event["replay_handle"]["state_ref"] == (
        f"{result.state_path.name}#events/evt_code_review_compound_reliability_step_0001"
    )
    artifact_paths = _sqlite_values(
        result.state_path,
        """
        SELECT path FROM artifacts
        WHERE kind IN ('agent_step_event', 'tool_permission_packet')
        ORDER BY kind, artifact_id
        """,
    )
    assert set(artifact_paths) == {result.json_path.name}

    external_state = run_compound_reliability_counterfactual(
        tmp_path / "external" / "out",
        state_path=tmp_path / "external" / "state" / "compound_reliability.sqlite",
    )
    external_event = _sqlite_payload(
        external_state.state_path,
        "SELECT payload_json FROM events WHERE event_id = ?",
        ("evt_code_review_compound_reliability_step_0001",),
    )
    assert external_event["action"]["output_ref"] == external_state.json_path.name
    assert external_event["replay_handle"]["state_ref"] == (
        "../state/compound_reliability.sqlite#events/evt_code_review_compound_reliability_step_0001"
    )


def test_demo_2_budget_per_run_counterfactual(tmp_path: Path) -> None:
    first = run_budget_per_run_counterfactual(tmp_path / "first")
    second = run_budget_per_run_counterfactual(tmp_path / "second")

    assert first.total_steps == 47
    assert first.termination_step == 6
    assert first.original_total_usd == 47000
    assert first.counterfactual_total_usd == 5000
    assert first.state_path.read_bytes() == second.state_path.read_bytes()
    assert first.json_path.read_bytes() == second.json_path.read_bytes()
    assert first.jsonl_path.read_bytes() == second.jsonl_path.read_bytes()

    summary = json.loads(first.json_path.read_text(encoding="utf-8"))
    assert summary["budget"] == {
        "budget_cap_active_at_termination": True,
        "counterfactual_budget_cap_usd": 5000,
        "counterfactual_total_usd": 5000,
        "original_total_usd": 47000,
        "termination_code": "BUDGET_EXCEEDED",
        "termination_step": 6,
    }
    assert len(summary["cost_trace"]) == 47
    assert summary["cost_trace"][5] == {
        "budget_cap_active": True,
        "counterfactual_cumulative_usd": 5000,
        "original_cumulative_usd": 6000,
        "skipped_after_termination": False,
        "step": 6,
        "termination_code": "BUDGET_EXCEEDED",
    }
    assert len(summary["step_outputs"]) == 47
    assert [step["counterfactual"]["decision"] for step in summary["step_outputs"][:5]] == [
        "allow",
        "allow",
        "allow",
        "allow",
        "allow",
    ]
    termination_step = summary["step_outputs"][5]
    assert termination_step["counterfactual"]["decision"] == "deny"
    assert termination_step["counterfactual"]["decision_code"] == "BUDGET_EXCEEDED"
    assert termination_step["diff"]["budget_delta"] == {
        "budget_cap_active": True,
        "cost_trace_changed": True,
        "counterfactual_total_usd": 5000,
        "original_total_usd": 6000,
        "termination_code": "BUDGET_EXCEEDED",
        "termination_step": 6,
    }

    jsonl_records = [json.loads(line) for line in first.jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert jsonl_records == summary["step_outputs"]


def test_demo_3_approval_escalation_counterfactual(tmp_path: Path) -> None:
    first = run_approval_escalation_counterfactual(tmp_path / "first")
    second = run_approval_escalation_counterfactual(tmp_path / "second")

    assert first.total_steps == 6
    assert first.added_approval_steps == (
        "approval_step_02",
        "approval_step_04",
        "approval_step_05",
    )
    assert first.state_path.read_bytes() == second.state_path.read_bytes()
    assert first.json_path.read_bytes() == second.json_path.read_bytes()
    assert first.jsonl_path.read_bytes() == second.jsonl_path.read_bytes()

    summary = json.loads(first.json_path.read_text(encoding="utf-8"))
    assert summary["approval"] == {
        "added_approval_steps": ["approval_step_02", "approval_step_04", "approval_step_05"],
        "counterfactual_approval_type": "human_write_approval_required",
        "counterfactual_policy": "approval required for every write operation",
        "original_policy": "approval required only for production deploy actions",
    }
    assert len(summary["step_outputs"]) == 6
    assert summary["step_outputs"][0]["counterfactual"]["decision"] == "allow"

    step_2 = summary["step_outputs"][1]
    assert step_2["counterfactual"]["decision"] == "deny"
    assert step_2["counterfactual"]["decision_code"] == "APPROVAL_REQUIRED"
    assert step_2["diff"]["approval_delta"] == {
        "added_approval_steps": ["approval_step_02"],
        "approval_requirements_changed": True,
        "counterfactual_approval_capture": {
            "approval_type": "human_write_approval_required",
            "approver": {
                "display_name": "code owner",
                "id": "human_code_owner",
                "type": "human",
            },
            "required_at_step": "approval_step_02",
        },
        "removed_approval_steps": [],
    }
    assert summary["step_outputs"][3]["counterfactual"]["decision_code"] == "APPROVAL_REQUIRED"
    assert summary["step_outputs"][4]["counterfactual"]["decision_code"] == "APPROVAL_REQUIRED"
    assert summary["step_outputs"][5]["counterfactual"]["decision"] == "allow"

    jsonl_records = [json.loads(line) for line in first.jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert jsonl_records == summary["step_outputs"]


@pytest.mark.parametrize(
    "runner",
    [
        pytest.param(run_compound_reliability_counterfactual, id="compound_reliability"),
        pytest.param(run_budget_per_run_counterfactual, id="budget_per_run"),
        pytest.param(run_approval_escalation_counterfactual, id="approval_escalation"),
    ],
)
def test_counterfactual_replay_byte_identical_across_runs(
    tmp_path: Path,
    runner: Callable[[Path], Any],
) -> None:
    first = runner(tmp_path / "first")
    second = runner(tmp_path / "second")

    assert first.state_path.read_bytes() == second.state_path.read_bytes()
    assert first.json_path.read_bytes() == second.json_path.read_bytes()
    assert first.jsonl_path.read_bytes() == second.jsonl_path.read_bytes()


def test_counterfactual_output_validates_against_schema(tmp_path: Path) -> None:
    schema = json.loads((ROOT / "replay" / "counterfactual_replay.v0.schema.json").read_text(encoding="utf-8"))
    result = run_compound_reliability_counterfactual(tmp_path)
    summary = json.loads(result.json_path.read_text(encoding="utf-8"))

    for step_output in summary["step_outputs"]:
        validate_json_schema(schema, step_output, instance_path=result.json_path)


def test_counterfactual_denied_path_no_replay_state(tmp_path: Path, state_path: Path) -> None:
    state_digest_before = _sha256(state_path)
    row_counts_before = _sqlite_row_counts(state_path)

    alt_policy_path = _write_deny_policy(tmp_path)
    result = counterfactual_replay_decision(
        state_path,
        DECISION_ID,
        alt_policy_path,
        replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
    )
    output = result.to_dict()

    assert output["counterfactual"]["decision"] == "deny"
    assert _sha256(state_path) == state_digest_before
    assert _sqlite_row_counts(state_path) == row_counts_before

    denied_eval = json.loads(
        (ROOT / "traces" / "examples" / "code_review_agent_denied_eval.v0.json").read_text(encoding="utf-8")
    )
    assert denied_eval["status"] == "failed"
    assert denied_eval["input_refs"]["state_ref"] == "missing:denied-tool-call"
    assert {
        "check_id": "no_replay_state",
        "status": "failed",
        "summary": "The denied tool call has no generated SQLite replay state.",
    } in denied_eval["checks"]

    with pytest.raises(ReplayError, match="no recorded decision"):
        counterfactual_replay_decision(
            state_path,
            "pder_code_review_write_diff_0001",
            alt_policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )


def test_counterfactual_replay_preserves_decision_under_same_policy(state_path: Path) -> None:
    result = counterfactual_replay_decision(
        state_path,
        DECISION_ID,
        ROOT / "permissions" / "policy" / "tool_permissions.rego",
        replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
    )
    output = result.to_dict()

    assert output["original"]["decision"] == "allow"
    assert output["counterfactual"]["decision"] == "allow"
    assert output["diff"]["decision_changed"] is False
    assert output["diff"]["rationale_changed"] is False
    assert output["diff"]["rule_set_delta"] == {
        "added": [],
        "removed": [],
        "unchanged": ["allow_reference_code_review_diff_read"],
    }


def test_counterfactual_record_nested_state_is_immutable(state_path: Path) -> None:
    result = counterfactual_replay_decision(
        state_path,
        DECISION_ID,
        ROOT / "permissions" / "policy" / "tool_permissions.rego",
        replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
    )

    with pytest.raises(TypeError):
        cast(Any, result.diff)["budget_delta"] = {"changed": True}

    mutable_copy = result.to_dict()
    mutable_copy["diff"]["budget_delta"] = {"changed": True}
    assert result.to_dict()["diff"]["budget_delta"] is None


def test_nd_builtin_cache_injection_returns_cached_value(tmp_path: Path, state_path: Path) -> None:
    _inject_nd_builtin_cache(
        state_path,
        {
            "time.now_ns": {
                "[]": 1777852800000000000,
            },
            "http.send": {
                '[{"method":"get","url":"https://example.test/status"}]': {
                    "status_code": 200,
                    "body": {"status": "cached"},
                }
            },
        },
    )

    cache_policy_dir = tmp_path / "cache_policy_bundle"
    cache_policy_dir.mkdir()
    cache_policy_path = cache_policy_dir / "cache_policy.rego"
    cache_policy_path.write_text(
        """
package oep.permissions

import data.oep.builtins as oep_builtins

cached_now_ns := oep_builtins.now_ns(input)
cached_http_status := oep_builtins.http_send(input, {"method": "get", "url": "https://example.test/status"}).status_code

decision := {
    "allow": true,
    "matched_rule": "allow_cached_nd_builtin_replay",
    "policy_id": "opa-tool-permission-policy",
    "policy_version": "0.3-test",
    "reason": sprintf("cached now_ns=%v http_status=%v", [cached_now_ns, cached_http_status]),
} if {
    cached_now_ns == 1777852800000000000
    cached_http_status == 200
}
""",
        encoding="utf-8",
    )
    (cache_policy_dir / "oep.rego").write_text(
        (ROOT / "permissions" / "policy" / "counterfactual" / "oep.rego").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    result = counterfactual_replay_decision(
        state_path,
        DECISION_ID,
        cache_policy_dir,
        replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
    )
    output = result.to_dict()

    assert output["counterfactual"]["decision"] == "allow"
    assert output["counterfactual"]["rationale"] == "cached now_ns=1777852800000000000 http_status=200"
    assert output["counterfactual"]["matched_rules"] == ["allow_cached_nd_builtin_replay"]
    assert output["replay_metadata"]["nd_builtin_cache_entries_used"] == 2


def test_counterfactual_replay_rejects_missing_or_undefined_policy(tmp_path: Path, state_path: Path) -> None:
    with pytest.raises(replay_module.OpaEvaluationError, match="counterfactual policy bundle not found"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            tmp_path / "missing.rego",
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )

    undefined_policy_path = tmp_path / "undefined_policy.rego"
    undefined_policy_path.write_text("package oep.permissions\n", encoding="utf-8")
    with pytest.raises(ReplayError, match="may be undefined or evaluated to empty"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            undefined_policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )


def test_counterfactual_replay_rejects_nonstandard_query_path(state_path: Path) -> None:
    with pytest.raises(replay_module.OpaEvaluationError, match="unsupported OPA query path"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            ROOT / "permissions" / "policy" / "tool_permissions.rego",
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
            query="data.oep.permissions.decision; injected := true",
        )
