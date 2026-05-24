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
from typing import Any

import oep_demo.runner as demo_runner
import pytest
from oep_demo import deterministic_review, run_demo
from oep_demo.runner import create_schema

import oep_verify.verify_support as verify_support
from oep_verify.scenarios import REPO_ROOT, get_scenario, scenario_names
from oep_verify.verify_support import (
    load_json_object,
    require_datetime_not_after,
    require_resolved_layer_bindings,
    sha256_digest,
    validate_json_schema,
    validate_json_schema_from_path,
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
    with pytest.raises(ValueError, match="created_at must not be after event_time"):
        require_datetime_not_after(
            "2026-05-04T00:00:02Z",
            "2026-05-04T00:00:01Z",
            "created_at",
            "event_time",
        )


def test_json_schema_format_validation_rejects_bad_datetime() -> None:
    schema = load_json_object(ROOT / "manifest" / "schema" / "release_manifest.v0.schema.json")
    manifest = load_json_object(ROOT / "manifest" / "examples" / "code_review_agent_release.v0.json")
    manifest["created_at"] = "not-a-date-time"

    with pytest.raises(ValueError, match="created_at"):
        validate_json_schema(
            schema,
            manifest,
            instance_path=ROOT / "manifest" / "examples" / "code_review_agent_release.v0.json",
        )


def test_json_schema_validation_requires_active_format_checker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(verify_support, "JSON_SCHEMA_REQUIRED_FORMATS", ("date-time", "missing-format"))

    with pytest.raises(RuntimeError, match="jsonschema format dependencies"):
        validate_json_schema(
            {"type": "string", "format": "date-time", "description": str(tmp_path)},
            "2026-05-04T00:00:00Z",
            instance_path=tmp_path / "format_check.json",
        )


def test_verify_support_rejects_invalid_helper_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    list_json = tmp_path / "list.json"
    list_json.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(TypeError, match="must contain a JSON object"):
        load_json_object(list_json)

    with pytest.raises(ValueError, match="bad condition"):
        verify_support.require(False, "bad condition")
    with pytest.raises(TypeError, match="object required"):
        verify_support.require_json_object([], "object required")
    with pytest.raises(TypeError, match="list required"):
        verify_support.require_json_list({}, "list required")
    with pytest.raises(TypeError, match="string required"):
        verify_support.require_string(1, "string required")

    fake_opa = tmp_path / "opa"
    fake_opa.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"version\" ]; then\n"
        "  echo 'Version: 1.7.1'\n"
        "fi\n",
        encoding="utf-8",
    )
    fake_opa.chmod(0o755)
    monkeypatch.setenv("OEP_OPA_BIN_PATH", str(fake_opa))
    monkeypatch.setattr("oep_verify.verify_support.shutil.which", lambda _name: None)
    assert verify_support.require_executable("opa", "unit test") == str(fake_opa)

    prerelease_opa = tmp_path / "prerelease-opa"
    prerelease_opa.write_text("#!/bin/sh\necho 'Version: 1.8-rc1'\n", encoding="utf-8")
    prerelease_opa.chmod(0o755)
    monkeypatch.setenv("OEP_OPA_BIN_PATH", str(prerelease_opa))
    assert verify_support.require_executable("opa", "unit test") == str(prerelease_opa)

    old_opa = tmp_path / "old-opa"
    old_opa.write_text("#!/bin/sh\necho 'Version: 0.64.0'\n", encoding="utf-8")
    old_opa.chmod(0o755)
    monkeypatch.setenv("OEP_OPA_BIN_PATH", str(old_opa))
    with pytest.raises(ValueError, match="opa 1\\.x is required"):
        verify_support.require_executable("opa", "unit test")

    monkeypatch.setenv("OEP_OPA_BIN_PATH", str(tmp_path / "missing-opa"))
    with pytest.raises(ValueError, match="OEP_OPA_BIN_PATH"):
        verify_support.require_executable("opa", "unit test")

    monkeypatch.delenv("OEP_OPA_BIN_PATH")
    monkeypatch.delenv("OPA_PATH", raising=False)
    with pytest.raises(FileNotFoundError, match="opa executable is required"):
        verify_support.require_executable("opa", "unit test")

    with pytest.raises(ValueError, match="created_at must be a valid date-time"):
        verify_support.parse_datetime("not-a-date-time", "created_at")
    with pytest.raises(ValueError, match="created_at must include a timezone"):
        verify_support.parse_datetime("2026-05-04T00:00:00", "created_at")

    default_path = tmp_path / "default"
    monkeypatch.delenv("OEP_TEST_PATH", raising=False)
    assert verify_support.path_from_env(tmp_path, "OEP_TEST_PATH", default_path) == default_path

    absolute_path = tmp_path / "absolute"
    monkeypatch.setenv("OEP_TEST_PATH", str(absolute_path))
    assert verify_support.path_from_env(tmp_path, "OEP_TEST_PATH", default_path) == absolute_path

    monkeypatch.setenv("OEP_TEST_PATH", "relative")
    assert verify_support.path_from_env(tmp_path, "OEP_TEST_PATH", default_path) == tmp_path / "relative"

    connection = sqlite3.connect(":memory:")
    try:
        with pytest.raises(ValueError, match="query returned no rows"):
            verify_support.scalar(connection, "SELECT 1 WHERE 0", ())
    finally:
        connection.close()

    with pytest.raises(ValueError, match="digest path must point to a file or directory"):
        sha256_digest(tmp_path / "missing")

    with pytest.raises(ValueError, match="invalid JSON Schema") as invalid_schema_error:
        validate_json_schema({"type": 1}, {}, instance_path=tmp_path / "bad.schema.json")
    assert "invalid JSON Schema for <schema>" in str(invalid_schema_error.value)
    assert "bad.schema.json" not in str(invalid_schema_error.value)

    validate_json_schema(
        {"type": "array", "items": {"type": "integer"}},
        [1, 2, 3],
        instance_path=tmp_path / "array.json",
    )

    with pytest.raises(ValueError) as schema_error:
        validate_json_schema(
            {
                "type": "object",
                "required": ["name", "count"],
                "properties": {
                    "name": {"type": "string"},
                    "count": {"type": "integer"},
                },
            },
            {"name": 123},
            instance_path=tmp_path / "multi_error.json",
        )
    schema_message = str(schema_error.value)
    assert "name" in schema_message
    assert "count" in schema_message

    with pytest.raises(ValueError) as pointer_error:
        validate_json_schema(
            {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}},
                        },
                    }
                },
            },
            {"items": [{"name": "ok"}, {"name": 123}]},
            instance_path=tmp_path / "nested_array.json",
        )
    assert "/items/1/name" in str(pointer_error.value)

    schema_path = tmp_path / "reloadable.schema.json"
    schema_path.write_text(json.dumps({"type": "string"}), encoding="utf-8")
    validate_json_schema_from_path(schema_path, "ok", instance_path=tmp_path / "reloadable.json")

    schema_path.write_text(json.dumps({"type": "integer"}), encoding="utf-8")
    stat = schema_path.stat()
    os.utime(schema_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

    with pytest.raises(ValueError, match="<root>: 'ok' is not of type 'integer'"):
        validate_json_schema_from_path(schema_path, "ok", instance_path=tmp_path / "reloadable.json")
    validate_json_schema_from_path(schema_path, 1, instance_path=tmp_path / "reloadable.json")


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

    (tree / "a.txt").write_text("a", encoding="utf-8")
    mode_digest = sha256_digest(tree)
    (tree / "a.txt").chmod(0o600)
    assert sha256_digest(tree) == mode_digest
    (tree / "a.txt").chmod(0o755)
    assert sha256_digest(tree) != mode_digest


def test_replay_ready_requires_resolved_manifest_layers() -> None:
    manifest = load_json_object(ROOT / "manifest" / "examples" / "code_review_agent_release.v0.json")
    manifest["layer_bindings"]["prompt"]["binding_status"] = "declared"
    manifest["layer_bindings"]["prompt"]["digest"] = None

    with pytest.raises(ValueError, match="replay-ready trace requires resolved release layer bindings: prompt"):
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


def test_dtr_jsonl_sort_uses_kind_and_id_tie_breakers() -> None:
    module = load_script_module(
        "integrations/decision-trace-reconstructor/scripts/to_dtr_jsonl.py",
        "to_dtr_jsonl_sort_test",
    )
    records = [
        {"id": "tool_b", "ts": 1.0, "kind": "tool"},
        {"id": "policy_z", "ts": 1.0, "kind": "policy"},
        {"id": "policy_a", "ts": 1.0, "kind": "policy"},
    ]

    sorted_records = module.sort_jsonl_records(records)

    assert [(record["kind"], record["id"]) for record in sorted_records] == [
        ("policy", "policy_a"),
        ("policy", "policy_z"),
        ("tool", "tool_b"),
    ]


def test_run_demo_replaces_existing_state_with_backup_api(tmp_path: Path) -> None:
    state_path = tmp_path / "state.sqlite"
    stale = sqlite3.connect(state_path)
    try:
        stale.execute("PRAGMA journal_mode = WAL")
        stale.execute("CREATE TABLE stale_rows (id INTEGER PRIMARY KEY)")
        stale.execute("INSERT INTO stale_rows (id) VALUES (1)")
        stale.commit()
    finally:
        stale.close()

    reader = sqlite3.connect(state_path)
    event_id = ""
    try:
        reader.execute("BEGIN")
        assert reader.execute("SELECT COUNT(*) FROM stale_rows").fetchone() == (1,)

        result = run_demo(state_path)
        assert result.state_path == state_path
        event_id = result.event_id
        assert reader.execute("SELECT COUNT(*) FROM stale_rows").fetchone() == (1,)
    finally:
        reader.close()

    with sqlite3.connect(state_path) as connection:
        stale_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("stale_rows",),
        ).fetchone()
        assert stale_table is None
        event_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        assert event_count == (1,)


def test_run_demo_retries_transient_backup_lock_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "state.sqlite"
    real_backup = demo_runner._backup_sqlite_state
    backup_calls = 0
    sleep_calls: list[float] = []

    def flaky_backup(src: Path, dst: Path) -> None:
        nonlocal backup_calls
        backup_calls += 1
        if backup_calls < 3:
            raise sqlite3.OperationalError("database is locked")
        real_backup(src, dst)

    monkeypatch.setattr("oep_demo.runner._backup_sqlite_state", flaky_backup)
    monkeypatch.setattr("oep_demo.runner.time.sleep", sleep_calls.append)

    result = run_demo(state_path)

    assert result.state_path == state_path
    assert backup_calls == 3
    assert sleep_calls == [0.05, 0.1]
    assert state_path.exists()


def test_run_demo_publishes_backup_with_atomic_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "state.sqlite"
    publish_path = tmp_path / ".state.sqlite.publish_tmp"
    real_replace = os.replace
    replace_calls: list[tuple[Path, Path]] = []

    def capture_replace(src: Path, dst: Path) -> None:
        replace_calls.append((src, dst))
        real_replace(src, dst)

    monkeypatch.setattr("oep_demo.runner.os.replace", capture_replace)

    result = run_demo(state_path)

    assert result.state_path == state_path
    assert replace_calls == [(publish_path, state_path)]
    assert state_path.exists()
    assert not publish_path.exists()
    assert not publish_path.with_name(f"{publish_path.name}-wal").exists()
    assert not publish_path.with_name(f"{publish_path.name}-shm").exists()


def test_run_demo_retries_transient_publish_replace_permission_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "state.sqlite"
    real_replace = os.replace
    replace_calls = 0
    sleep_calls: list[float] = []

    def flaky_replace(src: Path, dst: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls < 3:
            raise PermissionError("destination is locked")
        real_replace(src, dst)

    monkeypatch.setattr("oep_demo.runner.os.replace", flaky_replace)
    monkeypatch.setattr("oep_demo.runner.time.sleep", sleep_calls.append)

    result = run_demo(state_path)

    assert result.state_path == state_path
    assert replace_calls == 3
    assert sleep_calls == [0.05, 0.1]
    assert state_path.exists()


def test_checkpoint_state_uses_passive_wal_checkpoint() -> None:
    statements: list[str] = []
    connection = sqlite3.connect(":memory:")
    try:
        connection.set_trace_callback(statements.append)
        demo_runner.checkpoint_state(connection)
    finally:
        connection.close()

    assert any("PRAGMA wal_checkpoint(PASSIVE)" in statement for statement in statements)


def test_connect_state_rejects_existing_state(tmp_path: Path) -> None:
    state_path = tmp_path / "state.sqlite"
    state_path.write_bytes(b"placeholder")

    with pytest.raises(RuntimeError, match="refusing to reset existing SQLite state in place"):
        demo_runner.connect_state(state_path)


def test_connect_state_reports_missing_sqlite_json_support(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class JsonlessConnection:
        def execute(self, sql: str, parameters: object = ()) -> object:
            if "json_valid" in sql:
                raise sqlite3.OperationalError("no such function: json_valid")
            return self

        def close(self) -> None:
            return None

    def connect(*args: Any, **kwargs: Any) -> JsonlessConnection:
        return JsonlessConnection()

    monkeypatch.setattr("oep_demo.runner.sqlite3.connect", connect)

    with pytest.raises(RuntimeError, match="SQLite JSON functions are required"):
        demo_runner.connect_state(tmp_path / "state.sqlite")


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
    with pytest.raises(ValueError, match="replay state ref mismatch"):
        module.check_scenario(scenario, state_path=state_path)


def test_schema_validation_rejects_extra_properties() -> None:
    schema = load_json_object(ROOT / "events" / "schema" / "agent_step_event.v0.schema.json")
    event = load_json_object(ROOT / "events" / "examples" / "code_review_agent_step.v0.json")
    event["unexpected_extra_field"] = True

    with pytest.raises(ValueError, match="Additional properties are not allowed"):
        validate_json_schema(
            schema,
            event,
            instance_path=ROOT / "events" / "examples" / "code_review_agent_step.v0.json",
        )


def test_schema_validation_rejects_bad_trace_id() -> None:
    schema = load_json_object(ROOT / "events" / "schema" / "agent_step_event.v0.schema.json")
    event = load_json_object(ROOT / "events" / "examples" / "code_review_agent_step.v0.json")
    event["trace_id"] = "not-a-trace-id"

    with pytest.raises(ValueError, match="trace_id"):
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


def test_update_manifest_digests_rejects_missing_manifest_path(tmp_path: Path) -> None:
    module = load_script_module(
        "manifest/scripts/update_manifest_digests.py",
        "update_manifest_digests_missing_path_test",
    )
    missing_manifest = tmp_path / "missing_release_manifest.v0.json"

    with pytest.raises(SystemExit, match="release manifest not found"):
        module.main(
            [
                "--manifest",
                str(missing_manifest),
                "--check",
            ]
        )


def test_update_manifest_digests_rejects_missing_binding_uri(tmp_path: Path) -> None:
    module = load_script_module(
        "manifest/scripts/update_manifest_digests.py",
        "update_manifest_digests_missing_uri_test",
    )
    manifest = load_json_object(ROOT / "manifest" / "examples" / "code_review_agent_release.v0.json")
    manifest["layer_bindings"]["workflow"]["uri"] = "demo/src/oep_demo_missing"
    manifest_path = tmp_path / "release_manifest.v0.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SystemExit, match="resolved uri must point to a file or directory"):
        module.main(
            [
                "--manifest",
                str(manifest_path),
                "--check",
            ]
        )


def test_update_manifest_digests_cli_rejects_missing_manifest_path(tmp_path: Path) -> None:
    missing_manifest = tmp_path / "missing_release_manifest.v0.json"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "manifest" / "scripts" / "update_manifest_digests.py"),
            "--manifest",
            str(missing_manifest),
            "--check",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "release manifest not found" in result.stderr


def test_update_manifest_digests_cli_rejects_missing_binding_uri(tmp_path: Path) -> None:
    manifest = load_json_object(ROOT / "manifest" / "examples" / "code_review_agent_release.v0.json")
    manifest["layer_bindings"]["workflow"]["uri"] = "demo/src/oep_demo_missing"
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
    assert "resolved uri must point to a file or directory" in result.stderr


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


def test_sync_packaged_resources_copies_canonical_artifacts(tmp_path: Path) -> None:
    from oep_verify.artifacts import PackagedArtifact

    module = load_script_module("scripts/sync_packaged_resources.py", "sync_packaged_resources_test")
    canonical = tmp_path / "canonical.txt"
    resource = tmp_path / "workspace" / "src" / "oep_demo" / "resources" / "fixtures" / "fixture.txt"
    canonical.write_text("canonical", encoding="utf-8")
    resource.parent.mkdir(parents=True)
    resource.write_text("drifted", encoding="utf-8")

    synced = module.sync_packaged_resources(
        tmp_path,
        (PackagedArtifact("canonical.txt", "workspace", "oep_demo/resources/fixtures/fixture.txt"),),
    )

    assert synced == ["workspace/src/oep_demo/resources/fixtures/fixture.txt"]
    assert resource.read_text(encoding="utf-8") == "canonical"


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


def test_mcp_adapter_serializes_generic_arguments() -> None:
    module = load_script_module(
        "integrations/mcp/scripts/to_oep_permission.py",
        "mcp_projection_generic_args_test",
    )
    mcp_event = json.loads(
        (ROOT / "integrations" / "mcp" / "examples" / "code_review_mcp_tool_call.v0.json").read_text(encoding="utf-8")
    )
    mcp_event["request"]["params"]["arguments"] = {
        "line": 42,
        "path": "src/example.py",
    }

    projected = module.project_to_oep_permission(mcp_event)

    assert projected["requested_action"]["input_ref"] == '{"line":42,"path":"src/example.py"}'


def test_replay_schema_enforces_foreign_keys(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "state.sqlite")
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        create_schema(connection)
        index_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'idx_%'"
            ).fetchall()
        }
        assert "idx_events_trace_id" not in index_names
        assert "idx_permissions_fk" not in index_names
        assert "idx_events_trace_manifest" in index_names
        assert "idx_permissions_event_id" in index_names
        assert "idx_findings_event_trace" in index_names

        event_unique_indexes = [
            row
            for row in connection.execute("PRAGMA index_list('events')").fetchall()
            if row[2]
        ]
        assert len(event_unique_indexes) == 1

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO artifacts (kind, artifact_id, path, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                ("release_manifest", "rmf_invalid_json", "manifest.json", "{not-json"),
            )

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

        with pytest.raises(sqlite3.IntegrityError):
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
                    "pder_missing_event",
                    "evt_missing_event",
                    "tool_read_diff_0001",
                    "11111111111111111111111111111111",
                    "2222222222222222",
                    1,
                    "missing event",
                    "{}",
                ),
            )
    finally:
        connection.close()
