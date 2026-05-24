from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import oep_demo.counterfactual as counterfactual_module
import oep_permissions.replay as replay_module
import pytest
from oep_demo import run_demo
from oep_demo.counterfactual import (
    run_approval_escalation_counterfactual,
    run_budget_per_run_counterfactual,
    run_compound_reliability_counterfactual,
)
from oep_permissions import ReplayError, counterfactual_replay_decision

from oep_verify.cli import main as cli_main
from oep_verify.verify_support import validate_json_schema

ROOT = Path(__file__).resolve().parents[1]
DECISION_ID = "pder_code_review_read_diff_0001"
FIXED_REPLAY_TIMESTAMP = "2026-05-23T00:00:00Z"


def test_counterfactual_replay_substitutes_policy_bundle(tmp_path: Path) -> None:
    state_path = tmp_path / "code_review_agent.sqlite"
    run_demo(state_path)
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


def test_counterfactual_replay_cli_outputs_json_and_human(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "code_review_agent.sqlite"
    run_demo(state_path)
    alt_policy_path = _write_deny_policy(tmp_path)

    cli_main(
        [
            "replay",
            DECISION_ID,
            "--state-path",
            str(state_path),
            "--counterfactual",
            "--policy-bundle",
            str(alt_policy_path),
            "--output-format",
            "json",
            "--replay-timestamp-utc",
            FIXED_REPLAY_TIMESTAMP,
        ]
    )
    json_output = json.loads(capsys.readouterr().out)
    assert json_output["replay_mode"] == "counterfactual"
    assert json_output["counterfactual"]["decision"] == "deny"
    assert json_output["replay_metadata"]["replay_timestamp_utc"] == FIXED_REPLAY_TIMESTAMP

    cli_main(
        [
            "replay",
            DECISION_ID,
            "--state-path",
            str(state_path),
            "--counterfactual",
            "--policy-bundle",
            str(alt_policy_path),
            "--output-format",
            "json",
            "--strip-exclusions",
        ]
    )
    stripped_output = json.loads(capsys.readouterr().out)
    assert stripped_output["replay_mode"] == "counterfactual"
    assert "replay_timestamp_utc" not in stripped_output["replay_metadata"]
    assert stripped_output["replay_metadata"]["determinism_exclusions"] == [
        "replay_metadata.replay_timestamp_utc"
    ]

    cli_main(
        [
            "replay",
            DECISION_ID,
            "--state-path",
            str(state_path),
            "--counterfactual",
            "--policy-bundle",
            str(alt_policy_path),
            "--output-format",
            "jsonl",
        ]
    )
    jsonl_output = json.loads(capsys.readouterr().out)
    assert jsonl_output["replay_mode"] == "counterfactual"

    cli_main(
        [
            "replay",
            DECISION_ID,
            "--state-path",
            str(state_path),
            "--output-format",
            "human",
        ]
    )
    read_only_human_output = capsys.readouterr().out
    assert "trace_id:" in read_only_human_output
    assert "span_id:" in read_only_human_output
    assert "replay_handle:" in read_only_human_output

    monkeypatch.setenv("OEP_REPLAY_MODE", "counterfactual")
    cli_main(
        [
            "replay",
            DECISION_ID,
            "--state-path",
            str(state_path),
            "--policy-bundle",
            str(alt_policy_path),
        ]
    )
    human_output = capsys.readouterr().out
    assert "replay_mode: counterfactual" in human_output
    assert "counterfactual: deny" in human_output


def test_counterfactual_replay_cli_rejects_invalid_mode_and_missing_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "code_review_agent.sqlite"
    run_demo(state_path)

    with pytest.raises(SystemExit, match="--policy-bundle is required"):
        cli_main(["replay", DECISION_ID, "--state-path", str(state_path), "--counterfactual"])

    with pytest.raises(SystemExit, match="--policy-bundle requires counterfactual"):
        cli_main(
            [
                "replay",
                DECISION_ID,
                "--state-path",
                str(state_path),
                "--policy-bundle",
                str(ROOT / "permissions" / "policy" / "tool_permissions.rego"),
            ]
        )

    with pytest.raises(SystemExit, match="--replay-timestamp-utc requires counterfactual"):
        cli_main(
            [
                "replay",
                DECISION_ID,
                "--state-path",
                str(state_path),
                "--replay-timestamp-utc",
                FIXED_REPLAY_TIMESTAMP,
            ]
        )

    with pytest.raises(SystemExit, match="--strip-exclusions requires counterfactual"):
        cli_main(["replay", DECISION_ID, "--state-path", str(state_path), "--strip-exclusions"])

    monkeypatch.setenv("OEP_REPLAY_MODE", "invalid")
    with pytest.raises(SystemExit, match="OEP_REPLAY_MODE must be"):
        cli_main(["replay", DECISION_ID, "--state-path", str(state_path)])


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

    jsonl_records = [
        json.loads(line)
        for line in first.jsonl_path.read_text(encoding="utf-8").splitlines()
    ]
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

    jsonl_records = [
        json.loads(line)
        for line in first.jsonl_path.read_text(encoding="utf-8").splitlines()
    ]
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

    jsonl_records = [
        json.loads(line)
        for line in first.jsonl_path.read_text(encoding="utf-8").splitlines()
    ]
    assert jsonl_records == summary["step_outputs"]


def test_counterfactual_replay_byte_identical_across_runs(tmp_path: Path) -> None:
    runners: tuple[tuple[str, Callable[[Path], Any]], ...] = (
        ("compound_reliability", run_compound_reliability_counterfactual),
        ("budget_per_run", run_budget_per_run_counterfactual),
        ("approval_escalation", run_approval_escalation_counterfactual),
    )

    for name, runner in runners:
        first = runner(tmp_path / name / "first")
        second = runner(tmp_path / name / "second")

        assert first.state_path.read_bytes() == second.state_path.read_bytes()
        assert first.json_path.read_bytes() == second.json_path.read_bytes()
        assert first.jsonl_path.read_bytes() == second.jsonl_path.read_bytes()


def test_counterfactual_output_validates_against_schema(tmp_path: Path) -> None:
    schema = json.loads((ROOT / "replay" / "counterfactual_replay.v0.schema.json").read_text(encoding="utf-8"))
    result = run_compound_reliability_counterfactual(tmp_path)
    summary = json.loads(result.json_path.read_text(encoding="utf-8"))

    for step_output in summary["step_outputs"]:
        validate_json_schema(schema, step_output, instance_path=result.json_path)


def test_counterfactual_denied_path_no_replay_state(tmp_path: Path) -> None:
    state_path = tmp_path / "code_review_agent.sqlite"
    run_demo(state_path)
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


def test_counterfactual_replay_preserves_decision_under_same_policy(tmp_path: Path) -> None:
    state_path = tmp_path / "code_review_agent.sqlite"
    run_demo(state_path)

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


def test_counterfactual_record_nested_state_is_immutable(tmp_path: Path) -> None:
    state_path = tmp_path / "code_review_agent.sqlite"
    run_demo(state_path)
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


def test_nd_builtin_cache_injection_returns_cached_value(tmp_path: Path) -> None:
    state_path = tmp_path / "code_review_agent.sqlite"
    run_demo(state_path)
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


def test_counterfactual_replay_rejects_missing_or_undefined_policy(tmp_path: Path) -> None:
    state_path = tmp_path / "code_review_agent.sqlite"
    run_demo(state_path)

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


def test_counterfactual_replay_rejects_nonstandard_query_path(tmp_path: Path) -> None:
    state_path = tmp_path / "code_review_agent.sqlite"
    run_demo(state_path)

    with pytest.raises(replay_module.OpaEvaluationError, match="unsupported OPA query path"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            ROOT / "permissions" / "policy" / "tool_permissions.rego",
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
            query="data.oep.permissions.decision; injected := true",
        )


def test_reconstruct_decision_reads_read_only_sqlite_state(tmp_path: Path) -> None:
    state_path = tmp_path / "code_review_agent.sqlite"
    run_demo(state_path)
    state_path.chmod(0o444)
    try:
        record = replay_module.reconstruct_decision(state_path, DECISION_ID)
    finally:
        state_path.chmod(0o644)

    assert record.decision_id == DECISION_ID
    assert record.tool_call_id == "tool_read_diff_0001"


def test_replay_state_connection_is_sqlite_read_only(tmp_path: Path) -> None:
    state_path = tmp_path / "state with space.sqlite"
    run_demo(state_path)

    connection = replay_module._connect_read_only_state(state_path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("CREATE TABLE should_not_write (id TEXT)")
    finally:
        connection.close()


def test_reconstruct_decisions_preserves_requested_order_and_duplicates(tmp_path: Path) -> None:
    state_path = tmp_path / "code_review_agent.sqlite"
    run_demo(state_path)

    records = replay_module.reconstruct_decisions(state_path, [DECISION_ID, DECISION_ID])

    assert [record.decision_id for record in records] == [DECISION_ID, DECISION_ID]
    assert [record.tool_call_id for record in records] == ["tool_read_diff_0001", "tool_read_diff_0001"]
    assert replay_module.reconstruct_decisions(state_path, []) == []
    connection = sqlite3.connect(state_path)
    try:
        connection_records = replay_module.reconstruct_decisions(connection, [DECISION_ID])
        assert [record.decision_id for record in connection_records] == [DECISION_ID]
        assert connection.row_factory is None
        assert connection.execute("SELECT 1").fetchone() == (1,)
    finally:
        connection.close()
    assert (
        replay_module.counterfactual_replay_decisions(
            state_path,
            [],
            ROOT / "permissions" / "policy" / "tool_permissions.rego",
        )
        == []
    )


def test_reconstruct_decision_reports_sqlite_operational_errors(tmp_path: Path) -> None:
    state_path = tmp_path / "empty.sqlite"
    sqlite3.connect(state_path).close()

    with pytest.raises(ReplayError, match="database operational error during replay reconstruction"):
        replay_module.reconstruct_decision(state_path, DECISION_ID)

    with pytest.raises(replay_module.StateNotFoundError, match="replay state not found"):
        replay_module.reconstruct_decision(tmp_path / "missing.sqlite", DECISION_ID)


def test_reconstruct_decision_rejects_corrupt_joined_payloads(tmp_path: Path) -> None:
    bad_event_state_path = tmp_path / "bad_event.sqlite"
    run_demo(bad_event_state_path)
    bad_event = _sqlite_payload(
        bad_event_state_path,
        "SELECT payload_json FROM events WHERE event_id = ?",
        ("evt_code_review_agent_step_0001",),
    )
    bad_event["replay_handle"] = "not-an-object"
    _sqlite_update_payload(
        bad_event_state_path,
        "UPDATE events SET payload_json = ? WHERE event_id = ?",
        bad_event,
        ("evt_code_review_agent_step_0001",),
    )
    with pytest.raises(ReplayError, match="event.replay_handle must be an object"):
        replay_module.reconstruct_decision(bad_event_state_path, DECISION_ID)

    bad_permission_state_path = tmp_path / "bad_permission.sqlite"
    run_demo(bad_permission_state_path)
    _sqlite_update_raw_payload(
        bad_permission_state_path,
        "UPDATE permissions SET payload_json = ? WHERE packet_id = ?",
        "[]",
        (DECISION_ID,),
    )
    with pytest.raises(ReplayError, match="permission payload must decode to a JSON object"):
        replay_module.reconstruct_decision(bad_permission_state_path, DECISION_ID)

    bad_join_state_path = tmp_path / "bad_join.sqlite"
    run_demo(bad_join_state_path)
    bad_packet = _sqlite_payload(
        bad_join_state_path,
        "SELECT payload_json FROM permissions WHERE packet_id = ?",
        (DECISION_ID,),
    )
    bad_packet["event_id"] = "evt_code_review_agent_step_mismatch"
    _sqlite_update_payload(
        bad_join_state_path,
        "UPDATE permissions SET payload_json = ? WHERE packet_id = ?",
        bad_packet,
        (DECISION_ID,),
    )
    with pytest.raises(ReplayError, match="inconsistent joined field"):
        replay_module.reconstruct_decision(bad_join_state_path, DECISION_ID)

    schema_drift_state_path = tmp_path / "schema_drift.sqlite"
    run_demo(schema_drift_state_path)
    schema_drift_packet = _sqlite_payload(
        schema_drift_state_path,
        "SELECT payload_json FROM permissions WHERE packet_id = ?",
        (DECISION_ID,),
    )
    schema_drift_packet["unexpected_extra_field"] = True
    _sqlite_update_payload(
        schema_drift_state_path,
        "UPDATE permissions SET payload_json = ? WHERE packet_id = ?",
        schema_drift_packet,
        (DECISION_ID,),
    )
    with pytest.raises(ReplayError, match="failed schema validation"):
        replay_module.reconstruct_decision(schema_drift_state_path, DECISION_ID)
    assert (
        replay_module.reconstruct_decision(
            schema_drift_state_path,
            DECISION_ID,
            validate_schema=False,
        ).decision_id
        == DECISION_ID
    )

    missing_manifest_state_path = tmp_path / "missing_manifest.sqlite"
    run_demo(missing_manifest_state_path)
    connection = sqlite3.connect(missing_manifest_state_path)
    try:
        connection.execute("DELETE FROM artifacts WHERE kind = ?", ("release_manifest",))
        connection.commit()
    finally:
        connection.close()
    record = replay_module.reconstruct_decision(missing_manifest_state_path, DECISION_ID)
    assert record.release_manifest_summary is None


def test_read_only_state_uses_file_uri_with_percent_encoding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "state with space.sqlite"
    state_path.write_bytes(b"")
    real_connect = sqlite3.connect
    calls: list[tuple[object, dict[str, Any]]] = []

    def connect(database: object, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        calls.append((database, kwargs))
        return real_connect(":memory:")

    monkeypatch.setattr("oep_permissions.replay.sqlite3.connect", connect)

    connect_read_only_state = cast(
        Callable[[Path], sqlite3.Connection],
        vars(replay_module)["_connect_read_only_state"],
    )
    connection = connect_read_only_state(state_path)
    try:
        assert calls[0][1]["uri"] is True
        assert calls[0][1]["timeout"] == 10.0
        assert isinstance(calls[0][0], str)
        assert calls[0][0].startswith("file:///")
        assert calls[0][0].endswith("?mode=ro")
        assert "state%20with%20space.sqlite" in calls[0][0]
        assert len(calls) == 1
    finally:
        connection.close()


def test_counterfactual_replay_reports_opa_timeout_and_stdout_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "code_review_agent.sqlite"
    run_demo(state_path)
    policy_path = ROOT / "permissions" / "policy" / "tool_permissions.rego"

    terminated_processes: list[_FakeOpaProcess] = []

    def timeout_popen(args: list[str], **kwargs: Any) -> _FakeOpaProcess:
        assert args[1] == "eval"
        assert kwargs["encoding"] == "utf-8"
        return _FakeOpaProcess(
            args,
            timeout=True,
            expected_timeout=replay_module.OPA_EVAL_TIMEOUT_SECONDS,
        )

    def terminate(process: _FakeOpaProcess) -> None:
        terminated_processes.append(process)
        process.kill()

    monkeypatch.setattr("oep_permissions.replay.subprocess.Popen", timeout_popen)
    monkeypatch.setattr("oep_permissions.replay._terminate_opa_process", terminate)
    with pytest.raises(ReplayError, match="timed out after 30 seconds"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )
    assert len(terminated_processes) == 1
    assert terminated_processes[0].killed is True
    assert terminated_processes[0].waited is True

    unexpected_processes: list[_FakeOpaProcess] = []

    def unexpected_popen(args: list[str], **kwargs: Any) -> _FakeOpaProcess:
        return _FakeOpaProcess(
            args,
            unexpected_exception=RuntimeError("unexpected communicate failure"),
            expected_timeout=replay_module.OPA_EVAL_TIMEOUT_SECONDS,
        )

    def terminate_unexpected(process: _FakeOpaProcess) -> None:
        unexpected_processes.append(process)
        process.kill()

    monkeypatch.setattr("oep_permissions.replay.subprocess.Popen", unexpected_popen)
    monkeypatch.setattr("oep_permissions.replay._terminate_opa_process", terminate_unexpected)
    with pytest.raises(RuntimeError, match="unexpected communicate failure"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )
    assert len(unexpected_processes) == 1
    assert unexpected_processes[0].killed is True
    assert unexpected_processes[0].waited is True

    def failing_popen(args: list[str], **kwargs: Any) -> _FakeOpaProcess:
        assert args[1] == "eval"
        assert kwargs["encoding"] == "utf-8"
        return _FakeOpaProcess(
            args,
            returncode=1,
            stdout="stdout failure",
            expected_timeout=replay_module.OPA_EVAL_TIMEOUT_SECONDS,
        )

    monkeypatch.setattr("oep_permissions.replay.subprocess.Popen", failing_popen)
    with pytest.raises(ReplayError, match="stdout failure"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )

    long_error = ("x" * replay_module.OPA_ERROR_OUTPUT_LIMIT) + "UNTRUNCATED_SUFFIX"

    def verbose_failing_popen(args: list[str], **kwargs: Any) -> _FakeOpaProcess:
        return _FakeOpaProcess(
            args,
            returncode=1,
            stderr=long_error,
            expected_timeout=replay_module.OPA_EVAL_TIMEOUT_SECONDS,
        )

    monkeypatch.setattr("oep_permissions.replay.subprocess.Popen", verbose_failing_popen)
    with pytest.raises(ReplayError) as exc_info:
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
    )
    assert "[output truncated]" in str(exc_info.value)
    assert "UNTRUNCATED_SUFFIX" not in str(exc_info.value)


def test_opa_eval_rejects_oversized_stdin_before_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_opa_eval = cast(
        Callable[[list[str], str, float | None], subprocess.CompletedProcess[str]],
        vars(replay_module)["_run_opa_eval"],
    )

    def fail_popen(*args: Any, **kwargs: Any) -> _FakeOpaProcess:
        raise AssertionError("OPA subprocess must not start for oversized stdin")

    monkeypatch.setattr(replay_module, "OPA_STDIN_INPUT_LIMIT_BYTES", 4)
    monkeypatch.setattr("oep_permissions.replay.subprocess.Popen", fail_popen)

    with pytest.raises(replay_module.OpaEvaluationError, match="input exceeds 4 bytes"):
        run_opa_eval(["opa", "eval"], "12345", 1.0)


def test_counterfactual_replay_rejects_invalid_replay_timestamp_before_opa(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "code_review_agent.sqlite"
    run_demo(state_path)
    policy_path = ROOT / "permissions" / "policy" / "tool_permissions.rego"

    def fail_popen(*args: Any, **kwargs: Any) -> _FakeOpaProcess:
        raise AssertionError("OPA subprocess must not start for an invalid replay timestamp")

    monkeypatch.setattr("oep_permissions.replay.subprocess.Popen", fail_popen)

    with pytest.raises(ReplayError, match="replay_timestamp_utc must be a valid date-time"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc="garbage",
        )


def test_counterfactual_replay_uses_configured_opa_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "code_review_agent.sqlite"
    run_demo(state_path)
    policy_path = ROOT / "permissions" / "policy" / "tool_permissions.rego"

    def timeout_popen(args: list[str], **kwargs: Any) -> _FakeOpaProcess:
        assert args[1] == "eval"
        return _FakeOpaProcess(args, timeout=True, expected_timeout=0.25)

    monkeypatch.setenv(replay_module.OEP_OPA_EVAL_TIMEOUT_SECONDS_ENV, "10")
    monkeypatch.setattr("oep_permissions.replay.subprocess.Popen", timeout_popen)
    monkeypatch.setattr(
        "oep_permissions.replay._terminate_opa_process",
        lambda process: process.kill(),
    )
    with pytest.raises(ReplayError, match="timed out after 0.25 seconds"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
            timeout_seconds=0.25,
        )

    monkeypatch.setenv(replay_module.OEP_OPA_EVAL_TIMEOUT_SECONDS_ENV, "0.25")
    with pytest.raises(ReplayError, match="timed out after 0.25 seconds"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )

    with pytest.raises(ReplayError, match="timeout_seconds must be a number of seconds greater than or equal to 0.001"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
            timeout_seconds=0,
        )

    with pytest.raises(ReplayError, match="timeout_seconds must be a number of seconds greater than or equal to 0.001"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
            timeout_seconds=0.000_000_001,
        )

    monkeypatch.setenv(replay_module.OEP_OPA_EVAL_TIMEOUT_SECONDS_ENV, "0")
    with pytest.raises(ReplayError, match="must be a number of seconds greater than or equal to 0.001"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )

    monkeypatch.setenv(replay_module.OEP_OPA_EVAL_TIMEOUT_SECONDS_ENV, "0.000000001")
    with pytest.raises(ReplayError, match="must be a number of seconds greater than or equal to 0.001"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )

    monkeypatch.setenv(replay_module.OEP_OPA_EVAL_TIMEOUT_SECONDS_ENV, "not-a-number")
    with pytest.raises(ReplayError, match="must be a number of seconds greater than or equal to 0.001"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )


def test_counterfactual_replay_allows_opa_command_wrapper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "code_review_agent.sqlite"
    run_demo(state_path)
    policy_path = ROOT / "permissions" / "policy" / "tool_permissions.rego"

    def wrapped_popen(args: list[str], **kwargs: Any) -> _FakeOpaProcess:
        assert args[0:2] == ["/usr/bin/prlimit", "--as=100000000"]
        assert Path(args[2]).name == "opa"
        assert args[3] == "eval"
        return _FakeOpaProcess(
            args,
            stdout=json.dumps(
                {
                    "result": [
                        {
                            "expressions": [
                                {
                                    "value": {
                                        "00000000": {
                                            "allow": True,
                                            "matched_rule": "allow_reference_code_review_diff_read",
                                            "policy_id": "opa-tool-permission-policy",
                                            "policy_version": "0.1.0",
                                            "reason": (
                                                "reference code review agent may inspect an immutable synthetic diff"
                                            ),
                                        }
                                    }
                                }
                            ]
                        }
                    ]
                }
            ),
        )

    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "prlimit --as=100000000")
    monkeypatch.setattr("oep_permissions.replay.shutil.which", lambda executable, path=None: f"/usr/bin/{executable}")
    monkeypatch.setattr("oep_verify.verify_support.require_executable", lambda name, purpose: f"/usr/bin/{name}")
    monkeypatch.setattr("oep_permissions.replay.subprocess.Popen", wrapped_popen)

    result = counterfactual_replay_decision(
        state_path,
        DECISION_ID,
        policy_path,
        replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
    )

    assert result.counterfactual["decision"] == "allow"


def test_counterfactual_replay_rejects_invalid_opa_command_wrapper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "code_review_agent.sqlite"
    run_demo(state_path)
    policy_path = ROOT / "permissions" / "policy" / "tool_permissions.rego"

    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "\"unterminated")

    with pytest.raises(ReplayError, match="OEP_OPA_COMMAND_WRAPPER could not be parsed"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )


def test_counterfactual_replay_rejects_unauthorized_opa_command_wrapper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "code_review_agent.sqlite"
    run_demo(state_path)
    policy_path = ROOT / "permissions" / "policy" / "tool_permissions.rego"

    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "python -c pass")

    with pytest.raises(ReplayError, match="unauthorized OEP_OPA_COMMAND_WRAPPER executable"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )


def test_opa_command_wrapper_rejects_positional_binary_arguments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opa_command = cast(
        Callable[[list[str]], list[str]],
        vars(replay_module)["_opa_command"],
    )
    monkeypatch.setattr("oep_permissions.replay.shutil.which", lambda executable, path=None: f"/usr/bin/{executable}")

    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "nice -n 5")
    assert opa_command(["opa", "eval"]) == ["/usr/bin/nice", "-n", "5", "opa", "eval"]

    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "nice /tmp/arbitrary_binary")
    with pytest.raises(ReplayError, match="unauthorized OEP_OPA_COMMAND_WRAPPER argument"):
        opa_command(["opa", "eval"])

    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "sudo -s")
    with pytest.raises(ReplayError, match="unauthorized OEP_OPA_COMMAND_WRAPPER argument"):
        opa_command(["opa", "eval"])

    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "docker run --rm --init --network none opa:1.7.1")
    assert opa_command(["opa", "eval"]) == [
        "/usr/bin/docker",
        "run",
        "--rm",
        "--init",
        "--network",
        "none",
        "opa:1.7.1",
        "opa",
        "eval",
    ]

    volume_source = tmp_path / "policy"
    monkeypatch.setenv(
        replay_module.OEP_OPA_COMMAND_WRAPPER_ENV,
        f"docker run --rm --read-only -v {volume_source}:/policy:ro opa:1.7.1",
    )
    assert opa_command(["opa", "eval"]) == [
        "/usr/bin/docker",
        "run",
        "--rm",
        "--read-only",
        "-v",
        f"{volume_source}:/policy:ro",
        "opa:1.7.1",
        "opa",
        "eval",
    ]

    monkeypatch.setenv(
        replay_module.OEP_OPA_COMMAND_WRAPPER_ENV,
        f"docker run --rm -v {volume_source}:/policy:rw opa:1.7.1",
    )
    with pytest.raises(ReplayError, match="unauthorized OEP_OPA_COMMAND_WRAPPER argument"):
        opa_command(["opa", "eval"])

    monkeypatch.setenv(
        replay_module.OEP_OPA_COMMAND_WRAPPER_ENV,
        "docker run --rm -v relative-source:/policy:ro opa:1.7.1",
    )
    with pytest.raises(ReplayError, match="unauthorized OEP_OPA_COMMAND_WRAPPER argument"):
        opa_command(["opa", "eval"])

    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "docker run --entrypoint sh opa:1.7.1")
    with pytest.raises(ReplayError, match="unauthorized OEP_OPA_COMMAND_WRAPPER argument"):
        opa_command(["opa", "eval"])

    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "nice -n 5")
    monkeypatch.setattr("oep_permissions.replay.shutil.which", lambda executable, path=None: f"/tmp/{executable}")
    with pytest.raises(ReplayError, match="resolved to untrusted path"):
        opa_command(["opa", "eval"])


def test_opa_policy_bundle_data_path_uses_docker_volume_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_path = cast(
        Callable[[Path], str],
        vars(replay_module)["_opa_policy_bundle_data_path"],
    )
    policy_dir = tmp_path / "policy"
    policy_path = policy_dir / "counterfactual" / "policy.rego"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text("package oep.permissions\n", encoding="utf-8")

    monkeypatch.setenv(
        replay_module.OEP_OPA_COMMAND_WRAPPER_ENV,
        f"docker run --rm --volume={policy_dir}:/policy:ro opa:1.7.1",
    )

    assert data_path(policy_path) == "/policy/counterfactual/policy.rego"


def test_opa_command_wrapper_ignores_relative_path_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opa_command = cast(
        Callable[[list[str]], list[str]],
        vars(replay_module)["_opa_command"],
    )
    captured_search_path: str | None = None
    absolute_tmp_entry = tmp_path / "bin"

    def fake_which(executable: str, path: str | None = None) -> str:
        nonlocal captured_search_path
        captured_search_path = path
        return f"/usr/bin/{executable}"

    monkeypatch.setenv(
        "PATH",
        os.pathsep.join(("", ".", "relative-bin", str(absolute_tmp_entry), "/usr/bin")),
    )
    monkeypatch.setattr("oep_permissions.replay.shutil.which", fake_which)
    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "nice -n 5")

    assert opa_command(["opa", "eval"]) == ["/usr/bin/nice", "-n", "5", "opa", "eval"]
    assert captured_search_path == os.pathsep.join((str(absolute_tmp_entry), "/usr/bin"))


def test_opa_command_wrapper_validates_windows_trusted_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opa_command = cast(
        Callable[[list[str]], list[str]],
        vars(replay_module)["_opa_command"],
    )

    monkeypatch.setattr("oep_permissions.replay.os.name", "nt")
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    monkeypatch.setenv("ProgramFiles", r"C:\Program Files")
    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "nice -n 5")

    def trusted_which(executable: str, path: str | None = None) -> str:
        del path
        return rf"C:\Windows\System32\{executable}.exe"

    monkeypatch.setattr("oep_permissions.replay.shutil.which", trusted_which)
    assert opa_command(["opa", "eval"]) == [r"C:\Windows\System32\nice.exe", "-n", "5", "opa", "eval"]

    def untrusted_which(executable: str, path: str | None = None) -> str:
        del path
        return rf"C:\Users\mic\bin\{executable}.exe"

    monkeypatch.setattr("oep_permissions.replay.shutil.which", untrusted_which)
    with pytest.raises(ReplayError, match="resolved to untrusted path"):
        opa_command(["opa", "eval"])


def test_opa_command_wrapper_rejects_windows_junction_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opa_command = cast(
        Callable[[list[str]], list[str]],
        vars(replay_module)["_opa_command"],
    )

    monkeypatch.setattr("oep_permissions.replay.os.name", "nt")
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    monkeypatch.setenv("ProgramFiles", r"C:\Program Files")
    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "nice -n 5")
    monkeypatch.setattr(
        "oep_permissions.replay.shutil.which",
        lambda executable, path=None: rf"C:\Program Files\OEP\{executable}.exe",
    )
    monkeypatch.setattr(
        "oep_permissions.replay._resolve_windows_filesystem_path",
        lambda resolved: resolved.replace(r"C:\Program Files\OEP", r"D:\Untrusted"),
    )

    with pytest.raises(ReplayError, match="resolved to untrusted path"):
        opa_command(["opa", "eval"])


def test_stable_artifact_ref_falls_back_to_absolute_path_across_drives(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path = tmp_path / "state.sqlite"
    output_dir = tmp_path / "out"

    def cross_drive_relpath(path: Path, start: Path) -> str:
        del path, start
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    monkeypatch.setattr(counterfactual_module.os.path, "relpath", cross_drive_relpath)

    assert counterfactual_module._stable_artifact_ref(artifact_path, output_dir) == artifact_path.resolve().as_posix()


def test_opa_eval_uses_windows_process_group_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_opa_eval = cast(
        Callable[[list[str], str, float | None], subprocess.CompletedProcess[str]],
        vars(replay_module)["_run_opa_eval"],
    )
    popen_kwargs: dict[str, Any] = {}

    def popen(args: list[str], **kwargs: Any) -> _FakeOpaProcess:
        popen_kwargs.update(kwargs)
        return _FakeOpaProcess(args, stdout="{}")

    monkeypatch.setattr("oep_permissions.replay.os.name", "nt")
    monkeypatch.setattr(replay_module.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False)
    monkeypatch.setattr("oep_permissions.replay.subprocess.Popen", popen)

    result = run_opa_eval(["opa", "eval"], "{}", 1.0)

    assert result.returncode == 0
    assert popen_kwargs["creationflags"] == 512


def test_opa_termination_uses_windows_ctrl_break(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terminate_opa_process = cast(
        Callable[[_FakeOpaProcess], None],
        vars(replay_module)["_terminate_opa_process"],
    )
    kill_calls: list[tuple[int, int]] = []

    def kill(pid: int, signal_value: int) -> None:
        kill_calls.append((pid, signal_value))

    monkeypatch.setattr("oep_permissions.replay.os.name", "nt")
    monkeypatch.setattr(replay_module.signal, "CTRL_BREAK_EVENT", 21, raising=False)
    monkeypatch.setattr("oep_permissions.replay.os.kill", kill)
    process = _FakeOpaProcess(["wrapper"])

    terminate_opa_process(process)

    assert kill_calls == [(process.pid, 21)]
    assert process.killed is False


def test_opa_termination_falls_back_to_direct_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terminate_opa_process = cast(
        Callable[[_FakeOpaProcess], None],
        vars(replay_module)["_terminate_opa_process"],
    )

    def killpg(pid: int, signal_value: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr("oep_permissions.replay.os.name", "posix")
    monkeypatch.setattr("oep_permissions.replay.os.killpg", killpg)
    process = _FakeOpaProcess(["wrapper"])

    terminate_opa_process(process)

    assert process.killed is True


def test_decision_id_batch_parameters_use_fixed_placeholder_buckets() -> None:
    padded_parameters = cast(
        Callable[[list[str]], tuple[str | None, ...]],
        vars(replay_module)["_padded_decision_id_parameters"],
    )
    placeholders = cast(
        Callable[[int], str],
        vars(replay_module)["_decision_id_placeholders"],
    )

    assert padded_parameters(["a", "b", "c"]) == ("a", "b", "c", None)
    assert placeholders(3) == "?,?,?,?"
    assert len(padded_parameters([str(index) for index in range(513)])) == 900


def test_batch_reconstruction_caches_trace_and_manifest_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = run_compound_reliability_counterfactual(tmp_path / "compound")
    real_loads_object = cast(
        Callable[[object, str], dict[str, Any]],
        vars(replay_module)["_loads_object"],
    )
    load_counts: dict[str, int] = {}

    def counting_loads_object(text: object, field: str) -> dict[str, Any]:
        load_counts[field] = load_counts.get(field, 0) + 1
        return real_loads_object(text, field)

    monkeypatch.setattr("oep_permissions.replay._loads_object", counting_loads_object)
    records = replay_module.reconstruct_decisions(
        result.state_path,
        [
            f"pder_code_review_compound_reliability_step_{index:04d}"
            for index in range(1, result.total_steps + 1)
        ],
    )

    assert len(records) == result.total_steps
    assert load_counts["permission payload"] == result.total_steps
    assert load_counts["event payload"] == result.total_steps
    assert load_counts["trace payload"] == 1
    assert load_counts["manifest payload"] == 1


class _FakeOpaProcess:
    pid = 999_999

    def __init__(
        self,
        args: list[str],
        *,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
        timeout: bool = False,
        unexpected_exception: BaseException | None = None,
        expected_timeout: float | None = None,
    ) -> None:
        self.args = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.timeout = timeout
        self.unexpected_exception = unexpected_exception
        self.expected_timeout = expected_timeout
        self.killed = False
        self.waited = False
        self.communicate_calls = 0

    def communicate(
        self,
        input: str | None = None,
        timeout: float | None = None,
    ) -> tuple[str, str]:
        self.communicate_calls += 1
        if self.expected_timeout is not None and timeout is not None:
            assert timeout == self.expected_timeout
        if self.unexpected_exception is not None and self.communicate_calls == 1:
            raise self.unexpected_exception
        if self.timeout and self.communicate_calls == 1:
            raise subprocess.TimeoutExpired(cmd=self.args, timeout=timeout or 0.0)
        return self.stdout, self.stderr

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None) -> int:
        self.waited = True
        return self.returncode


def _sqlite_payload(state_path: Path, query: str, parameters: tuple[object, ...]) -> dict[str, Any]:
    connection = sqlite3.connect(state_path)
    try:
        row = connection.execute(query, parameters).fetchone()
        assert row is not None
        payload = json.loads(row[0])
        assert isinstance(payload, dict)
        return payload
    finally:
        connection.close()


def _sqlite_update_payload(
    state_path: Path,
    query: str,
    payload: dict[str, Any],
    parameters: tuple[object, ...],
) -> None:
    _sqlite_update_raw_payload(
        state_path,
        query,
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        parameters,
    )


def _sqlite_update_raw_payload(
    state_path: Path,
    query: str,
    payload_json: str,
    parameters: tuple[object, ...],
) -> None:
    connection = sqlite3.connect(state_path)
    try:
        connection.execute(query, (payload_json, *parameters))
        connection.commit()
    finally:
        connection.close()


def _sqlite_values(state_path: Path, query: str) -> list[object]:
    connection = sqlite3.connect(state_path)
    try:
        return [row[0] for row in connection.execute(query).fetchall()]
    finally:
        connection.close()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


SQLITE_ROW_COUNT_TABLES = frozenset(("artifacts", "events", "permissions", "traces", "findings", "evals"))


def _sqlite_row_counts(state_path: Path) -> dict[str, int]:
    connection = sqlite3.connect(state_path)
    try:
        return {
            table: _sqlite_row_count(connection, table)
            for table in sorted(SQLITE_ROW_COUNT_TABLES)
        }
    finally:
        connection.close()


def _sqlite_row_count(connection: sqlite3.Connection, table: str) -> int:
    if table not in SQLITE_ROW_COUNT_TABLES:
        raise ValueError(f"invalid replay-state table: {table}")
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_sqlite_row_count_rejects_unknown_table(tmp_path: Path) -> None:
    state_path = tmp_path / "code_review_agent.sqlite"
    run_demo(state_path)
    connection = sqlite3.connect(state_path)
    try:
        with pytest.raises(ValueError, match="invalid replay-state table"):
            _sqlite_row_count(connection, "events; DROP TABLE events")
    finally:
        connection.close()


def _inject_nd_builtin_cache(state_path: Path, nd_builtin_cache: dict[str, object]) -> None:
    connection = sqlite3.connect(state_path)
    try:
        row = connection.execute(
            "SELECT payload_json FROM permissions WHERE packet_id = ?",
            (DECISION_ID,),
        ).fetchone()
        assert row is not None
        packet = json.loads(row[0])
        packet["nd_builtin_cache"] = nd_builtin_cache
        connection.execute(
            "UPDATE permissions SET payload_json = ? WHERE packet_id = ?",
            (json.dumps(packet, sort_keys=True, separators=(",", ":")), DECISION_ID),
        )
        connection.commit()
    finally:
        connection.close()


def _write_deny_policy(tmp_path: Path) -> Path:
    alt_policy_path = tmp_path / "counterfactual_policy.rego"
    alt_policy_path.write_text(
        """
package oep.permissions

decision := {
    "allow": false,
    "matched_rule": "deny_replayed_model_alias",
    "policy_id": "opa-tool-permission-policy",
    "policy_version": "0.3-test",
    "reason": "counterfactual policy blocks the stored model alias",
    "decision_code": "COUNTERFACTUAL_POLICY_DENY",
} if {
    input.action.action_type == "inspect_diff"
    input.model_alias == "deterministic-mock-reviewer"
    input.scoped_credential_lifetime == "PT15M"
}
""",
        encoding="utf-8",
    )
    return alt_policy_path
