"""Run the emitted project's complete gates and built entrypoint, including GitHub setup."""

import os
import shutil
import subprocess
import tomllib

import pytest
import yaml
from copier import run_copy
from scripts.bootstrap import bootstrap, validate_project

from tests.copier_helpers import git

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("route", ["local", "github"])
@pytest.mark.parametrize("python_version", ["3.11", "3.12", "3.13"])
def test_generated_project_end_to_end(template_source, tmp_path, monkeypatch, route, python_version):
    # uv commands inside Make and the installed CLI must use the matrix
    # interpreter instead of the generated .python-version default (3.13).
    monkeypatch.setenv("UV_PYTHON", python_version)
    for name in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "UV_PROJECT", "UV_WORKING_DIR", "PYTHONPATH"):
        monkeypatch.delenv(name, raising=False)
    destination = tmp_path / "project"
    name = "weather-service" if route == "local" else "billing-service"
    description = 'A "quoted" Python description with a backslash \\ and Unicode: ölçüm'
    if route == "github":
        shutil.copytree(template_source, destination, ignore=shutil.ignore_patterns(".git"))
        git(destination, "init", "-q", "-b", "main")
        git(destination, "add", "-A")
        git(destination, "commit", "-qm", "test: GitHub template copy")
        template_head = git(destination, "rev-parse", "HEAD")
        assert template_head != git(template_source, "rev-parse", "HEAD")
        subprocess.run(
            [
                "uv",
                "run",
                "--locked",
                "python",
                "scripts/bootstrap.py",
                "--repository",
                f"acme/{name}",
                "--description",
                description,
            ],
            cwd=destination,
            check=True,
            timeout=600,
        )
        assert not (destination / "copier.yml").exists()
        assert not (destination / "template").exists()
        assert not (destination / "scripts/bootstrap.py").exists()
        assert not bootstrap(destination, repository=f"acme/{name}")
        assert git(destination, "diff", "--name-only", "--diff-filter=AM", "--", ".github/workflows") == ""
    else:
        template_head = git(template_source, "rev-parse", "HEAD")
        run_copy(
            str(template_source),
            destination,
            data={"project_name": name, "repo_owner": "acme", "description": description},
            defaults=True,
            vcs_ref="HEAD",
            quiet=True,
        )
        validate_project(destination, build_docs=python_version == "3.13")
    metadata = tomllib.loads((destination / "pyproject.toml").read_text())
    assert metadata["project"]["description"] == description
    assert metadata["project"]["version"] == "0.0.0"
    assert metadata["tool"]["coverage"]["report"]["fail_under"] == 80
    answers = yaml.safe_load((destination / ".copier-answers.yml").read_text())
    source = destination if route == "github" else template_source
    assert git(source, "rev-parse", answers["_commit"]) == template_head
    assert answers["_src_path"] == ("." if route == "github" else str(template_source))
    assert (destination / "site/index.html").exists() == (python_version == "3.13" and route == "local")
    assert not (destination / "node_modules").exists()
    assert not (destination / "package.json").exists()
    # Install the built wheel outside the source tree, without editable imports.
    subprocess.run(["uv", "build"], cwd=destination, check=True, timeout=60)
    (wheel,) = (destination / "dist").glob("*.whl")
    installed = tmp_path / "installed"
    subprocess.run(["uv", "venv", "--python", python_version, str(installed)], check=True, timeout=60)
    interpreter = installed / "bin/python"
    subprocess.run(
        ["uv", "pip", "install", "--python", str(interpreter), "--no-deps", str(wheel)],
        check=True,
        timeout=60,
    )
    package = name.replace("-", "_")
    environment = dict(os.environ, APP_LOG_LEVEL="INFO")
    probe = subprocess.run(
        [str(interpreter), "-I", "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert probe.stdout.strip() == python_version
    for command in ([str(installed / "bin" / name)], [str(interpreter), "-I", "-m", package]):
        help_result = subprocess.run(
            [*command, "--help"], cwd=tmp_path, env=environment, check=True, capture_output=True, text=True, timeout=30
        )
        assert name in help_result.stdout
        assert description in help_result.stdout
        assert "--name" in help_result.stdout
        greeting = subprocess.run(
            [*command, "--name", "ölçüm"],
            cwd=tmp_path,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert greeting.stdout == ""
        assert "Hello, ölçüm!" in greeting.stderr
        quiet = subprocess.run(
            command,
            cwd=tmp_path,
            env=dict(environment, APP_LOG_LEVEL=" warning "),
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert quiet.stdout == quiet.stderr == ""
        invalid = subprocess.run(
            [*command, "--unknown-option"],
            cwd=tmp_path,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert invalid.returncode == 2
        assert "unrecognized arguments" in invalid.stderr
