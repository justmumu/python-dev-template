"""Smoke tests for the CLI entrypoint module.

Covers the level-resolution branch in ``_setup_logging``, the argument parser,
the ``main`` body, and the trivial ``cli()`` wrapper so coverage reflects that
the module loads and runs cleanly on a fresh install.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

import your_package.__main__ as main_mod


def test_setup_logging_resolves_named_level(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_basic_config(**kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr("your_package.__main__.logging.basicConfig", fake_basic_config)
    main_mod._setup_logging("DEBUG")
    assert captured["level"] == logging.DEBUG


def test_setup_logging_falls_back_on_unknown_level(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_basic_config(**kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr("your_package.__main__.logging.basicConfig", fake_basic_config)
    main_mod._setup_logging("NOT_A_LEVEL")
    assert captured["level"] == logging.INFO


def test_build_parser_default_name() -> None:
    args = main_mod.build_parser().parse_args([])
    assert args.name == "world"


def test_main_returns_zero(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="your_package.__main__"):
        code = main_mod.main(["--name", "tester"])
    assert code == 0
    assert "tester" in caplog.text


def test_cli_exits_with_main_return_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_mod, "main", lambda: 3)
    with pytest.raises(SystemExit) as excinfo:
        main_mod.cli()
    assert excinfo.value.code == 3
