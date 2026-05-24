"""Update v0.2 digest fields in tool permission packet examples.

Recomputes `policy_bundle_version` and `release_manifest_version` from
the canonical manifest and policy bundle so the permission packet
examples stay in sync after a manifest or policy change. Run this after
`update_manifest_digests.py` so the manifest digest is final.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from oep_verify.verify_support import (
    load_json_object,
    require_json_object,
    require_string,
    sha256_digest,
)

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_MANIFEST_PATH = ROOT / "manifest" / "examples" / "code_review_agent_release.v0.json"
DEFAULT_PERMISSION_PATHS: tuple[Path, ...] = (
    ROOT / "permissions" / "examples" / "code_review_tool_permission.v0.json",
    ROOT / "permissions" / "examples" / "code_review_tool_permission_denied.v0.json",
)


def _stable_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def derive_versions(manifest_path: Path) -> tuple[str, str]:
    """Return (policy_bundle_version, release_manifest_version) for the manifest."""

    manifest = load_json_object(manifest_path)
    layer_bindings = require_json_object(manifest.get("layer_bindings"), "layer_bindings must be an object")
    policy_binding = require_json_object(layer_bindings.get("policy"), "policy layer binding must be an object")
    policy_bundle_version = require_string(
        policy_binding.get("digest"),
        "manifest policy layer binding must carry a digest",
    )
    release_manifest_version = sha256_digest(manifest_path)
    return policy_bundle_version, release_manifest_version


def update_permission_digests(
    manifest_path: Path,
    permission_paths: tuple[Path, ...],
    *,
    check: bool = False,
) -> bool:
    policy_bundle_version, release_manifest_version = derive_versions(manifest_path)

    overall_ok = True
    for packet_path in permission_paths:
        packet = load_json_object(packet_path)
        label = _display_path(packet_path)

        expected = {
            "policy_bundle_version": policy_bundle_version,
            "release_manifest_version": release_manifest_version,
        }
        changed = False
        for field, expected_value in expected.items():
            if packet.get(field) != expected_value:
                changed = True
                if check:
                    print(f"{label}: {field} mismatch; expected {expected_value}")
                else:
                    packet[field] = expected_value
                    print(f"{label}: updated {field}")

        if changed and check:
            overall_ok = False
            continue

        if changed and not check:
            packet_path.write_text(_stable_json(packet), encoding="utf-8")
        elif not changed:
            print(f"{label}: permission digests are up to date")

    return overall_ok


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="Release manifest path to derive digests from.",
    )
    parser.add_argument(
        "--packet",
        type=Path,
        action="append",
        default=None,
        help="Tool permission packet path to update. May be repeated. Defaults to canonical examples.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if any permission packet digest field is stale instead of writing updates.",
    )
    args = parser.parse_args()

    permission_paths = tuple(args.packet) if args.packet else DEFAULT_PERMISSION_PATHS
    ok = update_permission_digests(args.manifest, permission_paths, check=args.check)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
