"""Run text formatters on Git-visible project files with literal path arguments."""

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUFFIXES = {"md": {".md"}, "toml": {".toml"}, "yaml": {".yml", ".yaml"}, "json": {".json"}}


def project_files(kind: str) -> list[str]:
    """Find existing files without traversing ignored caches or template sources."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    paths = {Path(name.decode()) for name in result.stdout.split(b"\0") if name}
    return [
        f"./{path.as_posix()}"
        for path in sorted(paths)
        if path.parts[0] != "template"
        and path.suffix in SUFFIXES[kind]
        and path.name != "uv.lock"
        and (ROOT / path).is_file()
        and not (ROOT / path).is_symlink()
    ]


def format_files(kind: str, *, check: bool) -> int:
    """Delegate formatting and validation to the installed tools."""
    paths = project_files(kind)
    if not paths:
        return 0
    commands = {
        "md": ["mdformat"],
        "toml": ["taplo", "fmt"],
        "yaml": ["yamlfix"],
        "json": ["pretty-format-json", "--indent", "2", "--no-sort-keys", "--no-ensure-ascii"],
    }
    command = commands[kind]
    options = ["--check"] if check else []
    if kind == "json":
        options = [] if check else ["--autofix"]
    result = subprocess.run([*command, *options, *paths], cwd=ROOT, check=False)
    # The JSON CLI returns 1 both for a successful rewrite and invalid input.
    if kind == "json" and not check and result.returncode:
        return subprocess.run([*command, *paths], cwd=ROOT, check=False).returncode
    return result.returncode


def main() -> int:
    """Parse the Make recipe's formatter kind and optional check mode."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=SUFFIXES)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    return format_files(arguments.kind, check=arguments.check)


if __name__ == "__main__":
    raise SystemExit(main())
