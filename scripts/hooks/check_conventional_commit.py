#!/usr/bin/env python3
"""Validate commit subject against project Conventional Commits rules.

Rules:
- First line matches ``<type>[(scope)][!]: <subject>``.
- ``type`` in the allowed set.
- Entire first line (type + scope + subject) ≤ 72 characters.
- Subject does not end with a period.
- Autosquash (``fixup!``/``squash!``/``amend!``), merge and revert-autogen
  commits bypass all checks.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TYPES = (
    "feat",
    "fix",
    "docs",
    "chore",
    "ci",
    "refactor",
    "test",
    "style",
    "build",
    "perf",
    "revert",
)
MAX_SUBJECT = 72

PATTERN = re.compile(
    rf"^(?P<type>{'|'.join(TYPES)})"
    r"(?P<scope>\([^()\r\n]+\))?"
    r"(?P<bang>!)?: (?P<subject>.+)$"
)
SKIP_PREFIXES = ("Merge ", "fixup! ", "squash! ", "amend! ", 'Revert "')


def _error(msg: str) -> None:
    """Write ``msg`` to stderr with a trailing newline."""
    sys.stderr.write(msg + "\n")


def main() -> int:
    """Validate the commit message file passed as ``argv[1]``."""
    path = Path(sys.argv[1])
    raw = path.read_text(encoding="utf-8").splitlines()
    content = [line for line in raw if not line.lstrip().startswith("#")]
    if not content or not content[0].strip():
        _error("error: commit message is empty")
        return 1

    subject_line = content[0]
    if subject_line.startswith(SKIP_PREFIXES):
        return 0

    match = PATTERN.match(subject_line)
    if match is None:
        _error(f"error: subject does not match Conventional Commits\n  {subject_line}")
        _error(f"expected: <type>[(scope)][!]: <subject>\ntypes:    {', '.join(TYPES)}")
        return 1

    subject = match.group("subject")
    if subject.endswith("."):
        _error(f"error: subject must not end with a period\n  {subject_line}")
        return 1
    if len(subject_line) > MAX_SUBJECT:
        _error(f"error: subject line too long ({len(subject_line)} > {MAX_SUBJECT})\n  {subject_line}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
