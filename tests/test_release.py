"""Release operations use real disposable Git repositories, uv and Commitizen."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
RELEASE_SPEC = importlib.util.spec_from_file_location("release", ROOT / "scripts/release.py")
assert RELEASE_SPEC is not None
assert RELEASE_SPEC.loader is not None
release = importlib.util.module_from_spec(RELEASE_SPEC)
RELEASE_SPEC.loader.exec_module(release)


def git(repo, *arguments):
    return subprocess.check_output(["git", *arguments], cwd=repo, text=True).strip()


def commit(repo, message):
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)


@pytest.fixture
def project(tmp_path, monkeypatch):
    for key in os.environ:
        if key.startswith(("GIT_", "UV_")) or key in {"VIRTUAL_ENV", "MAKEFLAGS", "MAKEOVERRIDES", "MFLAGS"}:
            monkeypatch.delenv(key)
    monkeypatch.setenv("UV_PYTHON", sys.executable)
    monkeypatch.setenv("UV_OFFLINE", "1")
    repo = tmp_path / "app"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "release-fixture"\nversion = "0.0.0"\nrequires-python = ">=3.11"\n'
        "[dependency-groups]\ndev = []\n"
        '[tool.commitizen]\nname = "cz_conventional_commits"\nversion_provider = "pep621"\ntag_format = "v$version"\n'
    )
    (repo / ".gitignore").write_text(".venv/\n")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Release Test")
    git(repo, "config", "user.email", "release@example.invalid")
    git(repo, "config", "commit.gpgsign", "false")
    git(repo, "config", "tag.gpgsign", "false")
    commit(repo, "feat: inherited template feature")
    git(repo, "tag", "-a", "v9.0.0", "-m", "template release")
    (repo / ".copier-answers.yml").write_text("project_name: release-fixture\n")
    commit(repo, "chore: initialize application")
    git(repo, "switch", "-qc", "release/first")
    (repo / "app.py").write_text('"""Application."""\n')
    commit(repo, "feat: application feature")
    return repo


def test_bump_uses_uv_changelog_and_annotated_local_tag(project):
    release.bump(project, "patch")
    assert tomllib.loads((project / "pyproject.toml").read_text())["project"]["version"] == "0.0.1"
    assert tomllib.loads((project / "uv.lock").read_text())["package"][0]["version"] == "0.0.1"
    changelog = (project / "CHANGELOG.md").read_text()
    assert "## v0.0.1" in changelog
    assert "application feature" in changelog
    assert "inherited template" not in changelog
    assert "v9.0.0" not in changelog
    assert git(project, "cat-file", "-t", "refs/tags/v0.0.1") == "tag"
    assert git(project, "log", "-1", "--format=%s") == "chore: bump version to v0.0.1"
    assert git(project, "status", "--porcelain") == ""
    assert git(project, "remote") == ""


@pytest.mark.parametrize("state", ["main", "master", "detached", "tracked", "untracked", "staged"])
def test_bump_requires_clean_feature_branch(project, state):
    if state in {"main", "master"}:
        git(project, "branch", "-m", state) if state == "master" else git(project, "switch", "main")
    elif state == "detached":
        git(project, "checkout", "--detach", "-q")
    else:
        (project / ("app.py" if state == "tracked" else "new.py")).write_text("# local edit\n")
        if state == "staged":
            git(project, "add", "new.py")
    original = (project / "pyproject.toml").read_bytes()
    with pytest.raises(ValueError, match=r"feature branch|clean"):
        release.bump(project, "patch")
    assert (project / "pyproject.toml").read_bytes() == original
    assert "v0.0.1" not in git(project, "tag").splitlines()


@pytest.mark.parametrize("hook", ["pre-commit", "commit-msg"])
def test_failed_git_hook_stops_before_tag_without_disabling_hooks(project, hook):
    hook_path = project / ".git/hooks" / hook
    hook_path.write_text("#!/bin/sh\nexit 1\n")
    hook_path.chmod(0o755)
    head = git(project, "rev-parse", "HEAD")
    with pytest.raises(subprocess.CalledProcessError):
        release.bump(project, "patch")
    assert git(project, "rev-parse", "HEAD") == head
    assert "v0.0.1" not in git(project, "tag").splitlines()
    assert (project / "CHANGELOG.md").exists()


@pytest.mark.parametrize("phase", ["version", "changelog", "format"])
def test_command_failure_stops_before_commit_and_tag(project, monkeypatch, phase):
    original_run = release._run
    head = git(project, "rev-parse", "HEAD")
    failed = False

    def fail_step(repo, *arguments):
        nonlocal failed
        matches = {
            "version": arguments == ("uv", "version", "--bump", "patch"),
            "changelog": "cz" in arguments,
            "format": "mdformat" in arguments,
        }
        if matches[phase]:
            failed = True
            raise subprocess.CalledProcessError(1, arguments)
        return original_run(repo, *arguments)

    monkeypatch.setattr(release, "_run", fail_step)
    with pytest.raises(subprocess.CalledProcessError):
        release.bump(project, "patch")
    assert failed
    assert git(project, "rev-parse", "HEAD") == head
    assert "v0.0.1" not in git(project, "tag").splitlines()


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
def test_hidden_edits_are_not_a_clean_release(project, flag):
    git(project, "update-index", flag, "app.py")
    (project / "app.py").write_text("# hidden edit\n")
    assert git(project, "status", "--porcelain") == ""
    with pytest.raises(ValueError, match="index flags"):
        release.bump(project, "patch")
    assert "v0.0.1" not in git(project, "tag").splitlines()


def test_post_commit_edits_stop_tag_creation(project):
    hook = project / ".git/hooks/post-commit"
    hook.write_text("#!/bin/sh\nprintf '\\n# hook change\\n' >> app.py\n")
    hook.chmod(0o755)
    with pytest.raises(ValueError, match="clean"):
        release.bump(project, "patch")
    assert git(project, "log", "-1", "--format=%s") == "chore: bump version to v0.0.1"
    assert "v0.0.1" not in git(project, "tag").splitlines()


def test_existing_tag_is_rejected_before_metadata_changes(project):
    git(project, "tag", "-a", "v0.0.1", "-m", "already exists")
    original = (project / "pyproject.toml").read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        release.bump(project, "patch")
    assert (project / "pyproject.toml").read_bytes() == original
    assert git(project, "status", "--porcelain") == ""


def test_standalone_changelog_preserves_version_and_scopes_history(project):
    original = (project / "pyproject.toml").read_bytes()
    release.changelog(project)
    text = (project / "CHANGELOG.md").read_text()
    assert "Unreleased" in text
    assert "application feature" in text
    assert "inherited template" not in text
    assert (project / "pyproject.toml").read_bytes() == original
    assert "v0.0.1" not in git(project, "tag").splitlines()


def test_generator_changelog_includes_its_own_history(project):
    git(project, "rm", ".copier-answers.yml")
    commit(project, "test: generator fixture without answers")
    release.changelog(project)
    text = (project / "CHANGELOG.md").read_text()
    assert "inherited template feature" in text
    assert "v9.0.0" in text


def test_notes_cli_writes_only_the_verified_section(project, monkeypatch, tmp_path):
    release.bump(project, "patch")
    git(project, "update-ref", "refs/remotes/origin/main", "HEAD")
    output = tmp_path / "notes.md"
    monkeypatch.chdir(project)
    release.main(["notes", "--tag", "v0.0.1", "--output", str(output)])
    assert "application feature" in output.read_text()
    assert "inherited template" not in output.read_text()


def test_consecutive_release_keeps_earlier_application_section(project):
    release.bump(project, "patch")
    (project / "app.py").write_text('"""Corrected application."""\n')
    (project / ".copier-answers.yml").write_text("project_name: release-fixture\n_commit: updated-template\n")
    commit(project, "fix: correct application feature")
    release.bump(project, "minor")
    changelog = (project / "CHANGELOG.md").read_text()
    assert "## v0.1.0" in changelog
    assert "## v0.0.1" in changelog
    assert "inherited template" not in changelog
    git(project, "update-ref", "refs/remotes/origin/main", "HEAD")
    notes = release.release_notes(project, "v0.1.0")
    assert "correct application feature" in notes
    assert "## v0.0.1" not in notes


@pytest.mark.parametrize("problem", ["lightweight", "unmerged", "metadata", "section"])
def test_release_notes_reject_invalid_release_identity(project, problem):
    release.bump(project, "patch")
    if problem == "lightweight":
        git(project, "tag", "-d", "v0.0.1")
        git(project, "tag", "v0.0.1")
    if problem == "section":
        (project / "CHANGELOG.md").write_text("## v0.0.10\n\nWrong version.\n")
        commit(project, "test: wrong release notes")
        git(project, "tag", "-fa", "v0.0.1", "-m", "fixture")
    if problem == "metadata":
        git(project, "tag", "-a", "v0.0.2", "-m", "wrong version")
    git(project, "update-ref", "refs/remotes/origin/main", "HEAD~1" if problem == "unmerged" else "HEAD")
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        release.release_notes(project, "v0.0.2" if problem == "metadata" else "v0.0.1")


@pytest.mark.parametrize("exists", [True, False])
def test_github_release_step_is_idempotent(tmp_path, exists):
    workflow = Path(__file__).resolve().parent.parent / ".github/workflows/release.yml"
    script = yaml.safe_load(workflow.read_text())["jobs"]["release"]["steps"][-1]["run"]
    executable = tmp_path / "gh"
    executable.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$RELEASE_CALLS"\n'
        'if [ "$2" = view ]; then exit "$RELEASE_EXISTS_STATUS"; fi\n'
    )
    executable.chmod(0o755)
    calls = tmp_path / "calls.txt"
    environment = {
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "RELEASE_CALLS": str(calls),
        "RELEASE_EXISTS_STATUS": "0" if exists else "1",
        "GITHUB_REF_NAME": "v0.1.0",
        "RUNNER_TEMP": str(tmp_path),
    }
    subprocess.run(["sh", "-eu", "-c", script], env=environment, check=True)
    commands = calls.read_text().splitlines()
    assert commands[0] == "release view v0.1.0"
    if exists:
        assert len(commands) == 1
    else:
        assert commands[1] == (
            f"release create v0.1.0 --verify-tag --title v0.1.0 --notes-file {tmp_path}/release-notes.md"
        )
