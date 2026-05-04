"""Filesystem helpers for packaged trace artifacts."""

from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path

_RESOURCE_STACK = ExitStack()
_RESOURCE_ROOT = files("oep_traces").joinpath("resources")


def _resource_path(*parts: str) -> Path:
    return _RESOURCE_STACK.enter_context(as_file(_RESOURCE_ROOT.joinpath(*parts)))


SCHEMA_PATH = _resource_path("schema", "operational_trace.v0.schema.json")
EVAL_SCHEMA_PATH = _resource_path("schema", "eval_result.v0.schema.json")
TRACE_EXAMPLE_PATH = _resource_path("examples", "code_review_agent_trace.v0.json")
DENIED_TRACE_EXAMPLE_PATH = _resource_path("examples", "code_review_agent_denied_trace.v0.json")
EVAL_EXAMPLE_PATH = _resource_path("examples", "code_review_agent_eval.v0.json")
DENIED_EVAL_EXAMPLE_PATH = _resource_path("examples", "code_review_agent_denied_eval.v0.json")
PACKAGE_ROOT = SCHEMA_PATH.parents[1]

__all__ = [
    "DENIED_EVAL_EXAMPLE_PATH",
    "DENIED_TRACE_EXAMPLE_PATH",
    "EVAL_EXAMPLE_PATH",
    "EVAL_SCHEMA_PATH",
    "PACKAGE_ROOT",
    "SCHEMA_PATH",
    "TRACE_EXAMPLE_PATH",
]
