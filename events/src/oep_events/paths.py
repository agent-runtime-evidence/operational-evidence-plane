"""Filesystem helpers for packaged event artifacts."""

from oep_verify.resources import package_resource_loader

_resource_path = package_resource_loader("oep_events")


SCHEMA_PATH = _resource_path("schema", "agent_step_event.v0.schema.json")
EXAMPLE_PATH = _resource_path("examples", "code_review_agent_step.v0.json")
DENIED_EXAMPLE_PATH = _resource_path("examples", "code_review_agent_denied_step.v0.json")
PACKAGE_ROOT = SCHEMA_PATH.parents[1]
EXPECTED_SCHEMA_TITLE = "Operational Evidence Plane Agent Step Event v0"

__all__ = ["DENIED_EXAMPLE_PATH", "EXAMPLE_PATH", "EXPECTED_SCHEMA_TITLE", "PACKAGE_ROOT", "SCHEMA_PATH"]
