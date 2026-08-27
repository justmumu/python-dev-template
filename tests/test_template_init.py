"""Unit tests for scripts/template_init.py.

These tests exercise the pure-function helpers only. The full flow is covered
by tests/test_template_init_integration.py.
"""

import datetime

import pytest
from scripts.template_init import (
    INITIAL_VERSION,
    _drop_pyproject_template_residue,
    _remove_toml_table,
    derive_names,
    is_binary,
    pin_version_to_initial,
    sanitize_description,
    substitute_in_text,
    validate_owner_name,
    validate_package_name,
)


def test_derive_names_basic():
    owner, project, package = derive_names("acme/billing-service")
    assert owner == "acme"
    assert project == "billing-service"
    assert package == "billing_service"


def test_derive_names_no_hyphen():
    owner, project, package = derive_names("acme/server")
    assert owner == "acme"
    assert project == "server"
    assert package == "server"


def test_derive_names_multi_hyphen():
    _, _, package = derive_names("x/a-b-c-d")
    assert package == "a_b_c_d"


def test_derive_names_rejects_missing_slash():
    with pytest.raises(ValueError, match="GITHUB_REPOSITORY"):
        derive_names("no-slash-here")


def test_validate_package_name_accepts_valid():
    validate_package_name("foo_bar")


def test_validate_package_name_rejects_uppercase():
    with pytest.raises(SystemExit):
        validate_package_name("FooBar")


def test_validate_package_name_rejects_digit_start():
    with pytest.raises(SystemExit):
        validate_package_name("123_mcp")


def test_validate_package_name_rejects_dots():
    with pytest.raises(SystemExit):
        validate_package_name("foo.bar")


def test_validate_package_name_rejects_non_identifier():
    with pytest.raises(SystemExit):
        validate_package_name("foo-bar")  # hyphens should already be gone


def test_validate_owner_name_rejects_leading_hyphen():
    with pytest.raises(SystemExit):
        validate_owner_name("-bad")


def test_substitute_replaces_literal_project_name():
    out = substitute_in_text(
        'name = "python-dev-template"',
        project="foo-mcp",
        package="foo_mcp",
        owner="acme",
    )
    assert out == 'name = "foo-mcp"'


def test_substitute_replaces_literal_package_name():
    out = substitute_in_text(
        "from your_package.config import X",
        project="foo-mcp",
        package="foo_mcp",
        owner="acme",
    )
    assert out == "from foo_mcp.config import X"


def test_substitute_replaces_owner_marker():
    out = substitute_in_text(
        "repo = https://github.com/{{REPO_OWNER}}/foo",
        project="foo-mcp",
        package="foo_mcp",
        owner="acme",
    )
    assert out == "repo = https://github.com/acme/foo"


def test_substitute_replaces_author_marker():
    out = substitute_in_text(
        '{ name = "{{AUTHOR}}" }',
        project="foo-mcp",
        package="foo_mcp",
        owner="acme",
    )
    assert out == '{ name = "acme" }'


def test_substitute_replaces_year_marker_with_explicit_year():
    out = substitute_in_text(
        "Copyright (c) {{YEAR}} foo",
        project="foo-mcp",
        package="foo_mcp",
        owner="acme",
        year="2099",
    )
    assert out == "Copyright (c) 2099 foo"


def test_substitute_replaces_year_marker_with_current_year_by_default():
    expected = str(datetime.datetime.now(tz=datetime.UTC).year)
    out = substitute_in_text(
        "{{YEAR}}",
        project="foo-mcp",
        package="foo_mcp",
        owner="acme",
    )
    assert out == expected


def test_substitute_fills_description_when_provided():
    src = 'description = "{{PROJECT_DESCRIPTION}}"'
    out = substitute_in_text(src, project="foo", package="foo", owner="acme", description="A neat service.")
    assert out == 'description = "A neat service."'


def test_sanitize_description_collapses_and_neutralizes_quotes():
    assert sanitize_description('  A  "neat"\n  service. ') == "A 'neat' service."


def test_substitute_leaves_description_marker_alone():
    src = 'description = "{{PROJECT_DESCRIPTION}}"'
    out = substitute_in_text(src, project="foo-mcp", package="foo_mcp", owner="acme")
    assert out == src


def test_substitute_all_at_once():
    src = "pkg=your_package name=python-dev-template owner={{REPO_OWNER}} auth={{AUTHOR}} d={{PROJECT_DESCRIPTION}}"
    out = substitute_in_text(src, project="foo-mcp", package="foo_mcp", owner="acme")
    assert out == "pkg=foo_mcp name=foo-mcp owner=acme auth=acme d={{PROJECT_DESCRIPTION}}"


def test_is_binary_detects_null_byte(tmp_path):
    p = tmp_path / "bin"
    p.write_bytes(b"hello\x00world")
    assert is_binary(p)


def test_is_binary_on_text_file(tmp_path):
    p = tmp_path / "txt"
    p.write_text("hello world\nsecond line")
    assert not is_binary(p)


def test_is_binary_on_empty_file(tmp_path):
    p = tmp_path / "empty"
    p.write_bytes(b"")
    assert not is_binary(p)


def test_remove_toml_table_drops_target_block():
    src = (
        "[project]\n"
        'name = "foo"\n'
        "\n"
        "[tool.uv.build-backend]\n"
        'module-name = "foo_pkg"\n'
        'module-root = "src"\n'
        "\n"
        "[tool.ruff]\n"
        "line-length = 120\n"
    )
    out = _remove_toml_table(src, header="[tool.uv.build-backend]")
    assert "[tool.uv.build-backend]" not in out
    assert "module-name" not in out
    assert "[project]" in out
    assert "[tool.ruff]" in out
    assert out.count("\n\n\n") == 0


def test_remove_toml_table_at_eof_no_trailing_section():
    src = '[project]\nname = "foo"\n\n[tool.uv.build-backend]\nmodule-name = "foo_pkg"\n'
    out = _remove_toml_table(src, header="[tool.uv.build-backend]")
    assert "[tool.uv.build-backend]" not in out
    assert out.endswith('name = "foo"\n')


def test_remove_toml_table_no_op_when_absent():
    src = '[project]\nname = "foo"\n'
    assert _remove_toml_table(src, header="[tool.uv.build-backend]") == src


def test_drop_pyproject_residue_trims_pythonpath():
    src = '[tool.pytest.ini_options]\npythonpath = ["src", "."]\nasyncio_mode = "auto"\n'
    out = _drop_pyproject_template_residue(src)
    assert 'pythonpath = ["src"]' in out
    assert '"."' not in out


def test_drop_pyproject_residue_removes_extrapaths_line():
    src = (
        "[tool.pyright]\n"
        'pythonVersion = "3.13"\n'
        'include = ["src", "tests", "scripts"]\n'
        'extraPaths = ["."]\n'
        'typeCheckingMode = "strict"\n'
    )
    out = _drop_pyproject_template_residue(src)
    assert "extraPaths" not in out
    assert "include" in out
    assert "typeCheckingMode" in out


def test_drop_pyproject_residue_removes_integration_markers_block():
    src = (
        "[tool.pytest.ini_options]\n"
        'filterwarnings = ["error"]\n'
        "markers = [\n"
        '    "integration: integration tests that copy the template tree and run subprocesses",\n'
        "]\n"
        "\n"
        "[tool.ruff]\n"
    )
    out = _drop_pyproject_template_residue(src)
    assert "markers" not in out
    assert "integration: integration tests" not in out
    assert "[tool.ruff]" in out


def test_drop_pyproject_residue_resets_template_keyword():
    src = '[project]\nkeywords = ["template"]\n'
    out = _drop_pyproject_template_residue(src)
    assert "keywords = []" in out
    assert '"template"' not in out


def test_drop_pyproject_residue_no_op_when_clean():
    src = '[tool.pytest.ini_options]\npythonpath = ["src"]\n'
    assert _drop_pyproject_template_residue(src) == src


def test_drop_pyproject_residue_preserves_user_markers():
    """User-added markers (different content) must survive — we only strip our exact line."""
    src = '[tool.pytest.ini_options]\nmarkers = [\n    "slow: my slow tests",\n]\n'
    out = _drop_pyproject_template_residue(src)
    assert out == src


def test_drop_pyproject_residue_removes_scripts_ignores_block():
    src = (
        "[tool.ruff.lint.per-file-ignores]\n"
        '"tests/*" = ["S101"]\n'
        "# scripts/ are CLI entry points: `print` is the user-facing output mechanism (T201),\n"
        "# and cleanup helpers accept a positional `dry_run: bool` flag by design (FBT001/FBT002).\n"
        '"scripts/*" = [\n'
        '    "INP001",\n'
        '    "T201",\n'
        '    "FBT001",\n'
        '    "FBT002",\n'
        "]\n"
    )
    out = _drop_pyproject_template_residue(src)
    assert '"scripts/*"' not in out
    assert "FBT001" not in out
    assert "cleanup helpers" not in out
    assert '"tests/*"' in out


def test_drop_pyproject_residue_preserves_user_scripts_ignores():
    """User-customized scripts/* ignores (no template comment) must survive."""
    src = '[tool.ruff.lint.per-file-ignores]\n"scripts/*" = [\n    "T201",\n]\n'
    out = _drop_pyproject_template_residue(src)
    assert out == src


def test_drop_pyproject_residue_handles_prettier_collapsed_markers():
    """Prettier collapses short arrays to a single line — regex must still match."""
    src = (
        "[tool.pytest.ini_options]\n"
        'markers = ["integration: integration tests that copy the template tree and run subprocesses"]\n'
        "\n"
        "[tool.ruff]\n"
    )
    out = _drop_pyproject_template_residue(src)
    assert "markers" not in out
    assert "integration: integration tests" not in out
    assert "[tool.ruff]" in out


def test_drop_pyproject_residue_handles_prettier_collapsed_scripts_ignores():
    """Prettier collapses the scripts/* array to a single line — regex must still match."""
    src = (
        "[tool.ruff.lint.per-file-ignores]\n"
        '"tests/*" = ["S101"]\n'
        "# scripts/ are CLI entry points: `print` is the user-facing output mechanism (T201),\n"
        "# and cleanup helpers accept a positional `dry_run: bool` flag by design (FBT001/FBT002).\n"
        '"scripts/*" = ["INP001", "T201", "FBT001", "FBT002"]\n'
    )
    out = _drop_pyproject_template_residue(src)
    assert '"scripts/*"' not in out
    assert "FBT001" not in out
    assert "cleanup helpers" not in out
    assert '"tests/*"' in out


def test_pin_version_to_initial_rewrites_non_initial_version(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "foo"\nversion = "1.4.7"\nrequires-python = ">=3.13"\n',
        encoding="utf-8",
    )
    pin_version_to_initial(tmp_path)
    text = pyproject.read_text(encoding="utf-8")
    assert 'version = "0.0.0"' in text
    assert 'version = "1.4.7"' not in text


def test_pin_version_to_initial_no_op_when_already_initial(tmp_path):
    src = '[project]\nname = "foo"\nversion = "0.0.0"\n'
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(src, encoding="utf-8")
    pin_version_to_initial(tmp_path)
    assert pyproject.read_text(encoding="utf-8") == src


def test_pin_version_to_initial_only_touches_first_version_line(tmp_path):
    """The regex must hit only the [project] version, not e.g. a `version` key inside a string."""
    src = '[project]\nname = "foo"\nversion = "2.0.0"\n[tool.something]\ndescription = "see also: version = \\"x\\""\n'
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(src, encoding="utf-8")
    pin_version_to_initial(tmp_path)
    text = pyproject.read_text(encoding="utf-8")
    assert 'version = "0.0.0"' in text
    assert 'version = "2.0.0"' not in text


def test_initial_version_constant_is_semver_initial():
    assert INITIAL_VERSION == "0.0.0"
