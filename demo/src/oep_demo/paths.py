"""Filesystem helpers for the deterministic demo package."""

import atexit
import os
from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path
from threading import Lock

from oep_events.paths import EXAMPLE_PATH as EVENT_PATH
from oep_manifest.paths import EXAMPLE_PATH as MANIFEST_PATH
from oep_permissions.paths import EXAMPLE_PATH as PERMISSION_PATH
from oep_traces.paths import EVAL_EXAMPLE_PATH as EVAL_PATH
from oep_traces.paths import TRACE_EXAMPLE_PATH as TRACE_PATH

_RESOURCE_STACK = ExitStack()
atexit.register(_RESOURCE_STACK.close)
_RESOURCE_ROOT = files("oep_demo").joinpath("resources")
_RESOURCE_LOCK = Lock()
_RESOURCE_PATHS: dict[tuple[str, ...], Path] = {}


def _resource_path(*parts: str) -> Path:
    with _RESOURCE_LOCK:
        cached = _RESOURCE_PATHS.get(parts)
        if cached is None:
            cached = _RESOURCE_STACK.enter_context(as_file(_RESOURCE_ROOT.joinpath(*parts)))
            _RESOURCE_PATHS[parts] = cached
        return cached


REPO_ROOT = Path.cwd()
DEMO_ROOT = REPO_ROOT / "demo"
STATE_ENV_VAR = "OEP_DEMO_STATE_PATH"
FIXTURE_PATH = _resource_path("fixtures", "diff_synthetic_001.patch")
MODEL_CONTRACT_PATH = _resource_path("model", "deterministic_mock_reviewer.md")
PROMPT_CONTRACT_PATH = _resource_path("prompts", "code_review_agent.md")
REPLAY_STATE_RECIPE_PATH = _resource_path("state", "replay_state_recipe.md")
DEFAULT_STATE_PATH = DEMO_ROOT / "state" / "code_review_agent.sqlite"
_STATE_PATH_ENV = os.environ.get(STATE_ENV_VAR)
if _STATE_PATH_ENV:
    _state_path = Path(_STATE_PATH_ENV).expanduser()
    STATE_PATH = _state_path if _state_path.is_absolute() else REPO_ROOT / _state_path
else:
    STATE_PATH = DEFAULT_STATE_PATH

__all__ = [
    "DEFAULT_STATE_PATH",
    "DEMO_ROOT",
    "EVAL_PATH",
    "EVENT_PATH",
    "FIXTURE_PATH",
    "MANIFEST_PATH",
    "MODEL_CONTRACT_PATH",
    "PERMISSION_PATH",
    "PROMPT_CONTRACT_PATH",
    "REPO_ROOT",
    "REPLAY_STATE_RECIPE_PATH",
    "STATE_ENV_VAR",
    "STATE_PATH",
    "TRACE_PATH",
]
