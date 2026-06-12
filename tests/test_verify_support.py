"""Unit tests for oep_verify.verify_support helpers."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest
from helpers import (
    ROOT,
)

import oep_verify.verify_support as verify_support
from oep_verify.verify_support import (
    load_json_object,
    require_resolved_layer_bindings,
    sha256_digest,
    validate_json_schema,
    validate_json_schema_from_path,
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
        '#!/bin/sh\nif [ "$1" = "version" ]; then\n  echo \'Version: 1.7.1\'\nfi\n',
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
