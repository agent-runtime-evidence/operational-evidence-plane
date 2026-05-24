"""Update content digests for resolved file or directory bindings in the release manifest."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from oep_verify.verify_support import load_json_object, require_json_object, sha256_digest

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_MANIFEST_PATH = ROOT / "manifest" / "examples" / "code_review_agent_release.v0.json"


def update_manifest_digests(manifest_path: Path, *, check: bool = False) -> bool:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"release manifest not found: {manifest_path}")

    manifest = load_json_object(manifest_path)
    layer_bindings = require_json_object(manifest.get("layer_bindings"), "layer_bindings must be an object")

    changed = False
    for layer, raw_binding in layer_bindings.items():
        binding = require_json_object(raw_binding, f"{layer} binding must be an object")
        if binding.get("binding_status") != "resolved":
            continue

        uri = binding.get("uri")
        if not isinstance(uri, str):
            raise TypeError(f"{layer} resolved binding must have an artifact uri")

        artifact_path = ROOT / uri
        if not artifact_path.exists():
            raise ValueError(f"{layer} resolved uri must point to a file or directory: {uri}")

        expected_digest = sha256_digest(artifact_path)
        if binding.get("digest") != expected_digest:
            changed = True
            if check:
                print(f"{layer}: digest mismatch for {uri}; expected {expected_digest}")
            else:
                binding["digest"] = expected_digest
                print(f"{layer}: updated digest for {uri}")

    if changed and check:
        return False

    if changed:
        manifest_path.write_text(_stable_json(manifest), encoding="utf-8")
    else:
        print("Manifest digests are up to date")
    return True


def _stable_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="Release manifest path to update.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if any resolved binding digest is stale instead of writing updates.",
    )
    args = parser.parse_args(argv)

    try:
        ok = update_manifest_digests(args.manifest, check=args.check)
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
