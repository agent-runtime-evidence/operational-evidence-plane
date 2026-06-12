"""Verification scripts, packaged CLIs, scenario registry, and replay CLI joins."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from helpers import (
    ROOT,
    VERIFY_SCRIPTS,
    load_script_module,
    run_script,
)
from oep_demo import run_demo

from oep_verify.scenarios import REPO_ROOT, get_scenario, scenario_names
from oep_verify.verify_support import (
    load_json_object,
)


def test_verify_scripts_use_isolated_state(tmp_path: Path) -> None:
    state_path = tmp_path / "code_review_agent.sqlite"
    env = os.environ.copy()
    env["OEP_DEMO_STATE_PATH"] = str(state_path)

    for relative_path, expected_output in VERIFY_SCRIPTS:
        output = run_script(relative_path, env=env)
        assert expected_output in output

    assert state_path.exists()


def test_scenario_registry_paths_exist() -> None:
    assert ROOT == REPO_ROOT
    for name in scenario_names():
        scenario = get_scenario(name)
        for relative_path in (
            scenario.manifest,
            scenario.event,
            scenario.permission,
            scenario.trace,
            scenario.eval_result,
            scenario.reconstruction,
            scenario.policy_input,
        ):
            assert scenario.path(relative_path).exists(), f"{name} missing {relative_path}"


def test_scenario_registry_rejects_unknown() -> None:
    with pytest.raises(KeyError, match="unknown scenario"):
        get_scenario("missing_scenario")


def test_packaged_manifest_cli_validates_packaged_resources() -> None:
    from oep_manifest.cli import check_manifest
    from oep_manifest.paths import EXAMPLE_PATH, SCHEMA_PATH

    check_manifest(SCHEMA_PATH, EXAMPLE_PATH)


def test_manifest_cli_main_validates_repo_digests(capsys: pytest.CaptureFixture[str]) -> None:
    from oep_manifest.cli import main

    main(
        [
            "--schema",
            str(ROOT / "manifest" / "schema" / "release_manifest.v0.schema.json"),
            "--manifest",
            str(ROOT / "manifest" / "examples" / "code_review_agent_release.v0.json"),
            "--artifact-root",
            str(ROOT),
        ]
    )

    assert "Release manifest checks passed" in capsys.readouterr().out


def test_packaged_reconstruction_cli_validates_packaged_resources() -> None:
    from oep_playbooks.cli import check_reconstruction_packets
    from oep_playbooks.paths import DENIED_EXAMPLE_PATH, EXAMPLE_PATH, SCHEMA_PATH

    check_reconstruction_packets(SCHEMA_PATH, [EXAMPLE_PATH, DENIED_EXAMPLE_PATH])


def test_reconstruction_cli_main_validates_packaged_resources(capsys: pytest.CaptureFixture[str]) -> None:
    from oep_playbooks.cli import main

    main([])

    assert "Reconstruction packet package checks passed" in capsys.readouterr().out


def test_demo_cli_runs_from_packaged_resources(tmp_path: Path) -> None:
    state_path = tmp_path / "cli-demo.sqlite"
    result = subprocess.run(
        [sys.executable, "-m", "oep_demo.cli", "--state-path", str(state_path)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Generated demo state:" in result.stdout
    assert state_path.exists()


def test_opa_policy_unit_tests_pass() -> None:
    subprocess.run(
        [
            "opa",
            "test",
            str(ROOT / "permissions" / "policy" / "tool_permissions.rego"),
            str(ROOT / "permissions" / "policy" / "tool_permissions_test.rego"),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_reconstruction_rejects_replay_state_ref_mismatch(
    tmp_path: Path,
    state_path: Path,
) -> None:
    packet = load_json_object(ROOT / "playbooks" / "examples" / "code_review_reconstruction_packet.v0.json")
    packet["evidence_summary"]["replay_state"]["ref"] = "demo/state/other.sqlite"
    packet_path = tmp_path / "code_review_reconstruction_packet.v0.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")

    scenario = replace(
        get_scenario("code_review_agent"),
        reconstruction=str(packet_path),
    )
    module = load_script_module(
        "playbooks/scripts/check_reconstruction_packet.py",
        "check_reconstruction_packet_test",
    )
    with pytest.raises(ValueError, match="replay state ref mismatch"):
        module.check_scenario(scenario, state_path=state_path)


def test_replay_cli_reconstructs_recorded_decision(tmp_path: Path, state_path: Path) -> None:
    from oep_permissions import ReplayError, reconstruct_decision

    from oep_verify.cli import main as cli_main

    record = reconstruct_decision(state_path, "pder_code_review_read_diff_0001")
    assert record.decision_id == "pder_code_review_read_diff_0001"
    assert record.tool_call_id == "tool_read_diff_0001"
    assert record.model_alias == "deterministic-mock-reviewer"
    assert record.model_provider == "operational-evidence-plane-reference"
    assert record.policy_bundle_version is not None
    assert record.policy_bundle_version.startswith("sha256:")
    assert record.release_manifest_version is not None
    assert record.release_manifest_version.startswith("sha256:")
    assert record.scoped_credential_lifetime == "PT15M"
    assert record.approval_capture is None

    with pytest.raises(ReplayError, match="no recorded decision"):
        reconstruct_decision(state_path, "pder_does_not_exist")

    missing_state = tmp_path / "missing.sqlite"
    with pytest.raises(ReplayError, match="replay state not found"):
        reconstruct_decision(missing_state, "pder_code_review_read_diff_0001")

    denied_event = load_json_object(ROOT / "events" / "examples" / "code_review_agent_denied_step.v0.json")
    connection = sqlite3.connect(state_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "INSERT INTO traces (trace_id, release_manifest_id, status, payload_json) VALUES (?, ?, ?, ?)",
            (denied_event["trace_id"], denied_event["release_manifest_id"], "partial", "{}"),
        )
        connection.execute(
            """
            INSERT INTO events (event_id, trace_id, span_id, release_manifest_id,
                                tool_call_id, permission_packet_ref, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                denied_event["event_id"],
                denied_event["trace_id"],
                denied_event["span_id"],
                denied_event["release_manifest_id"],
                denied_event["tool_call_id"],
                denied_event["permission_packet_ref"],
                json.dumps(denied_event),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ReplayError, match="denied decisions do not generate SQLite replay state"):
        reconstruct_decision(state_path, denied_event["permission_packet_ref"])

    tampered_state_path = tmp_path / "tampered.sqlite"
    run_demo(tampered_state_path)
    tampered = sqlite3.connect(tampered_state_path)
    try:
        tampered.execute(
            "UPDATE permissions SET payload_json = ? WHERE packet_id = ?",
            (
                json.dumps({"not_a_valid_packet": True}),
                "pder_code_review_read_diff_0001",
            ),
        )
        tampered.commit()
    finally:
        tampered.close()
    with pytest.raises(ReplayError, match="failed schema validation"):
        reconstruct_decision(tampered_state_path, "pder_code_review_read_diff_0001")

    corrupt_state_path = tmp_path / "corrupt.sqlite"
    run_demo(corrupt_state_path)
    corrupt = sqlite3.connect(corrupt_state_path)
    try:
        corrupt.execute("PRAGMA ignore_check_constraints = ON")
        corrupt.execute(
            "UPDATE permissions SET payload_json = ? WHERE packet_id = ?",
            ("{not-valid-json", "pder_code_review_read_diff_0001"),
        )
        corrupt.commit()
    finally:
        corrupt.close()
    with pytest.raises(ReplayError, match="permission payload is not valid JSON"):
        reconstruct_decision(corrupt_state_path, "pder_code_review_read_diff_0001")

    cli_main(
        [
            "replay",
            "pder_code_review_read_diff_0001",
            "--state-path",
            str(state_path),
            "--field",
            "decision_id",
        ]
    )

    with pytest.raises(SystemExit, match="unknown replay record field"):
        cli_main(
            [
                "replay",
                "pder_code_review_read_diff_0001",
                "--state-path",
                str(state_path),
                "--field",
                "not_a_field",
            ]
        )
