"""Integration test: apply template_init.py to a copy of the template tree.

Proves that the cleanup pipeline turns a template-shaped repo into a clean,
installable, lint-clean, test-green Python project.

Marked `integration` so that `make check` (which excludes the marker) stays fast.
Run explicitly:   uv run --group dev pytest tests/test_template_init_integration.py -v
"""

from __future__ import annotations

import datetime
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


REPO_ROOT = Path(__file__).resolve().parent.parent


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=T", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", "commit", "-qm", "seed"],
        cwd=repo,
        check=True,
    )


def test_full_template_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Copy the template into tmp_path. Exclude the bits that would bloat the test
    # (venv, git history, caches, superpowers) but KEEP scripts/ and .github/ so the script
    # can self-delete from something real.
    dst = tmp_path / "target"
    shutil.copytree(
        REPO_ROOT,
        dst,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            ".pytest_cache",
            ".ruff_cache",
            "__pycache__",
            ".superpowers",
            "site",
            "htmlcov",
            "dist",
        ),
    )

    # Simulate a template repo that has already shipped releases: its own
    # changelog must NOT leak into the downstream repo.
    (dst / "CHANGELOG.md").write_text("## v0.4.0 (2026-01-01)\n\n### Feat\n\n- template internal history\n")

    _git_init(dst)

    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/test-target")
    monkeypatch.setenv("REPO_DESCRIPTION", "A neat demo service.")

    subprocess.run(
        ["uv", "run", "python", "scripts/template_init.py", "--repo", str(dst)],
        cwd=dst,
        check=True,
        env={**os.environ, "GITHUB_REPOSITORY": "acme/test-target", "REPO_DESCRIPTION": "A neat demo service."},
    )

    # Substitutions applied
    for rel in ("pyproject.toml", "README.md", "mkdocs.yml", "Makefile"):
        text = (dst / rel).read_text()
        assert "python-dev-template" not in text
        assert "your_package" not in text

    assert (dst / "mkdocs.yml").is_file()
    # Repo description injected everywhere; no marker left anywhere
    for rel in ("pyproject.toml", "mkdocs.yml", "docs/index.md", "README.md"):
        text = (dst / rel).read_text()
        assert "{{PROJECT_DESCRIPTION}}" not in text, rel
    assert 'description = "A neat demo service."' in (dst / "pyproject.toml").read_text()
    assert "A neat demo service." in (dst / "README.md").read_text()
    assert "Fill in the project description" not in (dst / "POST_SETUP.md").read_text()
    assert "{{REPO_OWNER}}" not in (dst / "pyproject.toml").read_text()
    assert "{{AUTHOR}}" not in (dst / "pyproject.toml").read_text()

    # [tool.uv.build-backend] block stripped — default discovery applies downstream
    pyproject_text = (dst / "pyproject.toml").read_text()
    assert "[tool.uv.build-backend]" not in pyproject_text

    # Template-only pytest/pyright residue removed
    assert 'pythonpath = ["src", "."]' not in pyproject_text
    assert 'pythonpath = ["src"]' in pyproject_text
    assert 'extraPaths = ["."]' not in pyproject_text
    assert "integration: integration tests" not in pyproject_text
    assert '"scripts/*"' not in pyproject_text
    assert "cleanup helpers accept a positional" not in pyproject_text
    assert 'keywords = ["template"]' not in pyproject_text
    assert "keywords = []" in pyproject_text

    # No template-only coverage omit — symmetric with source repos
    assert "omit = [" not in pyproject_text

    # LICENSE shipped, placeholders substituted to the repo owner + current year
    license_text = (dst / "LICENSE").read_text()
    assert "{{AUTHOR}}" not in license_text
    assert "{{YEAR}}" not in license_text
    assert "MIT License" in license_text
    assert "acme" in license_text
    current_year = str(datetime.datetime.now(tz=datetime.UTC).year)
    assert current_year in license_text

    # Downstream repo always starts unreleased at 0.0.0, even if the template
    # repo has bumped past that point.
    downstream_pyproject = (dst / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.0.0"' in downstream_pyproject

    # Dir renamed
    assert (dst / "src" / "test_target").is_dir()
    assert not (dst / "src" / "your_package").exists()

    # Machinery deleted
    assert not (dst / "scripts" / "template_init.py").exists()
    assert not (dst / "scripts" / "__init__.py").exists()
    assert not (dst / ".github" / "workflows" / "template-cleanup.yml").exists()
    assert not (dst / ".github" / "workflows" / "template-ci.yml").exists()
    assert not (dst / ".github" / ".template-pending").exists()
    assert not (dst / "tests" / "test_template_init.py").exists()
    assert not (dst / "tests" / "test_template_init_integration.py").exists()

    # Template's own changelog must not leak downstream
    assert not (dst / "CHANGELOG.md").exists()

    # POST_SETUP exists
    assert (dst / "POST_SETUP.md").is_file()

    # uv.lock generated
    assert (dst / "uv.lock").is_file()

    # Ultimate proof: make check + docs build pass on the transformed repo
    subprocess.run(["uv", "sync", "--group", "dev", "--group", "docs"], cwd=dst, check=True)
    subprocess.run(["make", "check"], cwd=dst, check=True)
    subprocess.run(["make", "docs-build"], cwd=dst, check=True)
