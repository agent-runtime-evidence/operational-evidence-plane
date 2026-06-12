"""Filesystem helpers for packaged manifest artifacts."""

from oep_verify.resources import package_resource_loader

_resource_path = package_resource_loader("oep_manifest")


SCHEMA_PATH = _resource_path("schema", "release_manifest.v0.schema.json")
EXAMPLE_PATH = _resource_path("examples", "code_review_agent_release.v0.json")
PACKAGE_ROOT = SCHEMA_PATH.parents[1]
EXPECTED_SCHEMA_TITLE = "Operational Evidence Plane Release Manifest v0"

__all__ = ["EXAMPLE_PATH", "EXPECTED_SCHEMA_TITLE", "PACKAGE_ROOT", "SCHEMA_PATH"]
