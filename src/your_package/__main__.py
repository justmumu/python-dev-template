"""Entrypoint for `python -m your_package`."""

import argparse
import logging
import os
import sys
from typing import NoReturn

from .config import AppConfig

logger = logging.getLogger(__name__)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=logging.getLevelNamesMapping().get(level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser. Replace the demo flags with real ones."""
    parser = argparse.ArgumentParser(prog="python-dev-template", description="{{PROJECT_DESCRIPTION}}")
    parser.add_argument("--name", default="world", help="Name to greet (demo flag, replace me).")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code."""
    config = AppConfig.from_env(os.environ)
    _setup_logging(config.log_level)

    args = build_parser().parse_args(argv)
    logger.info("Hello, %s!", args.name)
    return 0


def cli() -> NoReturn:
    """Sync entrypoint for the ``python-dev-template`` console script."""
    sys.exit(main())


if __name__ == "__main__":
    cli()
