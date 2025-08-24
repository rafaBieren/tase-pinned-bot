"""
settings.py
------------
Centralized configuration loader for environment variables.

This module:
- Loads environment variables from a local `.env` file (if present).
- Exposes a typed `Settings` dataclass, with defaults for development.
- Provides a helper to parse the indices mapping string into a dict.

Why:
Keeping configuration in one place makes the code easier to reason about,
and swapping providers (e.g., data source) trivial.
"""

from dataclasses import dataclass
from dotenv import load_dotenv
import os
from typing import Dict

load_dotenv()  # Loads variables from .env if the file exists


@dataclass
class Settings:
    """Typed container for project runtime settings."""

    bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat: str = os.getenv("TELEGRAM_CHAT", "")
    tz: str = os.getenv("TIMEZONE", "Asia/Jerusalem")
    indices_raw: str = os.getenv(
        "INDICES",
        "TA-35=TA35.TA,TA-125=^TA125.TA,TA-90=TA90.TA,Banks-5=TA-BANKS.TA",
    )
    update_interval_sec: int = int(os.getenv("UPDATE_INTERVAL_SEC", "60"))
    off_hours_interval_sec: int = int(os.getenv("OFF_HOURS_INTERVAL_SEC", "300"))
    state_path: str = os.getenv("STATE_PATH", "state.json")

    def indices_map(self) -> Dict[str, str]:
        """
        Parse the comma-separated string of name=symbol pairs into a dict.

        Example:
            "TA-35=TA35.TA,TA-125=^TA125.TA" -> {"TA-35": "TA35.TA", "TA-125": "^TA125.TA"}
        """
        out: Dict[str, str] = {}
        for pair in self.indices_raw.split(","):
            if "=" in pair:
                name, symbol = pair.split("=", 1)
                out[name.strip()] = symbol.strip()
        return out


settings = Settings()
