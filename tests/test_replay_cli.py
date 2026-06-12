"""CLI surface of `oep replay`, `oep diff`, `oep reserve`, and `oep project`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from helpers import (
    DECISION_ID,
    FIXED_REPLAY_TIMESTAMP,
    ROOT,
    _write_deny_policy,
)

import oep_verify.cli as cli_module
from oep_verify.cli import main as cli_main


def test_counterfactual_replay_cli_outputs_json_and_human(
    tmp_path: Path,
    state_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alt_policy_path = _write_deny_policy(tmp_path)

    cli_main(
        [
            "replay",
            DECISION_ID,
            "--state-path",
            str(state_path),
            "--counterfactual",
            "--policy-bundle",
            str(alt_policy_path),
            "--output-format",
            "json",
            "--replay-timestamp-utc",
            FIXED_REPLAY_TIMESTAMP,
        ]
    )
    json_output = json.loads(capsys.readouterr().out)
    assert json_output["replay_mode"] == "counterfactual"
    assert json_output["counterfactual"]["decision"] == "deny"
    assert json_output["replay_metadata"]["replay_timestamp_utc"] == FIXED_REPLAY_TIMESTAMP

    cli_main(
        [
            "replay",
            DECISION_ID,
            "--state-path",
            str(state_path),
            "--counterfactual",
            "--policy-bundle",
            str(alt_policy_path),
            "--output-format",
            "json",
            "--strip-exclusions",
        ]
    )
    stripped_output = json.loads(capsys.readouterr().out)
    assert stripped_output["replay_mode"] == "counterfactual"
    assert "replay_timestamp_utc" not in stripped_output["replay_metadata"]
    assert stripped_output["replay_metadata"]["determinism_exclusions"] == ["replay_metadata.replay_timestamp_utc"]

    cli_main(
        [
            "replay",
            DECISION_ID,
            "--state-path",
            str(state_path),
            "--counterfactual",
            "--policy-bundle",
            str(alt_policy_path),
            "--output-format",
            "jsonl",
        ]
    )
    jsonl_output = json.loads(capsys.readouterr().out)
    assert jsonl_output["replay_mode"] == "counterfactual"

    cli_main(
        [
            "replay",
            DECISION_ID,
            "--state-path",
            str(state_path),
            "--output-format",
            "human",
        ]
    )
    read_only_human_output = capsys.readouterr().out
    assert "trace_id:" in read_only_human_output
    assert "span_id:" in read_only_human_output
    assert "replay_handle:" in read_only_human_output

    monkeypatch.setenv("OEP_REPLAY_MODE", "counterfactual")
    cli_main(
        [
            "replay",
            DECISION_ID,
            "--state-path",
            str(state_path),
            "--policy-bundle",
            str(alt_policy_path),
        ]
    )
    human_output = capsys.readouterr().out
    assert "replay_mode: counterfactual" in human_output
    assert "counterfactual: deny" in human_output


def test_v03_cli_outputs_composed_replay_and_budget_commands(
    state_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli_main(
        [
            "replay",
            DECISION_ID,
            "--state-path",
            str(state_path),
            "--substitute",
            "prompt=code-review-agent-prompt@0.2.0,tool=code-review-tool-registry@0.2.0",
            "--substitute-budget",
            "per_run_cap_usd=0.005",
            "--substitute-model",
            "bedrock:anthropic.claude-opus-4-6",
            "--output-format",
            "human",
            "--replay-timestamp-utc",
            FIXED_REPLAY_TIMESTAMP,
            "--strip-exclusions",
        ]
    )
    replay_human = capsys.readouterr().out
    assert "replay_class: evaluative" in replay_human
    assert "counterfactual: deny" in replay_human

    cli_main(
        [
            "diff",
            DECISION_ID,
            DECISION_ID,
            "--state-path",
            str(state_path),
            "--surface",
            "model,policy",
            "--output-format",
            "human",
        ]
    )
    diff_human = capsys.readouterr().out
    assert "replay_class: deterministic" in diff_human
    assert "changed_surfaces: []" in diff_human

    cli_main(
        [
            "reserve",
            "--budget-cap-usd",
            "10",
            "--reservation",
            "bres_0001:6:4",
            "--reservation",
            "bres_0002:8:7",
            "--output-format",
            "human",
        ]
    )
    reserve_output = json.loads(capsys.readouterr().out)
    assert reserve_output["first_denied_reservation_id"] == "bres_0002"

    cli_main(
        [
            "project",
            "--projected-cost-window",
            "4:9",
            "--budget-cap-usd",
            "10",
            "--approve",
            "--output-format",
            "json",
        ]
    )
    projection = json.loads(capsys.readouterr().out)
    assert projection["replay_class"] == "evaluative"
    assert projection["approval_outcome"] == "approved"


def test_v03_cli_rejects_invalid_inputs(state_path: Path) -> None:
    with pytest.raises(SystemExit, match="--field is only supported"):
        cli_main(
            [
                "replay",
                DECISION_ID,
                "--state-path",
                str(state_path),
                "--field",
                "decision_id",
                "--substitute-budget",
                "per_run_cap_usd=1",
            ]
        )

    with pytest.raises(SystemExit, match="--field is only supported"):
        cli_main(
            [
                "replay",
                DECISION_ID,
                "--state-path",
                str(state_path),
                "--field",
                "decision_id",
                "--counterfactual",
                "--policy-bundle",
                str(ROOT / "permissions" / "policy" / "tool_permissions.rego"),
            ]
        )

    with pytest.raises(SystemExit, match="no recorded decision"):
        cli_main(["replay", "pder_missing", "--state-path", str(state_path)])

    with pytest.raises(SystemExit, match="no recorded decision"):
        cli_main(["diff", DECISION_ID, "pder_missing", "--state-path", str(state_path)])

    with pytest.raises(SystemExit, match="budget_cap_usd"):
        cli_main(["reserve", "--budget-cap-usd", "-1", "--reservation", "bres_0001:1:1"])

    with pytest.raises(SystemExit, match="must not exceed"):
        cli_main(["project", "--projected-cost-window", "2:1", "--budget-cap-usd", "3"])

    with pytest.raises(SystemExit, match="key=value"):
        cli_main(["replay", DECISION_ID, "--state-path", str(state_path), "--substitute", "bad"])

    with pytest.raises(SystemExit, match="id:estimated_usd:committed_usd"):
        cli_main(["reserve", "--budget-cap-usd", "1", "--reservation", "bad"])

    with pytest.raises(SystemExit, match="must be numeric"):
        cli_main(["reserve", "--budget-cap-usd", "1", "--reservation", "bres:a:1"])

    with pytest.raises(SystemExit, match="min_usd:max_usd"):
        cli_main(["project", "--projected-cost-window", "bad", "--budget-cap-usd", "1"])

    with pytest.raises(SystemExit, match="values must be numeric"):
        cli_main(["project", "--projected-cost-window", "a:b", "--budget-cap-usd", "1"])


def test_cli_helper_defensive_branches() -> None:
    assert cli_module._parse_substitution_args(None) == {}
    assert cli_module._parse_substitution_args([",prompt=next"]) == {"prompt": "next"}
    assert cli_module._strip_determinism_exclusions(cast(Any, [])) == []
    assert cli_module._strip_determinism_exclusions({"replay_metadata": {"determinism_exclusions": "bad"}}) == {
        "replay_metadata": {"determinism_exclusions": "bad"}
    }
    nested = {
        "replay_metadata": {"determinism_exclusions": ["bad..path", "missing.child", "parent.child"]},
        "parent": "not-an-object",
    }
    assert cli_module._strip_determinism_exclusions(nested)["parent"] == "not-an-object"
    with pytest.raises(SystemExit, match="unknown output format"):
        cli_module._print_record({}, "yaml")


def test_counterfactual_replay_cli_rejects_invalid_mode_and_missing_bundle(
    state_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(SystemExit, match="--policy-bundle is required"):
        cli_main(["replay", DECISION_ID, "--state-path", str(state_path), "--counterfactual"])

    with pytest.raises(SystemExit, match="--policy-bundle requires counterfactual"):
        cli_main(
            [
                "replay",
                DECISION_ID,
                "--state-path",
                str(state_path),
                "--policy-bundle",
                str(ROOT / "permissions" / "policy" / "tool_permissions.rego"),
            ]
        )

    with pytest.raises(SystemExit, match="--replay-timestamp-utc requires counterfactual"):
        cli_main(
            [
                "replay",
                DECISION_ID,
                "--state-path",
                str(state_path),
                "--replay-timestamp-utc",
                FIXED_REPLAY_TIMESTAMP,
            ]
        )

    with pytest.raises(SystemExit, match="--strip-exclusions requires counterfactual"):
        cli_main(["replay", DECISION_ID, "--state-path", str(state_path), "--strip-exclusions"])

    monkeypatch.setenv("OEP_REPLAY_MODE", "invalid")
    with pytest.raises(SystemExit, match="OEP_REPLAY_MODE must be"):
        cli_main(["replay", DECISION_ID, "--state-path", str(state_path)])
