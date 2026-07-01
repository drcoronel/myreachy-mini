"""Loads Reachy personality definitions from config/personalities.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).parents[2] / "config" / "personalities.yaml"


def load_personality(name: str | None = None) -> str:
    """Return the system prompt string for the given personality name.

    Falls back to the default defined in the YAML if name is None.
    Raises KeyError if the name doesn't exist in the file.
    """
    data = yaml.safe_load(_CONFIG_PATH.read_text())
    key = name or data["default"]
    return data["personalities"][key]["prompt"]
