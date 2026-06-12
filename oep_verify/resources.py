"""Shared loader for packaged resources used by the per-package paths modules."""

from __future__ import annotations

import atexit
from collections.abc import Callable
from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path
from threading import Lock

_RESOURCE_STACK = ExitStack()
atexit.register(_RESOURCE_STACK.close)


def package_resource_loader(package_name: str) -> Callable[..., Path]:
    """Return a cached, thread-safe filesystem-path loader for *package_name* resources.

    The returned callable accepts resource path parts below the package's
    ``resources`` directory and materializes them with
    :func:`importlib.resources.as_file`, holding the extracted paths open
    until interpreter exit.
    """

    resource_root = files(package_name).joinpath("resources")
    lock = Lock()
    resource_paths: dict[tuple[str, ...], Path] = {}

    def resource_path(*parts: str) -> Path:
        with lock:
            cached = resource_paths.get(parts)
            if cached is None:
                cached = _RESOURCE_STACK.enter_context(as_file(resource_root.joinpath(*parts)))
                resource_paths[parts] = cached
            return cached

    return resource_path


__all__ = ["package_resource_loader"]
