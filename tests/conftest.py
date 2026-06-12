"""Shared fixtures for the test suite."""

from __future__ import annotations

from pathlib import Path

import pytest
from oep_demo import run_demo


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    """Fresh deterministic demo replay state under the per-test tmp dir."""
    path = tmp_path / "code_review_agent.sqlite"
    run_demo(path)
    return path
