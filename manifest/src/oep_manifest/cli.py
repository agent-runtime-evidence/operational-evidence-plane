"""Command-line checks for packaged release manifests."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from oep_manifest.paths import EXAMPLE_PATH, SCHEMA_PATH

EXPECTED_LAYERS = (
    "model",
    "prompt",
    "tool_schema",
    "policy",
    "workflow",
    "rollout",
    "eval",
    "data_state",
)


def check_resolved_digest(layer: str, binding: dict[str, Any], artifact_root: Path) -> None:
    from oep_verify.verify_support import require, require_string, sha256_digest

    if binding.get("binding_status") != "resolved":
        return

    uri = require_string(binding.get("uri"), f"{layer} resolved binding must have a uri")
    digest = require_string(binding.get("digest"), f"{layer} resolved binding must have a digest")

    artifact_path = artifact_root / uri
    require(artifact_path.exists(), f"{layer} resolved uri must point to a file or directory: {uri}")
    require(sha256_digest(artifact_path) == digest, f"{layer} digest mismatch for {uri}")


def check_manifest(schema_path: Path, manifest_path: Path, *, artifact_root: Path | None = None) -> None:
    from oep_verify.verify_support import (
        load_json_object,
        require,
        require_json_list,
        require_json_object,
        require_resolved_layer_bindings,
        validate_json_schema,
    )

    schema = load_json_object(schema_path)
    manifest = load_json_object(manifest_path)
    validate_json_schema(schema, manifest, instance_path=manifest_path)

    require(schema.get("title") == "Operational Evidence Plane Release Manifest v0", "bad schema")
    require(manifest.get("schema_version") == "oep.release_manifest.v0", "bad schema_version")
    require(str(manifest.get("manifest_id", "")).startswith("rmf_"), "bad manifest_id")
    release = require_json_object(manifest.get("release"), "release must be an object")
    if release.get("status") in {"candidate", "active"}:
        require_resolved_layer_bindings(manifest, f"{release.get('status')} manifest")

    layer_bindings = require_json_object(manifest.get("layer_bindings"), "layer_bindings must be an object")
    require(set(layer_bindings) == set(EXPECTED_LAYERS), "layer set mismatch")

    for layer in EXPECTED_LAYERS:
        binding = require_json_object(layer_bindings[layer], f"{layer} binding must be an object")
        require(binding.get("layer_type") == layer, f"{layer} binding has wrong layer_type")
        require(
            binding.get("binding_status") in {"declared", "resolved", "external", "missing"},
            f"{layer} has bad binding_status",
        )
        require(bool(binding.get("evidence_role")), f"{layer} is missing evidence_role")
        if artifact_root is not None:
            check_resolved_digest(layer, binding, artifact_root)

    claim_boundaries = require_json_list(manifest.get("claim_boundaries"), "claim_boundaries must be a list")
    require(len(claim_boundaries) == 7, "expected seven claim boundaries")
    require(len(set(claim_boundaries)) == len(claim_boundaries), "claim boundaries must be unique")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Validate an Operational Evidence Plane release manifest.")
    parser.add_argument("--schema", type=Path, default=SCHEMA_PATH, help="Release manifest JSON Schema path.")
    parser.add_argument("--manifest", type=Path, default=EXAMPLE_PATH, help="Release manifest JSON path.")
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=None,
        help="Optional repository root used to verify resolved binding digests.",
    )
    args = parser.parse_args(argv)

    check_manifest(args.schema, args.manifest, artifact_root=args.artifact_root)
    print("Release manifest checks passed")


if __name__ == "__main__":
    main()
