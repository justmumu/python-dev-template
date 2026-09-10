"""Prepare local releases and validate changelog notes for GitHub Releases."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import tomllib
from pathlib import Path


def _run(repo: Path, *arguments: str) -> str:
    """Stop on the first failed command and keep its diagnostics visible."""
    excluded = {"VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "UV_PROJECT", "UV_WORKING_DIR", "PYTHONPATH"}
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_") and key not in excluded
    }
    result = subprocess.run(arguments, cwd=repo, env=environment, text=True, capture_output=True, check=False)
    if result.returncode:
        print(result.stdout, end="")
        print(result.stderr, end="")
        result.check_returncode()
    return result.stdout.strip()


def _require_root(repo: Path) -> None:
    if Path(_run(repo, "git", "rev-parse", "--show-toplevel")).resolve() != repo.resolve():
        raise ValueError("Run release commands from the repository root.")
    if _run(repo, "git", "rev-parse", "--is-shallow-repository") != "false":
        raise ValueError("Release commands need full Git history; fetch with --unshallow first.")


def _require_clean(repo: Path) -> str:
    _require_root(repo)
    branch = _run(repo, "git", "rev-parse", "--abbrev-ref", "HEAD")
    if branch in {"main", "master", "HEAD"}:
        raise ValueError("Create a feature branch before preparing a release.")
    entries = _run(repo, "git", "ls-files", "-v", "-z").split("\0")
    if any(entry and (entry[0].islower() or entry[0] == "S") for entry in entries):
        raise ValueError("A clean release cannot use index flags that hide local changes.")
    if _run(repo, "git", "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("A release requires a clean working tree and index; commit or stash changes first.")
    return branch


def changelog(repo: Path, version: str | None = None) -> None:
    """Generate application-only history through Commitizen, then format Markdown."""
    _require_root(repo)
    arguments = ["uv", "run", "--group", "dev", "cz", "changelog"]
    if (repo / ".copier-answers.yml").is_file():
        introductions = _run(
            repo, "git", "log", "--first-parent", "--diff-filter=A", "--format=%H", "--", ".copier-answers.yml"
        ).splitlines()
        if not introductions:
            raise ValueError("Commit the generated project before creating its changelog.")
        # GitHub setup preserves generator history; the first answers commit is
        # the application boundary. Later Copier updates do not move it.
        arguments.extend(["--start-rev", introductions[-1]])
    if version is not None:
        arguments.extend(["--unreleased-version", f"v{version}"])
    _run(repo, *arguments)
    _run(repo, "uv", "run", "--group", "dev", "mdformat", "CHANGELOG.md")


def _section(text: str, tag: str) -> str:
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if re.fullmatch(rf"## {re.escape(tag)}(?: \([^\n]*\))?", line)]
    if len(starts) != 1:
        raise ValueError(f"CHANGELOG.md must contain exactly one section for {tag}.")
    start = starts[0]
    end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")), len(lines))
    return "\n".join(lines[start:end]).strip() + "\n"


def bump(repo: Path, segment: str) -> None:
    """Use uv for metadata, then commit and annotate a local tag with hooks active."""
    if segment not in {"patch", "minor", "major"}:
        raise ValueError("Choose a patch, minor or major version bump.")
    branch = _require_clean(repo)
    version = _run(repo, "uv", "version", "--bump", segment, "--dry-run", "--short")
    tag = f"v{version}"
    if tag in _run(repo, "git", "tag", "--list").splitlines():
        raise ValueError(f"Tag {tag} already exists; no files changed.")
    _run(repo, "uv", "version", "--bump", segment)
    changelog(repo, version)
    _section((repo / "CHANGELOG.md").read_text(), tag)
    _run(repo, "git", "add", "--", "pyproject.toml", "uv.lock", "CHANGELOG.md")
    _run(repo, "git", "commit", "-m", f"chore: bump version to {tag}")
    _require_clean(repo)
    _run(repo, "git", "tag", "-a", tag, "-m", tag)
    print(f"Local annotated tag {tag} created. Push branch {branch} and open a PR.")
    print(f"After its regular merge into main, push only this tag: git push origin {tag}")


def release_notes(repo: Path, tag: str) -> str:
    """Verify a merged annotated release and return only its changelog section."""
    _require_root(repo)
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ValueError("Release tags must use vMAJOR.MINOR.PATCH.")
    reference = f"refs/tags/{tag}"
    if _run(repo, "git", "cat-file", "-t", reference) != "tag":
        raise ValueError("A release requires an annotated tag.")
    _run(repo, "git", "merge-base", "--is-ancestor", reference + "^{commit}", "refs/remotes/origin/main")
    metadata = tomllib.loads(_run(repo, "git", "show", f"{reference}:pyproject.toml"))
    if metadata["project"]["version"] != tag.removeprefix("v"):
        raise ValueError("Tag and tagged pyproject.toml version must match.")
    return _section(_run(repo, "git", "show", f"{reference}:CHANGELOG.md"), tag)


def main(argv: list[str] | None = None) -> None:
    """Expose Make's local release operations and the workflow's notes validator."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    bump_parser = commands.add_parser("bump")
    bump_parser.add_argument("segment", choices=("patch", "minor", "major"))
    commands.add_parser("changelog")
    notes_parser = commands.add_parser("notes")
    notes_parser.add_argument("--tag", required=True)
    notes_parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    repo = Path.cwd()
    if arguments.command == "bump":
        bump(repo, arguments.segment)
    elif arguments.command == "changelog":
        changelog(repo)
    else:
        arguments.output.write_text(release_notes(repo, arguments.tag))


if __name__ == "__main__":
    main()
