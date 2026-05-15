from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest
from oep_demo import deterministic_review, run_demo
from oep_demo.runner import create_schema

from oep_verify.scenarios import REPO_ROOT, get_scenario, scenario_names
from oep_verify.verify_support import (
    load_json_object,
    require_datetime_not_after,
    require_resolved_layer_bindings,
    sha256_digest,
    validate_json_schema,
)

ROOT = Path(__file__).resolve().parents[1]

VERIFY_SCRIPTS = (
    ("manifest/scripts/check_release_manifest.py", "Release manifest checks passed"),
    ("events/scripts/check_agent_step_event.py", "Agent step event checks passed"),
    ("permissions/scripts/check_tool_permission_packet.py", "Tool permission packet checks passed"),
    ("demo/scripts/run_code_review_demo.py", "Generated demo state:"),
    ("demo/scripts/check_replay_state.py", "Demo replay state checks passed"),
    ("traces/scripts/check_eval_result.py", "Eval result checks passed"),
    ("traces/scripts/check_operational_trace.py", "Trace bundle checks passed"),
    ("playbooks/scripts/check_reconstruction_packet.py", "Reconstruction packet checks passed"),
    ("translations/bedrock/scripts/check_bedrock_translation.py", "Bedrock translation checks passed"),
    ("integrations/mcp/scripts/to_oep_permission.py", "MCP -> OEP permission packet projection checks passed"),
    ("scripts/check_public_docs.py", "Public documentation checks passed"),
)


def load_script_module(relative_path: str, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, ROOT / relative_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_script(
    relative_path: str,
    *,
    args: Sequence[str] = (),
    env: dict[str, str] | None = None,
) -> str:
    result = subprocess.run(
        [sys.executable, str(ROOT / relative_path), *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )
    return result.stdout


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


def test_deterministic_review_generates_unique_finding_ids() -> None:
    findings = deterministic_review("+ return None\n+ return None\n")
    assert [finding["finding_id"] for finding in findings] == [
        "finding_return_none_line_0001",
        "finding_return_none_line_0002",
    ]


def test_temporal_order_rejects_inversion() -> None:
    with pytest.raises(AssertionError, match="created_at must not be after event_time"):
        require_datetime_not_after(
            "2026-05-04T00:00:02Z",
            "2026-05-04T00:00:01Z",
            "created_at",
            "event_time",
        )


def test_sha256_digest_hashes_directory_deterministically(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "b.txt").write_text("b", encoding="utf-8")
    (tree / "a.txt").write_text("a", encoding="utf-8")

    digest = sha256_digest(tree)

    pycache = tree / "__pycache__"
    pycache.mkdir()
    (pycache / "ignored.pyc").write_bytes(b"ignored")
    assert sha256_digest(tree) == digest

    (tree / "a.txt").write_text("changed", encoding="utf-8")
    assert sha256_digest(tree) != digest


def test_replay_ready_requires_resolved_manifest_layers() -> None:
    manifest = load_json_object(ROOT / "manifest" / "examples" / "code_review_agent_release.v0.json")
    manifest["layer_bindings"]["prompt"]["binding_status"] = "declared"
    manifest["layer_bindings"]["prompt"]["digest"] = None

    with pytest.raises(AssertionError, match="replay-ready trace requires resolved release layer bindings: prompt"):
        require_resolved_layer_bindings(manifest, "replay-ready trace")


@pytest.mark.parametrize("scenario", scenario_names())
def test_dtr_jsonl_matches_committed_artifact(tmp_path: Path, scenario: str) -> None:
    generated_path = tmp_path / f"{scenario}.jsonl"
    output = run_script(
        "integrations/decision-trace-reconstructor/scripts/to_dtr_jsonl.py",
        args=("--scenario", scenario, "--out", str(generated_path)),
    )

    assert "wrote" in output
    assert generated_path.read_text(encoding="utf-8") == (
        ROOT / "integrations" / "decision-trace-reconstructor" / f"{scenario}.jsonl"
    ).read_text(encoding="utf-8")


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
) -> None:
    state_path = tmp_path / "code_review_agent.sqlite"
    run_demo(state_path)

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
    with pytest.raises(AssertionError, match="replay state ref mismatch"):
        module.check_scenario(scenario, state_path=state_path)


def test_schema_validation_rejects_extra_properties() -> None:
    schema = load_json_object(ROOT / "events" / "schema" / "agent_step_event.v0.schema.json")
    event = load_json_object(ROOT / "events" / "examples" / "code_review_agent_step.v0.json")
    event["unexpected_extra_field"] = True

    with pytest.raises(AssertionError, match="Additional properties are not allowed"):
        validate_json_schema(
            schema,
            event,
            instance_path=ROOT / "events" / "examples" / "code_review_agent_step.v0.json",
        )


def test_schema_validation_rejects_bad_trace_id() -> None:
    schema = load_json_object(ROOT / "events" / "schema" / "agent_step_event.v0.schema.json")
    event = load_json_object(ROOT / "events" / "examples" / "code_review_agent_step.v0.json")
    event["trace_id"] = "not-a-trace-id"

    with pytest.raises(AssertionError, match="trace_id"):
        validate_json_schema(
            schema,
            event,
            instance_path=ROOT / "events" / "examples" / "code_review_agent_step.v0.json",
        )


def test_resolved_manifest_digest_rejects_mismatch(tmp_path: Path) -> None:
    manifest = load_json_object(ROOT / "manifest" / "examples" / "code_review_agent_release.v0.json")
    manifest["layer_bindings"]["policy"]["digest"] = "sha256:" + ("0" * 64)
    manifest_path = tmp_path / "release_manifest.v0.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "manifest" / "scripts" / "update_manifest_digests.py"),
            "--manifest",
            str(manifest_path),
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "digest mismatch" in result.stdout


def test_package_build_rejects_missing_wheel_resource(tmp_path: Path) -> None:
    module = load_script_module("scripts/check_package_build.py", "check_package_build_test")
    wheel_path = tmp_path / "bad.whl"
    missing_file = "oep_demo/resources/fixtures/diff_synthetic_001.patch"

    with zipfile.ZipFile(wheel_path, "w") as archive:
        for expected_file in module.EXPECTED_PACKAGE_FILES:
            if expected_file != missing_file:
                archive.writestr(expected_file, "")

    with pytest.raises(SystemExit, match="wheel is missing package files"):
        module.check_wheel_contents(wheel_path)


def test_package_build_rejects_missing_sdist_source_file(tmp_path: Path) -> None:
    module = load_script_module("scripts/check_package_build.py", "check_package_build_sdist_missing_test")
    sdist_path = tmp_path / "bad.tar.gz"
    root_name = "operational_evidence_plane-0.1.0"
    missing_file = "docs/architecture.md"

    with tarfile.open(sdist_path, "w:gz") as archive:
        for expected_file in module.EXPECTED_PACKAGE_FILES:
            source_path = tmp_path / expected_file
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_text("", encoding="utf-8")
            archive.add(source_path, arcname=f"{root_name}/{expected_file}")
        for expected_file in module.SOURCE_DISTRIBUTION_FILES:
            if expected_file == missing_file:
                continue
            source_path = tmp_path / "source" / expected_file
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_text("", encoding="utf-8")
            archive.add(source_path, arcname=f"{root_name}/{expected_file}")

    with pytest.raises(SystemExit, match="sdist is missing source files"):
        module.check_sdist_contents(sdist_path)


def test_package_build_rejects_packaged_resource_drift(
    tmp_path: Path,
) -> None:
    from oep_verify.artifacts import PackagedArtifact

    module = load_script_module("scripts/check_package_build.py", "check_package_build_drift_test")
    canonical = tmp_path / "canonical.txt"
    resource = tmp_path / "workspace" / "src" / "oep_demo" / "resources" / "fixtures" / "fixture.txt"
    canonical.write_text("canonical", encoding="utf-8")
    resource.parent.mkdir(parents=True)
    resource.write_text("drifted", encoding="utf-8")

    with pytest.raises(SystemExit, match="packaged resource drift"):
        module.check_resource_sync(
            (PackagedArtifact("canonical.txt", "workspace", "oep_demo/resources/fixtures/fixture.txt"),),
            repo_root=tmp_path,
        )


def test_update_permission_digests_detects_drift(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        (ROOT / "manifest" / "examples" / "code_review_agent_release.v0.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    packet = load_json_object(ROOT / "permissions" / "examples" / "code_review_tool_permission.v0.json")
    packet["release_manifest_version"] = "sha256:" + ("0" * 64)
    packet_path = tmp_path / "code_review_tool_permission.v0.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")

    module = load_script_module(
        "permissions/scripts/update_permission_digests.py",
        "update_permission_digests_test",
    )
    assert module.update_permission_digests(manifest_path, (packet_path,), check=True) is False
    assert module.update_permission_digests(manifest_path, (packet_path,), check=False) is True
    refreshed = json.loads(packet_path.read_text(encoding="utf-8"))
    assert refreshed["release_manifest_version"].startswith("sha256:")
    assert refreshed["release_manifest_version"] != "sha256:" + ("0" * 64)


def test_replay_cli_reconstructs_recorded_decision(tmp_path: Path) -> None:
    from oep_permissions import ReplayError, reconstruct_decision

    from oep_verify.cli import main as cli_main

    state_path = tmp_path / "code_review_agent.sqlite"
    run_demo(state_path)

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


def test_mcp_adapter_rejects_canonical_drift(tmp_path: Path) -> None:
    module = load_script_module(
        "integrations/mcp/scripts/to_oep_permission.py",
        "mcp_projection_test",
    )
    mcp_event = json.loads(
        (ROOT / "integrations" / "mcp" / "examples" / "code_review_mcp_tool_call.v0.json").read_text(encoding="utf-8")
    )
    drifted = dict(mcp_event)
    drifted["session"] = {**mcp_event["session"], "policy_bundle_version": "sha256:" + ("0" * 64)}
    drifted_event_path = tmp_path / "drifted_mcp.json"
    drifted_event_path.write_text(json.dumps(drifted), encoding="utf-8")

    canonical_path = ROOT / "permissions" / "examples" / "code_review_tool_permission.v0.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "integrations" / "mcp" / "scripts" / "to_oep_permission.py"),
            "--mcp-event",
            str(drifted_event_path),
            "--compare-with",
            str(canonical_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "MCP -> OEP projection drift" in result.stderr

    projected = module.project_to_oep_permission(mcp_event)
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    assert projected == canonical


def test_replay_schema_enforces_foreign_keys(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "state.sqlite")
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        create_schema(connection)
        with pytest.raises(sqlite3.IntegrityError):
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
                    "evt_missing_trace",
                    "11111111111111111111111111111111",
                    "2222222222222222",
                    "rmf_code_review_agent_2026_05_04_v0",
                    "tool_read_diff_0001",
                    "pder_code_review_read_diff_0001",
                    "{}",
                ),
            )
    finally:
        connection.close()
