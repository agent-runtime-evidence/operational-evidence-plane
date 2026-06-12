"""Filesystem helpers for packaged playbook artifacts."""

from oep_verify.resources import package_resource_loader

_resource_path = package_resource_loader("oep_playbooks")


RECONSTRUCTION_RULES_PATH = _resource_path("rollback_reconstruction.md")
SCHEMA_PATH = _resource_path("schema", "reconstruction_packet.v0.schema.json")
EXAMPLE_PATH = _resource_path("examples", "code_review_reconstruction_packet.v0.json")
DENIED_EXAMPLE_PATH = _resource_path("examples", "code_review_denied_reconstruction_packet.v0.json")
PACKAGE_ROOT = SCHEMA_PATH.parents[1]
EXPECTED_SCHEMA_TITLE = "Operational Evidence Plane Reconstruction Packet v0"

__all__ = [
    "DENIED_EXAMPLE_PATH",
    "EXAMPLE_PATH",
    "EXPECTED_SCHEMA_TITLE",
    "PACKAGE_ROOT",
    "RECONSTRUCTION_RULES_PATH",
    "SCHEMA_PATH",
]
