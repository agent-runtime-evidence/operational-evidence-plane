"""Validation and resolution of the OEP_OPA_COMMAND_WRAPPER allow-list."""

from __future__ import annotations

import ntpath
import os
import re
import shlex
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Never

from oep_permissions.replay.records import (
    OpaEvaluationError,
)

OEP_OPA_COMMAND_WRAPPER_ENV = "OEP_OPA_COMMAND_WRAPPER"


OPA_WRAPPER_NUMERIC_VALUE_RE = re.compile(r"^(?:[+-]?\d+(?:\.\d+)?|\d+:\d+|unlimited)$")


OPA_WRAPPER_USER_VALUE_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


OPA_DOCKER_IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*(?::[A-Za-z0-9._-]+)?$")


OPA_DOCKER_MEMORY_VALUE_RE = re.compile(r"^\d+[kKmMgG]?$")


TRUSTED_OPA_WRAPPER_DIRS = tuple(
    Path(path)
    for path in (
        "/bin",
        "/sbin",
        "/usr/bin",
        "/usr/sbin",
        "/usr/local/bin",
        "/opt/homebrew/bin",
    )
)


WINDOWS_SYSTEM_ROOT_ENV_NAMES = ("SystemRoot", "WINDIR")


WINDOWS_TRUSTED_OPA_WRAPPER_ROOT_ENV_NAMES = ("ProgramFiles", "ProgramFiles(x86)")


WINDOWS_SYSTEM_ROOT_FALLBACK = r"C:\Windows"


ALLOWED_OPA_COMMAND_WRAPPER_OPTIONS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "docker": frozenset(
            {
                "--cpus",
                "--init",
                "--memory",
                "--network",
                "--pids-limit",
                "--read-only",
                "--rm",
                "--user",
                "--volume",
                "-v",
                "run",
            }
        ),
        "nice": frozenset({"--adjustment", "-n"}),
        "prlimit": frozenset(
            {
                "--adjustment",
                "--as",
                "--cpu",
                "--data",
                "--fsize",
                "--memlock",
                "--nice",
                "--nofile",
                "--nproc",
                "--pid",
                "--priority",
                "--rss",
                "--stack",
                "-n",
            }
        ),
        "sudo": frozenset({"--user", "-n", "-u"}),
    }
)


ALLOWED_OPA_COMMAND_WRAPPERS = frozenset(ALLOWED_OPA_COMMAND_WRAPPER_OPTIONS)


OPA_WRAPPER_OPTIONS_WITH_VALUES: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "docker": frozenset({"--cpus", "--memory", "--network", "--pids-limit", "--user", "--volume", "-v"}),
        "nice": frozenset({"--adjustment", "-n"}),
        "prlimit": frozenset(
            {
                "--adjustment",
                "--as",
                "--cpu",
                "--data",
                "--fsize",
                "--memlock",
                "--nice",
                "--nofile",
                "--nproc",
                "--pid",
                "--priority",
                "--rss",
                "--stack",
                "-n",
            }
        ),
        "sudo": frozenset({"--user", "-u"}),
    }
)


def _opa_command(args: Sequence[str]) -> list[str]:
    wrapper = os.environ.get(OEP_OPA_COMMAND_WRAPPER_ENV)
    if wrapper is None or wrapper.strip() == "":
        return list(args)
    try:
        wrapper_args = shlex.split(wrapper)
    except ValueError as exc:
        raise OpaEvaluationError(f"{OEP_OPA_COMMAND_WRAPPER_ENV} could not be parsed: {exc}") from exc
    if not wrapper_args:
        return list(args)
    _validate_opa_command_wrapper(wrapper_args)
    wrapper_args[0] = _resolve_opa_command_wrapper_executable(wrapper_args[0])
    return wrapper_args + list(args)


def _resolve_opa_command_wrapper_executable(executable: str) -> str:
    resolved = shutil.which(executable, path=_opa_command_wrapper_search_path())
    if resolved is None:
        raise OpaEvaluationError(
            f"authorized {OEP_OPA_COMMAND_WRAPPER_ENV} executable not found on PATH: {executable!r}"
        )
    if os.name == "nt":
        return _resolve_windows_opa_command_wrapper_path(resolved)
    resolved_path = Path(resolved).resolve()
    trusted_dirs = {path.resolve() for path in TRUSTED_OPA_WRAPPER_DIRS if path.exists()}
    if resolved_path.parent not in trusted_dirs:
        allowed = ", ".join(str(path) for path in TRUSTED_OPA_WRAPPER_DIRS)
        raise OpaEvaluationError(
            f"authorized {OEP_OPA_COMMAND_WRAPPER_ENV} executable resolved to untrusted path: {resolved_path}. "
            f"Expected one of: {allowed}"
        )
    return str(resolved_path)


def _opa_command_wrapper_search_path() -> str:
    path = os.environ.get("PATH", os.defpath)
    entries = [entry for entry in path.split(os.pathsep) if _is_absolute_opa_wrapper_search_path_entry(entry)]
    return os.pathsep.join(entries)


def _is_absolute_opa_wrapper_search_path_entry(entry: str) -> bool:
    if entry == "" or entry == os.curdir:
        return False
    expanded = os.path.expanduser(os.path.expandvars(entry))
    if os.name == "nt":
        return ntpath.isabs(expanded)
    return Path(expanded).is_absolute()


def _resolve_windows_opa_command_wrapper_path(resolved: str) -> str:
    normalized = ntpath.normpath(_resolve_windows_filesystem_path(resolved))
    normalized_for_compare = ntpath.normcase(normalized)
    trusted_roots = _trusted_windows_opa_wrapper_roots()
    if not ntpath.isabs(normalized) or not any(
        _windows_path_is_relative_to(normalized_for_compare, trusted_root) for trusted_root in trusted_roots
    ):
        allowed = ", ".join(trusted_roots)
        raise OpaEvaluationError(
            f"authorized {OEP_OPA_COMMAND_WRAPPER_ENV} executable resolved to untrusted path: {normalized}. "
            f"Expected one of: {allowed}"
        )
    return normalized


def _resolve_windows_filesystem_path(resolved: str) -> str:
    try:
        candidate = str(Path(resolved).resolve(strict=False))
    except (OSError, RuntimeError):
        return resolved
    # Non-Windows test runners cannot resolve Windows drive paths faithfully.
    # On real Windows this keeps junction/symlink resolution in the trust check.
    if ntpath.isabs(candidate) and ntpath.splitdrive(candidate)[0]:
        return candidate
    return resolved


def _trusted_windows_opa_wrapper_roots() -> tuple[str, ...]:
    system_root = next(
        (value for name in WINDOWS_SYSTEM_ROOT_ENV_NAMES if (value := os.environ.get(name))),
        WINDOWS_SYSTEM_ROOT_FALLBACK,
    )
    roots = [ntpath.join(system_root, "System32")]
    roots.extend(value for name in WINDOWS_TRUSTED_OPA_WRAPPER_ROOT_ENV_NAMES if (value := os.environ.get(name)))
    return tuple(ntpath.normcase(ntpath.normpath(root)) for root in roots)


def _windows_path_is_relative_to(path: str, root: str) -> bool:
    try:
        return ntpath.commonpath((path, root)) == root
    except ValueError:
        return False


def _validate_opa_command_wrapper(wrapper_args: Sequence[str]) -> None:
    executable = wrapper_args[0]
    if executable not in ALLOWED_OPA_COMMAND_WRAPPERS:
        allowed = ", ".join(sorted(ALLOWED_OPA_COMMAND_WRAPPERS))
        raise OpaEvaluationError(
            f"unauthorized {OEP_OPA_COMMAND_WRAPPER_ENV} executable: {executable!r}. Allowed wrappers: {allowed}"
        )
    if executable == "docker":
        _validate_docker_opa_command_wrapper(wrapper_args)
        return
    _validate_option_only_opa_command_wrapper(executable, wrapper_args)


def _validate_option_only_opa_command_wrapper(executable: str, wrapper_args: Sequence[str]) -> None:
    allowed_options = ALLOWED_OPA_COMMAND_WRAPPER_OPTIONS[executable]
    value_options = OPA_WRAPPER_OPTIONS_WITH_VALUES[executable]
    index = 1
    while index < len(wrapper_args):
        argument = wrapper_args[index]
        option, inline_value = _split_wrapper_option(argument)
        if option not in allowed_options:
            _raise_unauthorized_opa_wrapper_argument(argument)
        if inline_value is not None:
            if option not in value_options:
                _raise_unauthorized_opa_wrapper_argument(argument)
            _validate_opa_wrapper_option_value(executable, option, inline_value, argument)
        elif option in value_options:
            index += 1
            if index >= len(wrapper_args):
                _raise_unauthorized_opa_wrapper_argument(argument)
            _validate_opa_wrapper_option_value(executable, option, wrapper_args[index], wrapper_args[index])
        index += 1


def _validate_docker_opa_command_wrapper(wrapper_args: Sequence[str]) -> None:
    if len(wrapper_args) < 2 or wrapper_args[1] != "run":
        argument = wrapper_args[1] if len(wrapper_args) > 1 else "<missing docker subcommand>"
        _raise_unauthorized_opa_wrapper_argument(argument)

    allowed_options = ALLOWED_OPA_COMMAND_WRAPPER_OPTIONS["docker"]
    value_options = OPA_WRAPPER_OPTIONS_WITH_VALUES["docker"]
    image_seen = False
    init_seen = False
    index = 2
    while index < len(wrapper_args):
        argument = wrapper_args[index]
        option, inline_value = _split_wrapper_option(argument)
        if not image_seen and option in allowed_options and option != "run":
            if option == "--init":
                init_seen = True
            if inline_value is not None:
                if option not in value_options:
                    _raise_unauthorized_opa_wrapper_argument(argument)
                _validate_docker_wrapper_option_value(option, inline_value, argument)
            elif option in value_options:
                index += 1
                if index >= len(wrapper_args):
                    _raise_unauthorized_opa_wrapper_argument(argument)
                _validate_docker_wrapper_option_value(option, wrapper_args[index], wrapper_args[index])
            index += 1
            continue
        if not image_seen and OPA_DOCKER_IMAGE_RE.fullmatch(argument):
            image_seen = True
            index += 1
            continue
        _raise_unauthorized_opa_wrapper_argument(argument)

    if not image_seen:
        _raise_unauthorized_opa_wrapper_argument("<missing docker image>")
    if not init_seen:
        raise OpaEvaluationError(
            f"{OEP_OPA_COMMAND_WRAPPER_ENV} docker wrappers must include --init so timeout cleanup can signal "
            "containerized OPA reliably."
        )


def _split_wrapper_option(argument: str) -> tuple[str, str | None]:
    if argument.startswith("--") and "=" in argument:
        option, value = argument.split("=", 1)
        return option, value
    return argument, None


def _validate_opa_wrapper_option_value(
    executable: str,
    option: str,
    value: str,
    argument: str,
) -> None:
    if executable == "sudo":
        if OPA_WRAPPER_USER_VALUE_RE.fullmatch(value):
            return
    elif OPA_WRAPPER_NUMERIC_VALUE_RE.fullmatch(value):
        return
    _raise_unauthorized_opa_wrapper_argument(f"{option} {argument}")


def _validate_docker_wrapper_option_value(option: str, value: str, argument: str) -> None:
    if option == "--network":
        if value == "none":
            return
    elif option == "--user":
        if OPA_WRAPPER_USER_VALUE_RE.fullmatch(value):
            return
    elif option == "--memory":
        if OPA_DOCKER_MEMORY_VALUE_RE.fullmatch(value):
            return
    elif option in {"--volume", "-v"}:
        _validate_docker_read_only_volume(value, argument)
        return
    elif OPA_WRAPPER_NUMERIC_VALUE_RE.fullmatch(value):
        return
    _raise_unauthorized_opa_wrapper_argument(f"{option} {argument}")


def _opa_policy_bundle_data_path(policy_bundle_path: Path) -> str:
    wrapper = os.environ.get(OEP_OPA_COMMAND_WRAPPER_ENV)
    if wrapper is None or wrapper.strip() == "":
        return str(policy_bundle_path)
    try:
        wrapper_args = shlex.split(wrapper)
    except ValueError:
        return str(policy_bundle_path)
    if len(wrapper_args) < 2 or wrapper_args[0] != "docker" or wrapper_args[1] != "run":
        return str(policy_bundle_path)

    policy_path = policy_bundle_path.resolve(strict=False)
    for source, target in _docker_read_only_volume_mappings(wrapper_args):
        source_path = Path(os.path.expanduser(os.path.expandvars(source))).resolve(strict=False)
        try:
            relative_policy_path = policy_path.relative_to(source_path)
        except ValueError:
            continue
        target_path = PurePosixPath(target)
        if relative_policy_path.parts:
            target_path = target_path.joinpath(*relative_policy_path.parts)
        return target_path.as_posix()
    return str(policy_bundle_path)


def _docker_read_only_volume_mappings(wrapper_args: Sequence[str]) -> list[tuple[str, str]]:
    mappings: list[tuple[str, str]] = []
    image_seen = False
    index = 2
    while index < len(wrapper_args):
        argument = wrapper_args[index]
        option, inline_value = _split_wrapper_option(argument)
        if not image_seen and option in {"--volume", "-v"}:
            if inline_value is not None:
                mappings.append(_docker_read_only_volume_mapping(inline_value, argument))
            else:
                index += 1
                if index >= len(wrapper_args):
                    _raise_unauthorized_opa_wrapper_argument(argument)
                mappings.append(_docker_read_only_volume_mapping(wrapper_args[index], wrapper_args[index]))
            index += 1
            continue
        if not image_seen and option in ALLOWED_OPA_COMMAND_WRAPPER_OPTIONS["docker"] and option != "run":
            if inline_value is None and option in OPA_WRAPPER_OPTIONS_WITH_VALUES["docker"]:
                index += 1
            index += 1
            continue
        if not image_seen and OPA_DOCKER_IMAGE_RE.fullmatch(argument):
            image_seen = True
        index += 1
    return mappings


def _validate_docker_read_only_volume(value: str, argument: str) -> None:
    _docker_read_only_volume_mapping(value, argument)


def _docker_read_only_volume_mapping(value: str, argument: str) -> tuple[str, str]:
    parts = value.rsplit(":", 2)
    if len(parts) != 3:
        _raise_unauthorized_opa_wrapper_argument(argument)
    source, target, mode = parts
    if mode != "ro":
        _raise_unauthorized_opa_wrapper_argument(argument)
    if not _is_absolute_host_volume_source(source):
        _raise_unauthorized_opa_wrapper_argument(argument)
    target_path = PurePosixPath(target)
    if not target or not target_path.is_absolute() or ".." in target_path.parts:
        _raise_unauthorized_opa_wrapper_argument(argument)
    return source, target


def _is_absolute_host_volume_source(source: str) -> bool:
    if not source or "\x00" in source or "\n" in source:
        return False
    expanded = os.path.expanduser(os.path.expandvars(source))
    return Path(expanded).is_absolute() or ntpath.isabs(expanded)


def _raise_unauthorized_opa_wrapper_argument(argument: str) -> Never:
    raise OpaEvaluationError(
        f"unauthorized {OEP_OPA_COMMAND_WRAPPER_ENV} argument: {argument!r}. "
        "Wrapper arguments must use the allow-listed options and strict value formats for the selected wrapper."
    )
