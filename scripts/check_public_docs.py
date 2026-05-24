"""Check public documentation and repository text hygiene."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from oep_verify.artifacts import PACKAGED_ARTIFACTS, packaged_resource_sync_errors

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_TEXT_PATTERNS = (
    ("internal status labels", re.compile(r"^Status:", re.MULTILINE)),
    ("local MVP wording", re.compile(r"\blocal MVP\b|\bMVP uses\b")),
    ("unpublished-release wording", re.compile(r"not a published release|No GitHub repository")),
    ("future-public-repo wording", re.compile(r"after the public repository is enabled")),
    ("formal audit verb in value prop", re.compile(r"audit without|can audit")),
    ("stale root-package decision", re.compile(r"root `pyproject\.toml`.*intentionally empty")),
    ("stale local proof wording", re.compile(r"full local proof")),
)
PUBLIC_TEXT_GLOBS = (
    "**/*.md",
    ".github/**/*.yml",
    ".github/**/*.yaml",
    "CITATION.cff",
)
PACKAGED_MARKDOWN_ARTIFACTS = tuple(
    artifact for artifact in PACKAGED_ARTIFACTS if artifact.canonical_path.endswith(".md")
)
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def iter_files(globs: Iterable[str]) -> list[Path]:
    files: set[Path] = set()
    for pattern in globs:
        files.update(ROOT.glob(pattern))
    return sorted(
        path
        for path in files
        if path.is_file() and not any(part in {".git", ".venv"} for part in path.parts)
    )


def check_forbidden_text() -> list[str]:
    errors: list[str] = []
    for path in iter_files(PUBLIC_TEXT_GLOBS):
        text = path.read_text(encoding="utf-8")
        for label, pattern in FORBIDDEN_TEXT_PATTERNS:
            if pattern.search(text):
                errors.append(f"{path.relative_to(ROOT)} contains forbidden {label}")
    return errors


def check_markdown_links() -> list[str]:
    errors: list[str] = []
    for path in iter_files(("*.md", "**/*.md")):
        if any(part in {".git", ".venv"} for part in path.parts):
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for raw_target in MARKDOWN_LINK_RE.findall(line):
                target = raw_target.split()[0].strip("<>")
                if "://" in target or target.startswith(("mailto:", "#")):
                    continue
                target_path = target.split("#", 1)[0]
                if target_path and not (path.parent / target_path).resolve().exists():
                    errors.append(f"{path.relative_to(ROOT)}:{line_number} missing link target: {target}")
    return errors


def check_packaged_markdown_copies() -> list[str]:
    return packaged_resource_sync_errors(ROOT, PACKAGED_MARKDOWN_ARTIFACTS)


def main() -> None:
    errors = []
    errors.extend(check_forbidden_text())
    errors.extend(check_markdown_links())
    errors.extend(check_packaged_markdown_copies())
    if errors:
        raise SystemExit("\n".join(errors))
    print("Public documentation checks passed.")


if __name__ == "__main__":
    main()
