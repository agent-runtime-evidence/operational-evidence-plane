#!/usr/bin/env python3
"""Copy canonical artifacts into package resource directories."""

from __future__ import annotations

import argparse
import shutil
from collections.abc import Sequence
from pathlib import Path

from oep_verify.artifacts import PACKAGED_ARTIFACTS, PackagedArtifact, packaged_resource_sync_errors

REPO_ROOT = Path(__file__).resolve().parents[1]


def sync_packaged_resources(
    repo_root: Path = REPO_ROOT,
    artifacts: Sequence[PackagedArtifact] = PACKAGED_ARTIFACTS,
) -> list[str]:
    synced: list[str] = []
    for artifact in artifacts:
        canonical = artifact.canonical_file(repo_root)
        packaged = artifact.packaged_file(repo_root)
        if not canonical.is_file():
            raise SystemExit(f"missing canonical resource: {artifact.canonical_path}")
        packaged.parent.mkdir(parents=True, exist_ok=True)
        if packaged.is_file() and canonical.read_bytes() == packaged.read_bytes():
            continue
        shutil.copyfile(canonical, packaged)
        synced.append(artifact.packaged_display_path)
    return synced


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail on drift instead of copying resources.",
    )
    args = parser.parse_args()

    if args.check:
        errors = packaged_resource_sync_errors(REPO_ROOT)
        if errors:
            raise SystemExit("\n".join(errors))
        print("Packaged resources are in sync")
        return

    synced = sync_packaged_resources(REPO_ROOT)
    if synced:
        for path in synced:
            print(f"synced {path}")
    else:
        print("Packaged resources are already in sync")


if __name__ == "__main__":
    main()
