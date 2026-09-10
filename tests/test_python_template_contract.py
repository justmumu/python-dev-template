import tomllib
from pathlib import Path

from copier import run_copy


def test_copier_creates_a_general_python_application(template_source, tmp_path):
    source = Path(__file__).resolve().parents[1]
    assert (source / "copier.yml").is_file(), "The Python template must expose its Copier generator"
    destination = tmp_path / "server"
    run_copy(
        str(template_source),
        str(destination),
        data={"project_name": "server", "repo_owner": "acme"},
        defaults=True,
        vcs_ref="HEAD",
    )
    metadata = tomllib.loads((destination / "pyproject.toml").read_text())
    assert metadata["project"]["name"] == "server"
    assert metadata["project"]["version"] == "0.0.0"
    assert metadata["project"]["dependencies"] == []
    assert metadata["project"]["scripts"] == {"server": "server.__main__:cli"}
    assert "APP_LOG_LEVEL" in (destination / "src/server/config.py").read_text()
    assert not (destination / "src/server/tools").exists()
