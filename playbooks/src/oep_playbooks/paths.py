"""Filesystem helpers for packaged playbook artifacts."""

import atexit
from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path
from threading import Lock

_RESOURCE_STACK = ExitStack()
atexit.register(_RESOURCE_STACK.close)
_RESOURCE_ROOT = files("oep_playbooks").joinpath("resources")
_RESOURCE_LOCK = Lock()
_RESOURCE_PATHS: dict[tuple[str, ...], Path] = {}


def _resource_path(*parts: str) -> Path:
    with _RESOURCE_LOCK:
        cached = _RESOURCE_PATHS.get(parts)
        if cached is None:
            cached = _RESOURCE_STACK.enter_context(as_file(_RESOURCE_ROOT.joinpath(*parts)))
            _RESOURCE_PATHS[parts] = cached
        return cached


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
