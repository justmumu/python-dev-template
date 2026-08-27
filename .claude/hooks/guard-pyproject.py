#!/usr/bin/env python3
"""PreToolUse guard: prompt user before direct edits to pyproject.toml or uv.lock.

Allows legitimate dependency management entry points (`uv add|remove|lock|sync|pip`,
`make bump-*`) to pass through untouched. Blocks ad-hoc edits via Edit/Write/MultiEdit
or shell text-mungers (`sed`, `echo >`, `tee`, `printf >`, heredoc, etc.).

On a match, emits a PreToolUse hookSpecificOutput with permissionDecision=ask so
the harness surfaces the request to the user instead of silently blocking.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, cast

GUARDED_PATTERN = re.compile(r"pyproject\.toml|uv\.lock")
BASH_ALLOWLIST = re.compile(
    r"^\s*(uv\s+(add|remove|lock|sync|pip)\b|make\s+bump-)",
)


def ask(reason: str) -> None:
    """Emit a PreToolUse hook response asking the user to approve the action."""
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": reason,
            },
        },
        sys.stdout,
    )
    sys.exit(0)


def main() -> None:
    """Read a PreToolUse payload from stdin and gate guarded pyproject/uv.lock edits."""
    payload = cast("dict[str, Any]", json.load(sys.stdin))
    tool = str(payload.get("tool_name", ""))
    tool_input = cast("dict[str, Any]", payload.get("tool_input") or {})

    if tool == "Bash":
        cmd = str(tool_input.get("command", ""))
        if BASH_ALLOWLIST.match(cmd):
            return
        if GUARDED_PATTERN.search(cmd):
            ask(f"Bash command touches pyproject.toml or uv.lock: {cmd!r}")
        return

    if tool in {"Edit", "Write", "MultiEdit"}:
        path = str(tool_input.get("file_path", ""))
        if GUARDED_PATTERN.search(path):
            ask(f"{tool} targets guarded file: {path}")


if __name__ == "__main__":
    main()