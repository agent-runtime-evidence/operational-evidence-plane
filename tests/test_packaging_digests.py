"""Digest updaters, packaged-resource sync, and package build checks."""

from __future__ import annotations

import json
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest
from helpers import (
    ROOT,
    load_script_module,
)

from oep_verify.verify_support import (
    load_json_object,
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
