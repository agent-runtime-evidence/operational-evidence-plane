"""OPA subprocess lifecycle and OEP_OPA_COMMAND_WRAPPER validation."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import oep_demo.counterfactual as counterfactual_module
import oep_permissions.replay as replay_module
import pytest
from helpers import (
    DECISION_ID,
    FIXED_REPLAY_TIMESTAMP,
    ROOT,
    _FakeOpaProcess,
)
from oep_permissions import (
    ReplayError,
    counterfactual_replay_decision,
)


def test_counterfactual_replay_reports_opa_timeout_and_stdout_failure(
    state_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path = ROOT / "permissions" / "policy" / "tool_permissions.rego"

    terminated_processes: list[_FakeOpaProcess] = []

    def timeout_popen(args: list[str], **kwargs: Any) -> _FakeOpaProcess:
        assert args[1] == "eval"
        assert kwargs["encoding"] == "utf-8"
        return _FakeOpaProcess(
            args,
            timeout=True,
            expected_timeout=replay_module.OPA_EVAL_TIMEOUT_SECONDS,
        )

    def terminate(process: _FakeOpaProcess) -> None:
        terminated_processes.append(process)
        process.kill()

    monkeypatch.setattr("oep_permissions.replay.subprocess.Popen", timeout_popen)
    monkeypatch.setattr("oep_permissions.replay.opa._terminate_opa_process", terminate)
    with pytest.raises(ReplayError, match="timed out after 30 seconds"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )
    assert len(terminated_processes) == 1
    assert terminated_processes[0].killed is True
    assert terminated_processes[0].waited is True

    unexpected_processes: list[_FakeOpaProcess] = []

    def unexpected_popen(args: list[str], **kwargs: Any) -> _FakeOpaProcess:
        return _FakeOpaProcess(
            args,
            unexpected_exception=RuntimeError("unexpected communicate failure"),
            expected_timeout=replay_module.OPA_EVAL_TIMEOUT_SECONDS,
        )

    def terminate_unexpected(process: _FakeOpaProcess) -> None:
        unexpected_processes.append(process)
        process.kill()

    monkeypatch.setattr("oep_permissions.replay.subprocess.Popen", unexpected_popen)
    monkeypatch.setattr("oep_permissions.replay.opa._terminate_opa_process", terminate_unexpected)
    with pytest.raises(RuntimeError, match="unexpected communicate failure"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )
    assert len(unexpected_processes) == 1
    assert unexpected_processes[0].killed is True
    assert unexpected_processes[0].waited is True

    def failing_popen(args: list[str], **kwargs: Any) -> _FakeOpaProcess:
        assert args[1] == "eval"
        assert kwargs["encoding"] == "utf-8"
        return _FakeOpaProcess(
            args,
            returncode=1,
            stdout="stdout failure",
            expected_timeout=replay_module.OPA_EVAL_TIMEOUT_SECONDS,
        )

    monkeypatch.setattr("oep_permissions.replay.subprocess.Popen", failing_popen)
    with pytest.raises(ReplayError, match="stdout failure"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )

    long_error = ("x" * replay_module.OPA_ERROR_OUTPUT_LIMIT) + "UNTRUNCATED_SUFFIX"

    def verbose_failing_popen(args: list[str], **kwargs: Any) -> _FakeOpaProcess:
        return _FakeOpaProcess(
            args,
            returncode=1,
            stderr=long_error,
            expected_timeout=replay_module.OPA_EVAL_TIMEOUT_SECONDS,
        )

    monkeypatch.setattr("oep_permissions.replay.subprocess.Popen", verbose_failing_popen)
    with pytest.raises(ReplayError) as exc_info:
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )
    assert "[output truncated]" in str(exc_info.value)
    assert "UNTRUNCATED_SUFFIX" not in str(exc_info.value)


def test_opa_eval_rejects_oversized_stdin_before_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_opa_eval = cast(
        Callable[[list[str], str, float | None], subprocess.CompletedProcess[str]],
        vars(replay_module)["_run_opa_eval"],
    )

    def fail_popen(*args: Any, **kwargs: Any) -> _FakeOpaProcess:
        raise AssertionError("OPA subprocess must not start for oversized stdin")

    monkeypatch.setattr("oep_permissions.replay.opa.OPA_STDIN_INPUT_LIMIT_BYTES", 4)
    monkeypatch.setattr("oep_permissions.replay.subprocess.Popen", fail_popen)

    with pytest.raises(replay_module.OpaEvaluationError, match="input exceeds 4 bytes"):
        run_opa_eval(["opa", "eval"], "12345", 1.0)


def test_counterfactual_replay_rejects_invalid_replay_timestamp_before_opa(
    state_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path = ROOT / "permissions" / "policy" / "tool_permissions.rego"

    def fail_popen(*args: Any, **kwargs: Any) -> _FakeOpaProcess:
        raise AssertionError("OPA subprocess must not start for an invalid replay timestamp")

    monkeypatch.setattr("oep_permissions.replay.subprocess.Popen", fail_popen)

    with pytest.raises(ReplayError, match="replay_timestamp_utc must be a valid date-time"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc="garbage",
        )


def test_counterfactual_replay_uses_configured_opa_timeout(
    state_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path = ROOT / "permissions" / "policy" / "tool_permissions.rego"

    def timeout_popen(args: list[str], **kwargs: Any) -> _FakeOpaProcess:
        assert args[1] == "eval"
        return _FakeOpaProcess(args, timeout=True, expected_timeout=0.25)

    monkeypatch.setenv(replay_module.OEP_OPA_EVAL_TIMEOUT_SECONDS_ENV, "10")
    monkeypatch.setattr("oep_permissions.replay.subprocess.Popen", timeout_popen)
    monkeypatch.setattr(
        "oep_permissions.replay.opa._terminate_opa_process",
        lambda process: process.kill(),
    )
    with pytest.raises(ReplayError, match="timed out after 0.25 seconds"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
            timeout_seconds=0.25,
        )

    monkeypatch.setenv(replay_module.OEP_OPA_EVAL_TIMEOUT_SECONDS_ENV, "0.25")
    with pytest.raises(ReplayError, match="timed out after 0.25 seconds"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )

    with pytest.raises(ReplayError, match="timeout_seconds must be a number of seconds greater than or equal to 0.001"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
            timeout_seconds=0,
        )

    with pytest.raises(ReplayError, match="timeout_seconds must be a number of seconds greater than or equal to 0.001"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
            timeout_seconds=0.000_000_001,
        )

    monkeypatch.setenv(replay_module.OEP_OPA_EVAL_TIMEOUT_SECONDS_ENV, "0")
    with pytest.raises(ReplayError, match="must be a number of seconds greater than or equal to 0.001"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )

    monkeypatch.setenv(replay_module.OEP_OPA_EVAL_TIMEOUT_SECONDS_ENV, "0.000000001")
    with pytest.raises(ReplayError, match="must be a number of seconds greater than or equal to 0.001"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )

    monkeypatch.setenv(replay_module.OEP_OPA_EVAL_TIMEOUT_SECONDS_ENV, "not-a-number")
    with pytest.raises(ReplayError, match="must be a number of seconds greater than or equal to 0.001"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )


def test_counterfactual_replay_allows_opa_command_wrapper(
    state_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path = ROOT / "permissions" / "policy" / "tool_permissions.rego"

    def wrapped_popen(args: list[str], **kwargs: Any) -> _FakeOpaProcess:
        assert args[0:2] == ["/usr/bin/prlimit", "--as=100000000"]
        assert Path(args[2]).name == "opa"
        assert args[3] == "eval"
        return _FakeOpaProcess(
            args,
            stdout=json.dumps(
                {
                    "result": [
                        {
                            "expressions": [
                                {
                                    "value": {
                                        "00000000": {
                                            "allow": True,
                                            "matched_rule": "allow_reference_code_review_diff_read",
                                            "policy_id": "opa-tool-permission-policy",
                                            "policy_version": "0.1.0",
                                            "reason": (
                                                "reference code review agent may inspect an immutable synthetic diff"
                                            ),
                                        }
                                    }
                                }
                            ]
                        }
                    ]
                }
            ),
        )

    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "prlimit --as=100000000")
    monkeypatch.setattr("oep_permissions.replay.shutil.which", lambda executable, path=None: f"/usr/bin/{executable}")
    monkeypatch.setattr("oep_verify.verify_support.require_executable", lambda name, purpose: f"/usr/bin/{name}")
    monkeypatch.setattr("oep_permissions.replay.subprocess.Popen", wrapped_popen)

    result = counterfactual_replay_decision(
        state_path,
        DECISION_ID,
        policy_path,
        replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
    )

    assert result.counterfactual["decision"] == "allow"


def test_counterfactual_replay_rejects_invalid_opa_command_wrapper(
    state_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path = ROOT / "permissions" / "policy" / "tool_permissions.rego"

    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, '"unterminated')

    with pytest.raises(ReplayError, match="OEP_OPA_COMMAND_WRAPPER could not be parsed"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )


def test_counterfactual_replay_rejects_unauthorized_opa_command_wrapper(
    state_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path = ROOT / "permissions" / "policy" / "tool_permissions.rego"

    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "python -c pass")

    with pytest.raises(ReplayError, match="unauthorized OEP_OPA_COMMAND_WRAPPER executable"):
        counterfactual_replay_decision(
            state_path,
            DECISION_ID,
            policy_path,
            replay_timestamp_utc=FIXED_REPLAY_TIMESTAMP,
        )


def test_opa_command_wrapper_rejects_positional_binary_arguments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opa_command = cast(
        Callable[[list[str]], list[str]],
        vars(replay_module)["_opa_command"],
    )
    monkeypatch.setattr("oep_permissions.replay.shutil.which", lambda executable, path=None: f"/usr/bin/{executable}")

    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "nice -n 5")
    assert opa_command(["opa", "eval"]) == ["/usr/bin/nice", "-n", "5", "opa", "eval"]

    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "nice /tmp/arbitrary_binary")
    with pytest.raises(ReplayError, match="unauthorized OEP_OPA_COMMAND_WRAPPER argument"):
        opa_command(["opa", "eval"])

    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "sudo -s")
    with pytest.raises(ReplayError, match="unauthorized OEP_OPA_COMMAND_WRAPPER argument"):
        opa_command(["opa", "eval"])

    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "docker run --rm --init --network none opa:1.7.1")
    assert opa_command(["opa", "eval"]) == [
        "/usr/bin/docker",
        "run",
        "--rm",
        "--init",
        "--network",
        "none",
        "opa:1.7.1",
        "opa",
        "eval",
    ]

    volume_source = tmp_path / "policy"
    monkeypatch.setenv(
        replay_module.OEP_OPA_COMMAND_WRAPPER_ENV,
        f"docker run --rm --read-only --init -v {volume_source}:/policy:ro opa:1.7.1",
    )
    assert opa_command(["opa", "eval"]) == [
        "/usr/bin/docker",
        "run",
        "--rm",
        "--read-only",
        "--init",
        "-v",
        f"{volume_source}:/policy:ro",
        "opa:1.7.1",
        "opa",
        "eval",
    ]

    monkeypatch.setenv(
        replay_module.OEP_OPA_COMMAND_WRAPPER_ENV,
        "docker run --rm --network none opa:1.7.1",
    )
    with pytest.raises(ReplayError, match="docker wrappers must include --init"):
        opa_command(["opa", "eval"])

    monkeypatch.setenv(
        replay_module.OEP_OPA_COMMAND_WRAPPER_ENV,
        f"docker run --rm -v {volume_source}:/policy:rw opa:1.7.1",
    )
    with pytest.raises(ReplayError, match="unauthorized OEP_OPA_COMMAND_WRAPPER argument"):
        opa_command(["opa", "eval"])

    monkeypatch.setenv(
        replay_module.OEP_OPA_COMMAND_WRAPPER_ENV,
        "docker run --rm -v relative-source:/policy:ro opa:1.7.1",
    )
    with pytest.raises(ReplayError, match="unauthorized OEP_OPA_COMMAND_WRAPPER argument"):
        opa_command(["opa", "eval"])

    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "docker run --entrypoint sh opa:1.7.1")
    with pytest.raises(ReplayError, match="unauthorized OEP_OPA_COMMAND_WRAPPER argument"):
        opa_command(["opa", "eval"])

    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "nice -n 5")
    monkeypatch.setattr("oep_permissions.replay.shutil.which", lambda executable, path=None: f"/tmp/{executable}")
    with pytest.raises(ReplayError, match="resolved to untrusted path"):
        opa_command(["opa", "eval"])


def test_opa_policy_bundle_data_path_uses_docker_volume_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_path = cast(
        Callable[[Path], str],
        vars(replay_module)["_opa_policy_bundle_data_path"],
    )
    policy_dir = tmp_path / "policy"
    policy_path = policy_dir / "counterfactual" / "policy.rego"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text("package oep.permissions\n", encoding="utf-8")

    monkeypatch.setenv(
        replay_module.OEP_OPA_COMMAND_WRAPPER_ENV,
        f"docker run --rm --init --volume={policy_dir}:/policy:ro opa:1.7.1",
    )

    assert data_path(policy_path) == "/policy/counterfactual/policy.rego"


def test_opa_command_wrapper_ignores_relative_path_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opa_command = cast(
        Callable[[list[str]], list[str]],
        vars(replay_module)["_opa_command"],
    )
    captured_search_path: str | None = None
    absolute_tmp_entry = tmp_path / "bin"

    def fake_which(executable: str, path: str | None = None) -> str:
        nonlocal captured_search_path
        captured_search_path = path
        return f"/usr/bin/{executable}"

    monkeypatch.setenv(
        "PATH",
        os.pathsep.join(("", ".", "relative-bin", str(absolute_tmp_entry), "/usr/bin")),
    )
    monkeypatch.setattr("oep_permissions.replay.shutil.which", fake_which)
    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "nice -n 5")

    assert opa_command(["opa", "eval"]) == ["/usr/bin/nice", "-n", "5", "opa", "eval"]
    assert captured_search_path == os.pathsep.join((str(absolute_tmp_entry), "/usr/bin"))


def test_opa_command_wrapper_validates_windows_trusted_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opa_command = cast(
        Callable[[list[str]], list[str]],
        vars(replay_module)["_opa_command"],
    )

    monkeypatch.setattr("oep_permissions.replay.os.name", "nt")
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    monkeypatch.setenv("ProgramFiles", r"C:\Program Files")
    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "nice -n 5")

    def trusted_which(executable: str, path: str | None = None) -> str:
        del path
        return rf"C:\Windows\System32\{executable}.exe"

    monkeypatch.setattr("oep_permissions.replay.shutil.which", trusted_which)
    assert opa_command(["opa", "eval"]) == [r"C:\Windows\System32\nice.exe", "-n", "5", "opa", "eval"]

    def untrusted_which(executable: str, path: str | None = None) -> str:
        del path
        return rf"C:\Users\mic\bin\{executable}.exe"

    monkeypatch.setattr("oep_permissions.replay.shutil.which", untrusted_which)
    with pytest.raises(ReplayError, match="resolved to untrusted path"):
        opa_command(["opa", "eval"])


def test_opa_command_wrapper_rejects_windows_junction_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opa_command = cast(
        Callable[[list[str]], list[str]],
        vars(replay_module)["_opa_command"],
    )

    monkeypatch.setattr("oep_permissions.replay.os.name", "nt")
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    monkeypatch.setenv("ProgramFiles", r"C:\Program Files")
    monkeypatch.setenv(replay_module.OEP_OPA_COMMAND_WRAPPER_ENV, "nice -n 5")
    monkeypatch.setattr(
        "oep_permissions.replay.shutil.which",
        lambda executable, path=None: rf"C:\Program Files\OEP\{executable}.exe",
    )
    monkeypatch.setattr(
        "oep_permissions.replay.wrapper._resolve_windows_filesystem_path",
        lambda resolved: resolved.replace(r"C:\Program Files\OEP", r"D:\Untrusted"),
    )

    with pytest.raises(ReplayError, match="resolved to untrusted path"):
        opa_command(["opa", "eval"])


def test_stable_artifact_ref_falls_back_to_absolute_path_across_drives(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path = tmp_path / "state.sqlite"
    output_dir = tmp_path / "out"

    def cross_drive_relpath(path: Path, start: Path) -> str:
        del path, start
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    monkeypatch.setattr(counterfactual_module.os.path, "relpath", cross_drive_relpath)

    assert counterfactual_module._stable_artifact_ref(artifact_path, output_dir) == artifact_path.resolve().as_posix()


def test_opa_eval_uses_windows_process_group_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_opa_eval = cast(
        Callable[[list[str], str, float | None], subprocess.CompletedProcess[str]],
        vars(replay_module)["_run_opa_eval"],
    )
    popen_kwargs: dict[str, Any] = {}

    def popen(args: list[str], **kwargs: Any) -> _FakeOpaProcess:
        popen_kwargs.update(kwargs)
        return _FakeOpaProcess(args, stdout="{}")

    monkeypatch.setattr("oep_permissions.replay.os.name", "nt")
    monkeypatch.setattr(replay_module.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False)
    monkeypatch.setattr("oep_permissions.replay.subprocess.Popen", popen)

    result = run_opa_eval(["opa", "eval"], "{}", 1.0)

    assert result.returncode == 0
    assert popen_kwargs["creationflags"] == 512


def test_opa_termination_uses_windows_ctrl_break(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terminate_opa_process = cast(
        Callable[[_FakeOpaProcess], None],
        vars(replay_module)["_terminate_opa_process"],
    )
    kill_calls: list[tuple[int, int]] = []

    def kill(pid: int, signal_value: int) -> None:
        kill_calls.append((pid, signal_value))

    monkeypatch.setattr("oep_permissions.replay.os.name", "nt")
    monkeypatch.setattr(replay_module.signal, "CTRL_BREAK_EVENT", 21, raising=False)
    monkeypatch.setattr("oep_permissions.replay.os.kill", kill)
    process = _FakeOpaProcess(["wrapper"])

    terminate_opa_process(process)

    assert kill_calls == [(process.pid, 21)]
    assert process.killed is False


def test_opa_termination_falls_back_to_direct_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terminate_opa_process = cast(
        Callable[[_FakeOpaProcess], None],
        vars(replay_module)["_terminate_opa_process"],
    )

    def killpg(pid: int, signal_value: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr("oep_permissions.replay.os.name", "posix")
    monkeypatch.setattr("oep_permissions.replay.os.killpg", killpg)
    process = _FakeOpaProcess(["wrapper"])

    terminate_opa_process(process)

    assert process.killed is True
