"""Template cleanup script.

Runs once on a freshly-created repo from the python-dev-template. The
pipeline:

* Substitutes placeholders across every git-tracked text file
  (``python-dev-template`` → project, ``your_package`` → package,
  ``{{REPO_OWNER}}`` and ``{{AUTHOR}}`` → owner,
  ``{{YEAR}}`` → current UTC year, and ``{{PROJECT_DESCRIPTION}}`` → the GitHub
  repo description when one was set at create time).
* Renames ``src/your_package/`` → ``src/<package>/`` via ``git mv``.
* Strips the ``[tool.uv.build-backend]`` table from ``pyproject.toml`` (only
  needed in the template state to bridge the placeholder package dir).
* Cleans template-only ``pyproject.toml`` residue (``pythonpath`` ``"."``
  entry, ``[tool.pyright]`` ``extraPaths``, the ``integration`` pytest marker,
  the ``"scripts/*"`` ruff per-file-ignores block, and the ``template`` keyword).
* Pins ``pyproject.toml`` ``version`` back to ``"0.1.0"`` so every downstream
  repo starts fresh, regardless of where the template's own version has bumped.
* Deletes the template repo's own ``CHANGELOG.md`` (if present) — downstream
  history starts empty and the first ``make bump-*`` regenerates it.
* Generates ``uv.lock`` so the new repo ships a committed lockfile.
* Overwrites ``README.md`` with a generic project stub.
* Writes ``POST_SETUP.md`` with the remaining manual TODOs.
* Deletes itself, the cleanup workflow, the template-ci workflow, the
  sentinel file, and the template-only tests so the final commit ships a
  clean repo.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

TEMPLATE_PROJECT_NAME = "python-dev-template"
TEMPLATE_PACKAGE_NAME = "your_package"

SUBSTITUTION_SKIP = frozenset({"uv.lock", "CHANGELOG.md"})

_PACKAGE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_OWNER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")

README_STUB = """# {project}

{description}

## Development

```bash
make setup       # install deps + git hooks
make check       # lock-check + format-check + lint + typecheck + test
make docs-serve  # live docs at http://127.0.0.1:8000
```

See `POST_SETUP.md` for the remaining setup checklist.
"""


def build_post_setup(*, package: str, description_missing: bool) -> str:
    """Build the POST_SETUP.md content; items vary with what automation could fill."""
    items: list[str] = []
    if description_missing:
        items.append(
            "- [ ] Fill in the project description — the repo had no description at create time, so the "
            f"`{{{{PROJECT_DESCRIPTION}}}}` placeholder is still in: `pyproject.toml`, `mkdocs.yml`, "
            f"`docs/index.md`, `README.md`, `src/{package}/__main__.py`"
        )
    items += [
        "- [ ] Version starts at `0.0.0` (nothing released yet); when you have something to ship, "
        "`make bump-minor` creates `v0.1.0` and generates `CHANGELOG.md`",
        "- [ ] `mkdocs.yml` → set `site_url` if you deploy the docs anywhere; expand `nav` as you add pages",
        "- [ ] GH repo settings → add topics (`python`)",
        "- [ ] GH repo settings → enable **Discussions** (Settings → Features) — the issue-template contact link points there",
        "- [ ] (If public) branch protection on `main`: disable direct push, disable squash-merge",
        "- [ ] **First CI run happens on your next manual push**, not on this setup commit "
        "(GITHUB_TOKEN pushes don't trigger downstream workflows)",
        f"- [ ] Replace the demo CLI flag in `src/{package}/__main__.py` with real behavior",
        "- [ ] Delete this file (`POST_SETUP.md`)",
    ]
    header = "# Post-setup TODO\n\nAutomated template setup complete. Still to do manually:\n\n"
    footer = (
        "\nSetup tooling used (all now deleted): `scripts/template_init.py`, `scripts/__init__.py`, "
        "`.github/workflows/template-cleanup.yml`, `.github/workflows/template-ci.yml`, "
        "`tests/test_template_init.py`, `tests/test_template_init_integration.py`, `.github/.template-pending`.\n"
    )
    return header + "\n".join(items) + "\n" + footer


MACHINERY_TO_DELETE = [
    ".github/workflows/template-cleanup.yml",
    ".github/workflows/template-ci.yml",
    ".github/.template-pending",
    "scripts/template_init.py",
    "scripts/__init__.py",
    "tests/test_template_init.py",
    "tests/test_template_init_integration.py",
]


def derive_names(github_repository: str) -> tuple[str, str, str]:
    """Split ``owner/project`` and derive the Python package name.

    Args:
        github_repository: Value of the ``GITHUB_REPOSITORY`` env var, e.g. ``acme/foo-bar``.

    Returns:
        ``(owner, project, package)`` where ``package`` is ``project`` with hyphens
        replaced by underscores.

    Raises:
        ValueError: If ``github_repository`` does not contain a slash.
    """
    if "/" not in github_repository:
        raise ValueError(f"GITHUB_REPOSITORY must be 'owner/repo', got: {github_repository!r}")
    owner, project = github_repository.split("/", 1)
    package = project.replace("-", "_")
    return owner, project, package


def validate_package_name(package: str) -> None:
    """Exit with a clear error if ``package`` is not a valid Python identifier in lowercase snake_case."""
    if not package.isidentifier():
        sys.exit(f"ERROR: derived package '{package}' is not a valid Python identifier")
    if not _PACKAGE_NAME_RE.match(package):
        sys.exit(f"ERROR: package must be lowercase snake_case: got '{package}'")


def validate_owner_name(owner: str) -> None:
    """Exit if ``owner`` doesn't look like a valid GitHub username/org."""
    if not _OWNER_NAME_RE.match(owner):
        sys.exit(f"ERROR: owner '{owner}' does not look like a valid GitHub owner name")


def sanitize_description(raw: str) -> str:
    """Collapse whitespace and neutralize double quotes.

    The description is injected verbatim into TOML strings, a Python string
    literal, YAML and Markdown — single-line, double-quote-free text is the
    common denominator that is safe in all of them.
    """
    return " ".join(raw.split()).replace('"', "'")


def _current_year() -> str:
    """Return the current UTC year as a 4-digit string. Wrapped for test injection."""
    return str(datetime.datetime.now(tz=datetime.UTC).year)


def substitute_in_text(
    text: str,
    *,
    project: str,
    package: str,
    owner: str,
    year: str | None = None,
    description: str | None = None,
) -> str:
    """Apply all template substitutions to a text blob.

    Replaces (in order):
        - literal ``python-dev-template`` → ``project``
        - literal ``your_package`` → ``package``
        - ``{{REPO_OWNER}}`` → ``owner``
        - ``{{AUTHOR}}`` → ``owner``
        - ``{{YEAR}}`` → ``year`` (defaults to current UTC year)
        - ``{{PROJECT_DESCRIPTION}}`` → ``description`` (only when provided;
          otherwise the marker stays and POST_SETUP.md tells the user to fill it)
    """
    resolved_year = year if year is not None else _current_year()
    out = (
        text.replace(TEMPLATE_PROJECT_NAME, project)
        .replace(TEMPLATE_PACKAGE_NAME, package)
        .replace("{{REPO_OWNER}}", owner)
        .replace("{{AUTHOR}}", owner)
        .replace("{{YEAR}}", resolved_year)
    )
    if description:
        out = out.replace("{{PROJECT_DESCRIPTION}}", description)
    return out


def is_binary(path: Path) -> bool:
    """Return True if ``path`` appears to be a binary file.

    Heuristic: the first 8 KB contains a null byte. Cheap, good enough for the
    template's universe (code, markdown, YAML, TOML, plus occasional images).
    """
    try:
        chunk = path.read_bytes()[:8192]
    except OSError:
        return True
    return b"\x00" in chunk


def _run(cmd: list[str], *, cwd: Path, dry_run: bool) -> None:
    """Run ``cmd`` in ``cwd`` unless ``dry_run`` is set; always log."""
    print(f"+ {' '.join(cmd)}" + ("   [dry-run]" if dry_run else ""))
    if not dry_run:
        subprocess.run(cmd, cwd=cwd, check=True)


def _tracked_files(repo: Path) -> list[Path]:
    """Return the list of git-tracked files relative to ``repo``."""
    out = subprocess.run(
        ["git", "ls-files"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    return [repo / line for line in out if line]


def apply_substitutions(
    repo: Path, *, project: str, package: str, owner: str, description: str | None = None, dry_run: bool = False
) -> None:
    """Rewrite every non-binary tracked file in ``repo`` with substitutions applied.

    Files listed in :data:`SUBSTITUTION_SKIP` are skipped (e.g. ``uv.lock`` is
    regenerated later in the pipeline).
    """
    for path in _tracked_files(repo):
        rel = path.relative_to(repo).as_posix()
        if rel in SUBSTITUTION_SKIP:
            continue
        if not path.is_file() or is_binary(path):
            continue
        original = path.read_text(encoding="utf-8")
        rewritten = substitute_in_text(original, project=project, package=package, owner=owner, description=description)
        if rewritten != original:
            print(f"  rewrite: {path.relative_to(repo)}")
            if not dry_run:
                path.write_text(rewritten, encoding="utf-8")


def rename_package_dir(repo: Path, *, package: str, dry_run: bool = False) -> None:
    """git-mv src/your_package → src/<package> if the source dir is present."""
    src = repo / "src" / TEMPLATE_PACKAGE_NAME
    if not src.exists():
        print(f"  (skip rename: {src.relative_to(repo)} not found)")
        return
    _run(["git", "mv", str(src.relative_to(repo)), f"src/{package}"], cwd=repo, dry_run=dry_run)


INITIAL_VERSION = "0.0.0"

_VERSION_LINE_RE = re.compile(r'^version = "[^"]*"$', re.MULTILINE)


def pin_version_to_initial(repo: Path, dry_run: bool = False) -> None:
    """Reset ``pyproject.toml`` ``version`` to ``"0.0.0"``.

    The template repo can bump its own version freely; downstream repos start
    at ``0.0.0`` ("nothing released yet") so the first ``make bump-minor`` they
    run produces a real ``v0.1.0`` first release with a fresh ``CHANGELOG.md``.
    """
    pyproject = repo / "pyproject.toml"
    if not pyproject.exists():
        print("  (skip pin: pyproject.toml not found)")
        return
    text = pyproject.read_text(encoding="utf-8")
    new = _VERSION_LINE_RE.sub(f'version = "{INITIAL_VERSION}"', text, count=1)
    if new == text:
        print("  (skip pin: version already 0.0.0 or no version line)")
        return
    print(f'  rewrite: pyproject.toml (pin version = "{INITIAL_VERSION}")')
    if not dry_run:
        pyproject.write_text(new, encoding="utf-8")


def clean_pyproject_template_residue(repo: Path, dry_run: bool = False) -> None:
    """Strip pyproject.toml entries that exist only to support template-internal tests.

    After ``MACHINERY_TO_DELETE`` removes ``tests/test_template_init*.py`` and
    ``scripts/template_init.py``, four knobs become orphaned:

    * ``pythonpath = ["src", "."]`` — the trailing ``"."`` only existed so the
      template's own tests could ``from scripts.template_init import …``. Reduced
      to ``["src"]``.
    * ``extraPaths = ["."]`` under ``[tool.pyright]`` — same reason; removed.
    * The ``integration`` pytest marker — registered solely for the deleted
      integration test. The whole ``markers = [...]`` block is removed when its
      sole entry is the template's own marker; downstream adds its own as needed.
    * The ``"scripts/*"`` ruff per-file-ignores block — its rationale comment
      explicitly references ``template_init.py``'s ``dry_run: bool`` flag and
      ``print`` calls. Once that script is gone, the block is misleading
      template residue; downstream re-adds ignores for its own scripts as needed.
    * ``keywords = ["template"]`` — describes the template repo, not the
      downstream project. Reset to ``[]``; downstream fills in its own.

    Each edit anchors on stable text (header comment + key name), tolerating both
    multi-line and single-line-collapsed array styles. User-customized values are left alone.
    """
    pyproject = repo / "pyproject.toml"
    if not pyproject.exists():
        print("  (skip clean: pyproject.toml not found)")
        return
    text = pyproject.read_text(encoding="utf-8")
    new = _drop_pyproject_template_residue(text)
    if new == text:
        print("  (skip clean: no template residue in pyproject.toml)")
        return
    print("  rewrite: pyproject.toml (clean template residue)")
    if not dry_run:
        pyproject.write_text(new, encoding="utf-8")


_PYRIGHT_EXTRAPATHS_LINE_RE = re.compile(r'\nextraPaths = \["\."\]\n')

# Match the integration-marker block in either form:
#   markers = [\n    "integration: ...",\n]\n   (hand-formatted)
#   markers = ["integration: ..."]\n             (single-line-collapsed)
_INTEGRATION_MARKERS_BLOCK_RE = re.compile(
    r'markers\s*=\s*\[\s*"integration: integration tests that copy the template tree and run subprocesses",?\s*\]\n',
)

# Match the scripts/* ignores block (header comment + array) in either form,
# anchored on the unique header comment so a user-customized array body still
# matches as long as the comment survived. The array body is consumed greedily
# up to the closing bracket.
_SCRIPTS_IGNORES_BLOCK_RE = re.compile(
    r"# scripts/ are CLI entry points: `print` is the user-facing output mechanism \(T201\),\n"
    r"# and cleanup helpers accept a positional `dry_run: bool` flag by design \(FBT001/FBT002\)\.\n"
    r'"scripts/\*"\s*=\s*\[[^\]]*\]\n',
)


def _drop_pyproject_template_residue(text: str) -> str:
    """Return ``text`` with the five known template-only knobs stripped."""
    new = text.replace('pythonpath = ["src", "."]', 'pythonpath = ["src"]')
    new = new.replace('keywords = ["template"]', "keywords = []")
    new = _PYRIGHT_EXTRAPATHS_LINE_RE.sub("\n", new)
    new = _INTEGRATION_MARKERS_BLOCK_RE.sub("", new)
    return _SCRIPTS_IGNORES_BLOCK_RE.sub("", new)


def strip_uv_build_backend_block(repo: Path, dry_run: bool = False) -> None:
    """Drop the ``[tool.uv.build-backend]`` table from ``pyproject.toml``.

    The block exists in the template only to bridge the mismatch between the
    placeholder package dir (``src/your_package/``) and the template's project
    name. Once substitution + rename have run, ``name`` aligns with the package
    dir and uv's default module discovery works — the explicit block becomes
    redundant noise in the downstream repo, so we strip it.
    """
    pyproject = repo / "pyproject.toml"
    if not pyproject.exists():
        print("  (skip strip: pyproject.toml not found)")
        return
    text = pyproject.read_text(encoding="utf-8")
    new_text = _remove_toml_table(text, header="[tool.uv.build-backend]")
    if new_text == text:
        print("  (skip strip: [tool.uv.build-backend] not present)")
        return
    print("  rewrite: pyproject.toml (strip [tool.uv.build-backend])")
    if not dry_run:
        pyproject.write_text(new_text, encoding="utf-8")


def _remove_toml_table(text: str, *, header: str) -> str:
    """Return ``text`` with the TOML table starting at ``header`` removed.

    Strips the header line, all key=value lines beneath it, and one trailing
    blank line if present, so we don't leave a double-blank gap.
    """
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    skipping = False
    for line in lines:
        stripped = line.lstrip()
        if not skipping and stripped.startswith(header):
            skipping = True
            while out and out[-1].strip() == "":
                out.pop()
            continue
        if skipping:
            if stripped.startswith("["):
                skipping = False
                if out and not out[-1].endswith("\n\n"):
                    out.append("\n")
                out.append(line)
                continue
            continue
        out.append(line)
    return "".join(out)


def delete_template_changelog(repo: Path, dry_run: bool = False) -> None:
    """git-rm the template repo's own CHANGELOG.md so downstream starts fresh.

    The version is pinned back to 0.1.0; keeping the template's release history
    would contradict that. The first ``make bump-*`` downstream regenerates it.
    """
    path = repo / "CHANGELOG.md"
    if not path.exists():
        print("  (skip changelog: CHANGELOG.md not present)")
        return
    _run(["git", "rm", "-f", "CHANGELOG.md"], cwd=repo, dry_run=dry_run)


def generate_lockfile(repo: Path, dry_run: bool = False) -> None:
    """Run `uv lock` in ``repo`` so the new repo ships a committed lockfile."""
    _run(["uv", "lock"], cwd=repo, dry_run=dry_run)


def write_readme_stub(repo: Path, *, project: str, description: str, dry_run: bool = False) -> None:
    """Overwrite README.md with a project-specific stub.

    Runs after substitution so the stub contents don't get re-substituted.
    """
    content = README_STUB.format(project=project, description=description or "{{PROJECT_DESCRIPTION}}")
    target = repo / "README.md"
    print("  write: README.md (stub)")
    if not dry_run:
        target.write_text(content, encoding="utf-8")


def write_post_setup(repo: Path, *, package: str, description_missing: bool, dry_run: bool = False) -> None:
    """Create POST_SETUP.md in ``repo`` with instructions for the user."""
    content = build_post_setup(package=package, description_missing=description_missing)
    target = repo / "POST_SETUP.md"
    print("  write: POST_SETUP.md")
    if not dry_run:
        target.write_text(content, encoding="utf-8")


def delete_machinery(repo: Path, dry_run: bool = False) -> None:
    """git-rm the cleanup machinery so the final commit ships a clean repo."""
    for rel in MACHINERY_TO_DELETE:
        path = repo / rel
        if path.exists():
            _run(["git", "rm", "-f", rel], cwd=repo, dry_run=dry_run)
        else:
            print(f"  (skip rm: {rel} not found)")


def main(argv: list[str] | None = None) -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Run template cleanup on the current repo.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without modifying anything.")
    parser.add_argument("--repo", default=".", help="Repo root (default: cwd).")
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    github_repository = os.environ.get("GITHUB_REPOSITORY")
    if not github_repository:
        sys.exit("ERROR: GITHUB_REPOSITORY env var is required")

    owner, project, package = derive_names(github_repository)
    validate_package_name(package)
    validate_owner_name(owner)
    description = sanitize_description(os.environ.get("REPO_DESCRIPTION", ""))

    print(f"Applying template cleanup in {repo}")
    print(f"  owner={owner}  project={project}  package={package}")
    print(f"  description={description!r}" if description else "  description=(empty — left as TODO)")

    apply_substitutions(
        repo, project=project, package=package, owner=owner, description=description, dry_run=args.dry_run
    )
    rename_package_dir(repo, package=package, dry_run=args.dry_run)
    strip_uv_build_backend_block(repo, dry_run=args.dry_run)
    clean_pyproject_template_residue(repo, dry_run=args.dry_run)
    pin_version_to_initial(repo, dry_run=args.dry_run)
    delete_template_changelog(repo, dry_run=args.dry_run)
    generate_lockfile(repo, dry_run=args.dry_run)
    write_readme_stub(repo, project=project, description=description, dry_run=args.dry_run)
    write_post_setup(repo, package=package, description_missing=not description, dry_run=args.dry_run)
    delete_machinery(repo, dry_run=args.dry_run)

    print("Cleanup complete.")


if __name__ == "__main__":
    main()
