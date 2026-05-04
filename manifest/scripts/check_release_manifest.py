"""Check the local release manifest example against schema and joins."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCHEMA_PATH = ROOT / "manifest" / "schema" / "release_manifest.v0.schema.json"
EXAMPLE_PATH = ROOT / "manifest" / "examples" / "code_review_agent_release.v0.json"


def main() -> None:
    from oep_manifest.cli import check_manifest

    check_manifest(SCHEMA_PATH, EXAMPLE_PATH, artifact_root=ROOT)
    print("Release manifest checks passed")


if __name__ == "__main__":
    main()
