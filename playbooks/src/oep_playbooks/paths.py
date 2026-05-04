"""Filesystem helpers for packaged playbook artifacts."""

from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path

_RESOURCE_STACK = ExitStack()
_RESOURCE_ROOT = files("oep_playbooks").joinpath("resources")


def _resource_path(*parts: str) -> Path:
    return _RESOURCE_STACK.enter_context(as_file(_RESOURCE_ROOT.joinpath(*parts)))


RECONSTRUCTION_RULES_PATH = _resource_path("rollback_reconstruction.md")
SCHEMA_PATH = _resource_path("schema", "reconstruction_packet.v0.schema.json")
EXAMPLE_PATH = _resource_path("examples", "code_review_reconstruction_packet.v0.json")
DENIED_EXAMPLE_PATH = _resource_path("examples", "code_review_denied_reconstruction_packet.v0.json")
PACKAGE_ROOT = SCHEMA_PATH.parents[1]

__all__ = ["DENIED_EXAMPLE_PATH", "EXAMPLE_PATH", "PACKAGE_ROOT", "RECONSTRUCTION_RULES_PATH", "SCHEMA_PATH"]
