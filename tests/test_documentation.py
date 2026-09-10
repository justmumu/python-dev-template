"""Exercise the published documentation and its strict local-link gate."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(
    sys.version_info[:2] != (3, 13), reason="Documentation builds are validated on Python 3.13"
)


@pytest.fixture
def documentation_project(tmp_path):
    shutil.copy2(ROOT / "mkdocs.yml", tmp_path / "mkdocs.yml")
    shutil.copytree(ROOT / "docs", tmp_path / "docs")
    if (ROOT / "src").exists():
        shutil.copytree(ROOT / "src", tmp_path / "src")
    return tmp_path


def build_documentation(project):
    return subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--strict"],
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )


def test_documentation_builds_strictly(documentation_project):
    result = build_documentation(documentation_project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (documentation_project / "site" / "index.html").is_file()


@pytest.mark.parametrize("target", ["missing-guide.md", "index.md#missing-anchor"])
def test_documentation_rejects_broken_internal_links(documentation_project, target):
    index = documentation_project / "docs" / "index.md"
    index.write_text(index.read_text() + f"\n[Broken link]({target})\n")
    result = build_documentation(documentation_project)
    assert result.returncode != 0, result.stdout + result.stderr
    assert target in result.stdout + result.stderr
