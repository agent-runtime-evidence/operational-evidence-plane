"""Filesystem helpers for packaged permission artifacts."""

from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path

_RESOURCE_STACK = ExitStack()
_RESOURCE_ROOT = files("oep_permissions").joinpath("resources")


def _resource_path(*parts: str) -> Path:
    return _RESOURCE_STACK.enter_context(as_file(_RESOURCE_ROOT.joinpath(*parts)))


SCHEMA_PATH = _resource_path("schema", "tool_permission_packet.v0.schema.json")
EXAMPLE_PATH = _resource_path("examples", "code_review_tool_permission.v0.json")
DENIED_EXAMPLE_PATH = _resource_path("examples", "code_review_tool_permission_denied.v0.json")
POLICY_PATH = _resource_path("policy", "tool_permissions.rego")
POLICY_TEST_PATH = _resource_path("policy", "tool_permissions_test.rego")
INPUT_PATH = _resource_path("policy", "input", "code_review_read_diff.json")
DENIED_INPUT_PATH = _resource_path("policy", "input", "code_review_write_diff.json")
PACKAGE_ROOT = SCHEMA_PATH.parents[1]

__all__ = [
    "DENIED_EXAMPLE_PATH",
    "DENIED_INPUT_PATH",
    "EXAMPLE_PATH",
    "INPUT_PATH",
    "PACKAGE_ROOT",
    "POLICY_PATH",
    "POLICY_TEST_PATH",
    "SCHEMA_PATH",
]
