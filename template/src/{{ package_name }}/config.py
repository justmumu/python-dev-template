"""Application configuration loaded from environment variables."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True)
class AppConfig:
    """Runtime configuration. Loaded once at startup from env."""

    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Self:
        """Build a config from a dict-like env mapping (typically os.environ).

        Recognized variables:
            APP_LOG_LEVEL: standard Python log level name, defaults to ``INFO``.
        """
        log_level = env.get("APP_LOG_LEVEL", "INFO").strip().upper()
        return cls(log_level=log_level)
