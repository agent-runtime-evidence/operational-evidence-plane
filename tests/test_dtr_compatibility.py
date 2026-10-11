"""Versioned DTR expectations preserve historical and current semantics."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / "integrations/decision-trace-reconstructor/scripts/check_dtr_compatibility.py"))


def test_legacy_and_current_expectations_are_distinct() -> None:
    old = MODULE["expected_path"]("0.1.0", "code_review_agent")
    new = MODULE["expected_path"]("0.2.0", "code_review_agent")
    before, after = json.loads(old.read_text()), json.loads(new.read_text())
    assert old != new
    assert before["dominant_break"] == "decision_diffusion"
    assert after["dominant_break"] is None
    assert before["per_property"] == after["per_property"]
    assert after["evidence_contract"] == "fragment-coverage-v2"
    assert len(after["actor_inventory"]["record_producers"]) == 5
    assert after["actor_inventory"]["declared_agents"] == []
    assert len(after["actor_inventory"]["action_issuers"]) == 1


@pytest.mark.parametrize("version,scenario", [("0.9.0", "code_review_agent"), ("0.2.0", "../code_review_agent")])
def test_unreviewed_version_or_scenario_is_refused(version: str, scenario: str) -> None:
    with pytest.raises(ValueError):
        MODULE["expected_path"](version, scenario)
