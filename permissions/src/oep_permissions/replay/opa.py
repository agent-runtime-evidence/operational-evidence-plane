"""Deterministic OPA subprocess evaluation for counterfactual replay."""

from __future__ import annotations

import json
import math
import os
import signal
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from oep_permissions.replay.records import (
    OpaEvaluationError,
    ReplayRecord,
    _require_object,
    _require_string,
)
from oep_permissions.replay.wrapper import (
    _opa_command,
    _opa_policy_bundle_data_path,
)

OPA_EVAL_TIMEOUT_SECONDS = 30


MIN_OPA_EVAL_TIMEOUT_SECONDS = 0.001


OPA_STDIN_INPUT_LIMIT_BYTES = 8 * 1024 * 1024


OEP_OPA_EVAL_TIMEOUT_SECONDS_ENV = "OEP_OPA_EVAL_TIMEOUT_SECONDS"


OPA_DECISION_QUERY_PATH = "data.oep.permissions.decision"


OPA_BATCH_DECISION_QUERY = (
    '{sprintf("%08d", [i]): decision | '
    "some i; "
    "policy_input := input[i]; "
    "decision := data.oep.permissions.decision with input as policy_input"
    "}"
)


OPA_ERROR_OUTPUT_LIMIT = 1000


def _policy_input_from_record(record: ReplayRecord) -> dict[str, Any]:
    permission = record.permission_packet
    event = record.agent_step_event
    requested_action = _require_object(permission.get("requested_action"), "requested_action")
    input_context = {
        "release_manifest_id": record.release_manifest_id,
        "event_id": _require_string(permission.get("event_id"), "event_id"),
        "tool_call_id": record.tool_call_id,
        "trace_id": record.trace_id,
        "span_id": record.span_id,
        "actor": _require_object(permission.get("actor"), "actor"),
        "action": requested_action,
        "tool": _require_object(permission.get("tool"), "tool"),
        "resource": _require_object(permission.get("resource"), "resource"),
        "scoped_credential_lifetime": record.scoped_credential_lifetime,
        "approval_capture": record.approval_capture,
        "policy_bundle_version": record.policy_bundle_version,
        "release_manifest_version": record.release_manifest_version,
        "model_alias": record.model_alias,
        "resolved_model_version": record.resolved_model_version,
        "model_provider": record.model_provider,
        "replay_handle": record.replay_handle,
        "nd_builtin_cache": record.nd_builtin_cache or {},
    }
    checkpoint = event.get("checkpoint")
    if isinstance(checkpoint, dict):
        input_context["checkpoint"] = checkpoint
    budget = event.get("budget")
    if isinstance(budget, dict):
        input_context["budget"] = budget
    if record.decision_metadata is not None:
        input_context["decision_id"] = record.decision_metadata
        cost = record.decision_metadata.get("cost")
        if isinstance(cost, dict):
            input_context["cost"] = cost
    return input_context


def _evaluate_opa_decisions(
    policy_bundle_path: Path,
    policy_inputs: Sequence[dict[str, Any]],
    query: str,
    timeout_seconds: float | None,
) -> list[dict[str, Any]]:
    from oep_verify.verify_support import require_executable

    try:
        opa = require_executable("opa", "counterfactual policy replay")
    except (FileNotFoundError, ValueError) as exc:
        raise OpaEvaluationError(str(exc)) from exc

    if query != OPA_DECISION_QUERY_PATH:
        raise OpaEvaluationError(
            f"unsupported OPA query path: {query!r}. "
            f"Counterfactual policy bundles must expose {OPA_DECISION_QUERY_PATH!r}."
        )

    result = _run_opa_eval(
        [
            opa,
            "eval",
            "--format",
            "json",
            "--data",
            _opa_policy_bundle_data_path(policy_bundle_path),
            "--stdin-input",
            OPA_BATCH_DECISION_QUERY,
        ],
        json.dumps(policy_inputs, sort_keys=True, separators=(",", ":")),
        timeout_seconds,
    )
    if result.returncode != 0:
        error_output = _bounded_opa_error_output(result)
        raise OpaEvaluationError(f"counterfactual OPA evaluation failed: {error_output}")

    try:
        payload = json.loads(result.stdout)
        batch_value = payload["result"][0]["expressions"][0]["value"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise OpaEvaluationError("counterfactual OPA evaluation did not return a decision object") from exc

    if not isinstance(batch_value, dict):
        raise OpaEvaluationError("counterfactual OPA evaluation must return an indexed decision object")
    decisions: list[dict[str, Any]] = []
    for index in range(len(policy_inputs)):
        value = batch_value.get(f"{index:08d}")
        if value is None:
            raise OpaEvaluationError(
                f"counterfactual OPA evaluation did not return a decision object for input {index + 1}. "
                f"The query rule {OPA_DECISION_QUERY_PATH!r} may be undefined or evaluated to empty under "
                "the substituted policy bundle."
            )
        if not isinstance(value, dict):
            raise OpaEvaluationError(
                f"counterfactual OPA evaluation returned invalid decision type for input {index + 1}: "
                "expected object"
            )
        decisions.append(value)
    return decisions


def _run_opa_eval(
    args: Sequence[str],
    stdin: str,
    timeout_seconds: float | None,
) -> subprocess.CompletedProcess[str]:
    timeout = _opa_eval_timeout_seconds(timeout_seconds)
    _require_opa_stdin_within_limit(stdin)
    command = _opa_command(args)
    popen_kwargs: dict[str, Any] = {}
    if os.name == "posix":
        # Wrappers must keep OPA in this process group or forward termination
        # signals; containerized adaptations should use an init/signal-forwarder.
        popen_kwargs["start_new_session"] = True
    elif os.name == "nt":
        creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if creation_flags:
            popen_kwargs["creationflags"] = creation_flags
    try:
        process: subprocess.Popen[str] = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            text=True,
            **popen_kwargs,
        )
        try:
            stdout, stderr = process.communicate(stdin, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _terminate_opa_process(process)
            _reap_opa_process(process)
            raise OpaEvaluationError(
                f"counterfactual OPA evaluation timed out after {_format_timeout_seconds(timeout)} seconds"
            ) from exc
        except BaseException:
            _terminate_opa_process(process)
            _reap_opa_process(process)
            raise
        return subprocess.CompletedProcess(
            command,
            process.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    except OSError as exc:
        raise OpaEvaluationError(f"counterfactual OPA evaluation failed to start: {exc}") from exc


def _require_opa_stdin_within_limit(stdin: str) -> None:
    payload_size = len(stdin.encode("utf-8"))
    if payload_size > OPA_STDIN_INPUT_LIMIT_BYTES:
        raise OpaEvaluationError(
            "counterfactual OPA evaluation input exceeds "
            f"{OPA_STDIN_INPUT_LIMIT_BYTES} bytes; split the replay into smaller batches"
        )


def _terminate_opa_process(process: subprocess.Popen[str]) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return
        except ProcessLookupError:
            pass
        except OSError:
            pass
    if os.name == "nt":
        ctrl_break_event = getattr(signal, "CTRL_BREAK_EVENT", None)
        if ctrl_break_event is not None:
            try:
                os.kill(process.pid, ctrl_break_event)
                return
            except ProcessLookupError:
                pass
            except OSError:
                pass
    _kill_opa_process(process)


def _kill_opa_process(process: subprocess.Popen[str]) -> None:
    try:
        process.kill()
    except OSError:
        return


def _reap_opa_process(process: subprocess.Popen[str]) -> None:
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        _kill_opa_process(process)
        process.wait()
    except OSError:
        return


def _bounded_opa_error_output(result: subprocess.CompletedProcess[str]) -> str:
    error_output = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
    if len(error_output) <= OPA_ERROR_OUTPUT_LIMIT:
        return error_output
    return f"{error_output[:OPA_ERROR_OUTPUT_LIMIT]} ... [output truncated]"


def _opa_eval_timeout_seconds(timeout_seconds: float | None) -> float:
    if timeout_seconds is not None:
        return _require_positive_timeout_seconds(timeout_seconds, "timeout_seconds")

    raw_timeout = os.environ.get(OEP_OPA_EVAL_TIMEOUT_SECONDS_ENV)
    if raw_timeout is None or raw_timeout == "":
        return float(OPA_EVAL_TIMEOUT_SECONDS)
    try:
        timeout = float(raw_timeout)
    except ValueError as exc:
        raise OpaEvaluationError(_timeout_validation_message(OEP_OPA_EVAL_TIMEOUT_SECONDS_ENV)) from exc
    return _require_positive_timeout_seconds(timeout, OEP_OPA_EVAL_TIMEOUT_SECONDS_ENV)


def _require_positive_timeout_seconds(timeout: float, field: str) -> float:
    if not math.isfinite(timeout) or timeout < MIN_OPA_EVAL_TIMEOUT_SECONDS:
        raise OpaEvaluationError(_timeout_validation_message(field))
    return timeout


def _timeout_validation_message(field: str) -> str:
    return f"{field} must be a number of seconds greater than or equal to {MIN_OPA_EVAL_TIMEOUT_SECONDS}"


def _format_timeout_seconds(timeout: float) -> str:
    return str(int(timeout)) if timeout.is_integer() else str(timeout)
