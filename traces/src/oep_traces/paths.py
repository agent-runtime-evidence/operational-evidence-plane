"""Filesystem helpers for packaged trace artifacts."""

from oep_verify.resources import package_resource_loader

_resource_path = package_resource_loader("oep_traces")


SCHEMA_PATH = _resource_path("schema", "operational_trace.v0.schema.json")
EVAL_SCHEMA_PATH = _resource_path("schema", "eval_result.v0.schema.json")
TRACE_EXAMPLE_PATH = _resource_path("examples", "code_review_agent_trace.v0.json")
DENIED_TRACE_EXAMPLE_PATH = _resource_path("examples", "code_review_agent_denied_trace.v0.json")
EVAL_EXAMPLE_PATH = _resource_path("examples", "code_review_agent_eval.v0.json")
DENIED_EVAL_EXAMPLE_PATH = _resource_path("examples", "code_review_agent_denied_eval.v0.json")
PACKAGE_ROOT = SCHEMA_PATH.parents[1]
EXPECTED_SCHEMA_TITLE = "Operational Evidence Plane Trace Bundle v0"
EXPECTED_EVAL_SCHEMA_TITLE = "Operational Evidence Plane Eval Result v0"

__all__ = [
    "DENIED_EVAL_EXAMPLE_PATH",
    "DENIED_TRACE_EXAMPLE_PATH",
    "EVAL_EXAMPLE_PATH",
    "EVAL_SCHEMA_PATH",
    "EXPECTED_EVAL_SCHEMA_TITLE",
    "EXPECTED_SCHEMA_TITLE",
    "PACKAGE_ROOT",
    "SCHEMA_PATH",
    "TRACE_EXAMPLE_PATH",
]
