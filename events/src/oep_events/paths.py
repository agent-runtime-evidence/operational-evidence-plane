"""Filesystem helpers for packaged event artifacts."""

from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path

_RESOURCE_STACK = ExitStack()
_RESOURCE_ROOT = files("oep_events").joinpath("resources")


def _resource_path(*parts: str) -> Path:
    return _RESOURCE_STACK.enter_context(as_file(_RESOURCE_ROOT.joinpath(*parts)))


SCHEMA_PATH = _resource_path("schema", "agent_step_event.v0.schema.json")
EXAMPLE_PATH = _resource_path("examples", "code_review_agent_step.v0.json")
DENIED_EXAMPLE_PATH = _resource_path("examples", "code_review_agent_denied_step.v0.json")
PACKAGE_ROOT = SCHEMA_PATH.parents[1]

__all__ = ["DENIED_EXAMPLE_PATH", "EXAMPLE_PATH", "PACKAGE_ROOT", "SCHEMA_PATH"]
