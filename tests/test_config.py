"""Tests for AppConfig.from_env."""

from dataclasses import FrozenInstanceError

from your_package.config import AppConfig


def test_defaults_when_env_empty():
    cfg = AppConfig.from_env({})
    assert cfg.log_level == "INFO"


def test_log_level_from_env_is_upper_stripped():
    cfg = AppConfig.from_env({"APP_LOG_LEVEL": "  debug  "})
    assert cfg.log_level == "DEBUG"


def test_app_config_is_frozen():
    cfg = AppConfig.from_env({})
    try:
        cfg.log_level = "DEBUG"  # type: ignore[misc]
    except FrozenInstanceError:
        return
    raise AssertionError("AppConfig should be frozen")
