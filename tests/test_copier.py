"""The rendered project, rather than internal replacement helpers, is the contract."""

from __future__ import annotations

import json
import keyword
import re
import sys
import tomllib
from pathlib import Path

import pytest
import yaml
from copier import run_copy

from tests.copier_helpers import ROOT, git


def render(source: Path, destination: Path, **answers: str) -> Path:
    data = {"project_name": "example-project", "repo_owner": "acme", **answers}
    run_copy(str(source), destination, data=data, defaults=True, vcs_ref="HEAD", quiet=True)
    return destination


@pytest.mark.parametrize("project_name", ["server", "weather-service", "my-python-app", "match", "type"])
def test_rendered_project_contract(template_source, tmp_path, project_name):
    destination = render(template_source, tmp_path / "project", project_name=project_name)
    package = project_name.replace("-", "_")
    metadata = tomllib.loads((destination / "pyproject.toml").read_text())
    assert metadata["project"]["name"] == project_name
    assert metadata["project"]["version"] == "0.0.0"
    assert metadata["project"]["requires-python"] == ">=3.11"
    assert "docs" in metadata["dependency-groups"]
    assert "pythonVersion" not in metadata["tool"]["pyright"]
    assert metadata["project"]["scripts"] == {project_name: f"{package}.__main__:cli"}
    assert metadata["project"]["urls"]["Repository"] == f"https://github.com/acme/{project_name}"
    assert metadata["project"]["dependencies"] == []
    assert metadata["tool"]["pyright"]["typeCheckingMode"] == "strict"
    assert metadata["tool"]["coverage"]["report"]["fail_under"] == 80
    root_metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
    root_ruff = {key: value for key, value in root_metadata["tool"]["ruff"].items() if key != "src"}
    output_ruff = {key: value for key, value in metadata["tool"]["ruff"].items() if key != "src"}
    assert output_ruff == root_ruff
    path_keys = {"include", "extraPaths"}
    assert {key: value for key, value in metadata["tool"]["pyright"].items() if key not in path_keys} == {
        key: value for key, value in root_metadata["tool"]["pyright"].items() if key not in path_keys
    }
    assert metadata["tool"]["coverage"]["report"] == root_metadata["tool"]["coverage"]["report"]
    assert metadata["tool"]["coverage"]["run"]["branch"] == root_metadata["tool"]["coverage"]["run"]["branch"]
    assert (destination / "src" / package / "__main__.py").is_file()
    assert not (destination / "src/your_package").exists()
    for filename in (
        "AGENTS.md",
        "CLAUDE.md",
        ".claude/settings.json",
        ".codex/config.toml",
        ".codex/hooks.json",
        "scripts/hooks/guard_config.py",
        "tests/test_agent_permissions.py",
        "Makefile",
        ".github/workflows/ci.yml",
    ):
        assert (destination / filename).is_file(), filename
    assert (destination / "AGENTS.md").read_bytes() == (ROOT / "AGENTS.md").read_bytes()
    for workflow in (destination / ".github/workflows").glob("*.yml"):
        assert workflow.read_bytes() == (ROOT / ".github/workflows" / workflow.name).read_bytes()
    for filename in (
        "copier.yml",
        "template",
        "scripts/bootstrap.py",
        ".github/.template-pending",
        ".github/workflows/template-cleanup.yml",
    ):
        assert not (destination / filename).exists(), filename
    recorded = yaml.safe_load((destination / ".copier-answers.yml").read_text())
    assert recorded["project_name"] == project_name
    assert Path(recorded["_src_path"]).resolve() == template_source.resolve()
    assert git(template_source, "rev-parse", recorded["_commit"]) == git(template_source, "rev-parse", "HEAD")


def test_metadata_answers_are_escaped(template_source, tmp_path):
    description = 'A "quoted" description with a backslash \\ and Unicode: ölçüm 🚀'
    author = 'Ayd\u0131n "Engineering"'
    destination = render(template_source, tmp_path / "project", description=description, author=author)
    metadata = tomllib.loads((destination / "pyproject.toml").read_text())
    assert metadata["project"]["description"] == description
    assert metadata["project"]["authors"] == [{"name": author}]


@pytest.mark.parametrize(
    "project_name", ["../escape-project", "Bad-Name", "bad--name", "9-start", *keyword.kwlist, "bad_name", "a.b"]
)
def test_invalid_project_names_are_rejected(template_source, tmp_path, project_name):
    with pytest.raises(ValueError):
        render(template_source, tmp_path / "project", project_name=project_name)
    assert not (tmp_path / "escape-project").exists()


def test_invalid_owner_is_rejected(template_source, tmp_path):
    with pytest.raises(ValueError):
        render(template_source, tmp_path / "project", repo_owner="bad/owner")


def test_copy_has_no_implicit_tasks(template_source, tmp_path):
    destination = render(template_source, tmp_path / "project")
    assert not (destination / ".venv").exists()
    assert not (destination / "node_modules").exists()
    assert not (destination / "uv.lock").exists()


@pytest.mark.parametrize(
    "project_name", ["sys", "logging", "argparse", "typing", "pytest", "tests", "scripts", "server\n"]
)
def test_reserved_or_newline_package_names_are_rejected(template_source, tmp_path, project_name):
    with pytest.raises(ValueError):
        render(template_source, tmp_path / "project", project_name=project_name)


def test_owner_with_trailing_newline_is_rejected(template_source, tmp_path):
    with pytest.raises(ValueError):
        render(template_source, tmp_path / "project", repo_owner="acme\n")


def test_reserved_names_cover_the_supported_interpreter():
    reserved = set(json.loads((ROOT / "reserved-package-names.json").read_text()))
    standard_names = {name for name in sys.stdlib_module_names if re.fullmatch("[a-z][a-z0-9_]*", name)}
    assert standard_names <= reserved
    assert set(keyword.kwlist) - {"False", "True", "None"} <= reserved
    assert {"tests", "scripts", "pytest", "yaml", "mkdocs", "mkdocstrings", "uv_build"} <= reserved
    assert not {"server", "weather_service", "match", "type", "copier", "plumbum"} & reserved
