"""Filesystem helpers for packaged permission artifacts."""

import atexit
from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path
from threading import Lock

_RESOURCE_STACK = ExitStack()
atexit.register(_RESOURCE_STACK.close)
_RESOURCE_ROOT = files("oep_permissions").joinpath("resources")
_RESOURCE_LOCK = Lock()
_RESOURCE_PATHS: dict[tuple[str, ...], Path] = {}


def _resource_path(*parts: str) -> Path:
    with _RESOURCE_LOCK:
        cached = _RESOURCE_PATHS.get(parts)
        if cached is None:
            cached = _RESOURCE_STACK.enter_context(as_file(_RESOURCE_ROOT.joinpath(*parts)))
            _RESOURCE_PATHS[parts] = cached
        return cached


SCHEMA_PATH = _resource_path("schema", "tool_permission_packet.v0.schema.json")
COUNTERFACTUAL_REPLAY_SCHEMA_PATH = _resource_path("schema", "counterfactual_replay.v0.schema.json")
EXAMPLE_PATH = _resource_path("examples", "code_review_tool_permission.v0.json")
DENIED_EXAMPLE_PATH = _resource_path("examples", "code_review_tool_permission_denied.v0.json")
POLICY_PATH = _resource_path("policy", "tool_permissions.rego")
COUNTERFACTUAL_COMPOUND_RELIABILITY_POLICY_PATH = _resource_path(
    "policy",
    "counterfactual",
    "compound_reliability_step_bound.rego",
)
COUNTERFACTUAL_BUDGET_PER_RUN_POLICY_PATH = _resource_path(
    "policy",
    "counterfactual",
    "budget_per_run_cap.rego",
)
COUNTERFACTUAL_APPROVAL_PER_STEP_POLICY_PATH = _resource_path(
    "policy",
    "counterfactual",
    "approval_per_step_escalation.rego",
)
POLICY_TEST_PATH = _resource_path("policy", "tool_permissions_test.rego")
INPUT_PATH = _resource_path("policy", "input", "code_review_read_diff.json")
DENIED_INPUT_PATH = _resource_path("policy", "input", "code_review_write_diff.json")
PACKAGE_ROOT = SCHEMA_PATH.parents[1]
EXPECTED_SCHEMA_TITLE = "Operational Evidence Plane Tool Permission Packet v0"
EXPECTED_COUNTERFACTUAL_REPLAY_SCHEMA_TITLE = "Operational Evidence Plane Counterfactual Replay v0"

__all__ = [
    "COUNTERFACTUAL_REPLAY_SCHEMA_PATH",
    "COUNTERFACTUAL_APPROVAL_PER_STEP_POLICY_PATH",
    "COUNTERFACTUAL_BUDGET_PER_RUN_POLICY_PATH",
    "COUNTERFACTUAL_COMPOUND_RELIABILITY_POLICY_PATH",
    "DENIED_EXAMPLE_PATH",
    "DENIED_INPUT_PATH",
    "EXAMPLE_PATH",
    "EXPECTED_COUNTERFACTUAL_REPLAY_SCHEMA_TITLE",
    "EXPECTED_SCHEMA_TITLE",
    "INPUT_PATH",
    "PACKAGE_ROOT",
    "POLICY_PATH",
    "POLICY_TEST_PATH",
    "SCHEMA_PATH",
]
