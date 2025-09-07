"""
state.py
--------
Minimal local state persistence for the pinned message.

We store the Telegram `message_id` of the pinned message in a small JSON file.
This allows the bot to edit the same message across restarts.
"""

import json
from pathlib import Path
from typing import Optional, Any


class State:
    """Tiny JSON-backed state store for the pinned message id."""

    def __init__(self, path: str = "state.json"):
        self.path = Path(path)
        self._data: dict[str, Any] = {"pinned_message_id": None}

    def load(self) -> None:
        """Load state from disk if present."""
        if self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        """Persist state to disk."""
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @property
    def pinned_message_id(self) -> Optional[int]:
        """Return the saved message id (if any)."""
        return self._data.get("pinned_message_id")

    @pinned_message_id.setter
    def pinned_message_id(self, mid: int) -> None:
        """Update the saved message id."""
        self._data["pinned_message_id"] = mid
