"""Filesystem helpers for packaged event artifacts."""

import atexit
from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path
from threading import Lock

_RESOURCE_STACK = ExitStack()
atexit.register(_RESOURCE_STACK.close)
_RESOURCE_ROOT = files("oep_events").joinpath("resources")
_RESOURCE_LOCK = Lock()
_RESOURCE_PATHS: dict[tuple[str, ...], Path] = {}


def _resource_path(*parts: str) -> Path:
    with _RESOURCE_LOCK:
        cached = _RESOURCE_PATHS.get(parts)
        if cached is None:
            cached = _RESOURCE_STACK.enter_context(as_file(_RESOURCE_ROOT.joinpath(*parts)))
            _RESOURCE_PATHS[parts] = cached
        return cached


SCHEMA_PATH = _resource_path("schema", "agent_step_event.v0.schema.json")
EXAMPLE_PATH = _resource_path("examples", "code_review_agent_step.v0.json")
DENIED_EXAMPLE_PATH = _resource_path("examples", "code_review_agent_denied_step.v0.json")
PACKAGE_ROOT = SCHEMA_PATH.parents[1]
EXPECTED_SCHEMA_TITLE = "Operational Evidence Plane Agent Step Event v0"

__all__ = ["DENIED_EXAMPLE_PATH", "EXAMPLE_PATH", "EXPECTED_SCHEMA_TITLE", "PACKAGE_ROOT", "SCHEMA_PATH"]
