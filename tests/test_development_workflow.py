"""Exercise Make entrypoints and the real formatter hook on disposable projects."""

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_commit_message_hook_works_without_global_python(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    shutil.copyfile(ROOT / ".pre-commit-config.yaml", project / ".pre-commit-config.yaml")
    (project / "scripts/hooks").mkdir(parents=True)
    shutil.copyfile(
        ROOT / "scripts/hooks/check_conventional_commit.py", project / "scripts/hooks/check_conventional_commit.py"
    )
    (project / "pyproject.toml").write_text('[project]\nname = "hook-test"\nversion = "0.0.0"\n')
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for name in ("uv", "git", "bash", "dirname"):
        executable = shutil.which(name)
        assert executable is not None, f"Required test executable: {name}"
        (binaries / name).symlink_to(executable)
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith(("GIT_", "UV_")) and key != "VIRTUAL_ENV"
    }
    environment.update(PATH=str(binaries), UV_PYTHON=sys.executable)
    assert shutil.which("python", path=environment["PATH"]) is None
    subprocess.run(["git", "init", "-q"], cwd=project, env=environment, check=True)
    subprocess.run(["git", "add", "."], cwd=project, env=environment, check=True)
    subprocess.run(
        [sys.executable, "-m", "pre_commit", "install", "--hook-type", "commit-msg"],
        cwd=project,
        env=environment,
        check=True,
    )
    for message, accepted in (("chore: initialize project", True), ("invalid message", False)):
        result = subprocess.run(
            [
                "git",
                "-c",
                "user.name=Hook Test",
                "-c",
                "user.email=hook-test@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--allow-empty",
                "-m",
                message,
            ],
            cwd=project,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert (result.returncode == 0) is accepted, result.stdout + result.stderr
        assert "Conventional Commits (project rules)" in result.stdout + result.stderr
        if not accepted:
            assert "error: subject does not match Conventional Commits" in result.stdout + result.stderr


@pytest.fixture
def make_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    shutil.copyfile(ROOT / "Makefile", project / "Makefile")
    (project / "scripts").mkdir()
    shutil.copyfile(ROOT / "scripts/development.mk", project / "scripts/development.mk")
    (project / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')
    binary = tmp_path / "bin"
    binary.mkdir()
    # Capture tool arguments, but delegate the formatter runner to real tools.
    uv = binary / "uv"
    uv.write_text(
        f"#!{sys.executable}\nimport json, os, sys\n"
        "if sys.argv[1:5] == ['run', '--group', 'dev', 'python']:\n"
        "    os.execv(sys.executable, [sys.executable, *sys.argv[5:]])\n"
        "print(json.dumps(sys.argv[1:]))\n"
    )
    uv.chmod(0o755)
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    # A parent `make test-one TEST=…` must not override this fixture's selector.
    for name in ("MAKEFLAGS", "MAKEOVERRIDES", "MFLAGS", "MAKELEVEL"):
        environment.pop(name, None)
    environment["PATH"] = os.pathsep.join((str(binary), str(Path(sys.executable).parent), environment["PATH"]))
    environment.pop("CODEX_TEST_BINARY", None)
    environment.pop("TEST", None)
    return project, environment


@pytest.mark.parametrize("existing_lock", [False, True])
def test_install_initializes_only_a_missing_lock(make_project, existing_lock):
    project, environment = make_project
    if existing_lock:
        (project / "uv.lock").write_text("fixture\n")
    result = subprocess.run(
        ["make", "-s", "install"], cwd=project, env=environment, text=True, capture_output=True, check=True
    )
    calls = [json.loads(line) for line in result.stdout.splitlines()]
    assert calls == ([] if existing_lock else [["lock"]]) + [["sync", "--locked", "--group", "dev", "--group", "docs"]]


@pytest.mark.parametrize("selection_source", ["environment", "argument"])
@pytest.mark.parametrize(
    "selector",
    [
        "tests/test_example.py",
        "tests/test_example.py::test_case[with space]",
        "tests/test_example.py;touch injected",
        "tests/test_example.py::test_case[$(shell touch injected)]",
    ],
)
def test_selected_test_is_one_literal_argument(make_project, selector, selection_source):
    project, environment = make_project
    arguments = ["make", "-s", "test-one"]
    if selection_source == "environment":
        environment["TEST"] = selector
    else:
        arguments.append(f"TEST={selector}")
    result = subprocess.run(arguments, cwd=project, env=environment, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == ["run", "--group", "dev", "--group", "docs", "pytest", selector, "-v"]
    assert not (project / "injected").exists()


@pytest.mark.parametrize(
    "selector", ["", "--override-ini=addopts=", "/outside/unrelated.py", "tests/../../unrelated.py"]
)
def test_selected_test_rejects_missing_or_option_input(make_project, selector):
    project, environment = make_project
    environment["TEST"] = selector
    result = subprocess.run(
        ["make", "-s", "test-one"], cwd=project, env=environment, capture_output=True, text=True, check=False
    )
    assert result.returncode != 0
    assert "TEST=tests/" in result.stderr
    assert result.stdout == ""


@pytest.mark.skipif(not (ROOT / "copier.yml").exists(), reason="generator-only integration suite")
def test_integration_target_runs_the_complete_suite(make_project):
    project, environment = make_project
    result = subprocess.run(
        ["make", "-s", "test-integration"], cwd=project, env=environment, capture_output=True, text=True, check=True
    )
    assert json.loads(result.stdout) == [
        "run",
        "--locked",
        "--group",
        "dev",
        "--group",
        "docs",
        "pytest",
        "-v",
        "-m",
        "integration",
    ]


def test_permission_target_requires_an_actual_codex_binary(make_project):
    project, environment = make_project
    result = subprocess.run(
        ["make", "-s", "test-permissions"], cwd=project, env=environment, capture_output=True, text=True, check=False
    )
    assert result.returncode != 0
    assert "CODEX_TEST_BINARY" in result.stderr


@pytest.mark.parametrize(
    ("filename", "content"), [("README.md", "# Heading\n\nhello    \n"), ("settings.yml", 'answer:   "yes"\n')]
)
def test_non_python_change_runs_format_hook_and_preserves_metadata_values(make_project, filename, content):
    project, environment = make_project
    for name in (".pre-commit-config.yaml", ".mdformat.toml", ".taplo.toml", ".gitignore"):
        shutil.copyfile(ROOT / name, project / name)
    shutil.copyfile(ROOT / "scripts/format_files.py", project / "scripts/format_files.py")
    # Trusted formatting may rewrite whitespace in metadata, never its values.
    metadata = project / "pyproject.toml"
    metadata.write_text('[project]\nversion="0.1.0"\n[tool.ruff.lint]\nselect=["F","E"]\n')
    expected = tomllib.loads(metadata.read_text())
    (project / filename).write_text(content)
    subprocess.run(["git", "init", "-q"], cwd=project, env=environment, check=True)
    subprocess.run(["git", "add", filename, "pyproject.toml"], cwd=project, env=environment, check=True)
    result = subprocess.run(
        [sys.executable, "-m", "pre_commit", "run", "format", "--files", filename],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert "files were modified by this hook" in result.stdout, result.stdout + result.stderr
    assert (project / filename).read_text() != content
    assert 'version = "0.1.0"' in metadata.read_text()
    assert tomllib.loads(metadata.read_text()) == expected


def test_formatter_handles_spaces_and_skips_private_files(make_project):
    project, environment = make_project
    shutil.copyfile(ROOT / "scripts/format_files.py", project / "scripts/format_files.py")
    shutil.copyfile(ROOT / ".gitignore", project / ".gitignore")
    shutil.copyfile(ROOT / ".mdformat.toml", project / ".mdformat.toml")
    (project / "space name.md").write_text("# Heading\n\nhello    \n")
    (project / ".superpowers").mkdir()
    private = project / ".superpowers/private.md"
    private.write_text("# private    \n")
    subprocess.run(["git", "init", "-q"], cwd=project, env=environment, check=True)
    check = subprocess.run(
        ["make", "-s", "format-md-check"], cwd=project, env=environment, capture_output=True, check=False
    )
    assert check.returncode != 0
    assert (project / "space name.md").read_text().endswith("hello    \n")
    subprocess.run(["make", "-s", "format-md"], cwd=project, env=environment, check=True)
    assert (project / "space name.md").read_text().endswith("hello\n")
    assert private.read_text() == "# private    \n"
