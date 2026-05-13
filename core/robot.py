"""Thin wrapper around reachy2-sdk that handles connection lifecycle."""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from .config import settings

logger = logging.getLogger(__name__)


class ReachyMini:
    """Context-manager-friendly wrapper for the Reachy Mini SDK."""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self._host = host or settings.reachy_host
        self._port = port or settings.reachy_port
        self._reachy: Any = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        try:
            from reachy2_sdk import ReachySDK  # type: ignore[import]

            self._reachy = ReachySDK(host=self._host)
            logger.info("Connected to Reachy at %s", self._host)
        except Exception as exc:
            logger.error("Failed to connect to Reachy: %s", exc)
            raise

    def disconnect(self) -> None:
        if self._reachy is not None:
            with contextlib.suppress(Exception):
                self._reachy.disconnect()
            self._reachy = None
            logger.info("Disconnected from Reachy")

    def __enter__(self) -> "ReachyMini":
        self.connect()
        return self

    def __exit__(self, *_: Any) -> None:
        self.disconnect()

    # ------------------------------------------------------------------
    # Convenience accessors (delegated to SDK)
    # ------------------------------------------------------------------

    @property
    def sdk(self) -> Any:
        """Direct access to the underlying reachy2-sdk instance."""
        if self._reachy is None:
            raise RuntimeError("Not connected. Call connect() or use as context manager.")
        return self._reachy

    @property
    def is_connected(self) -> bool:
        return self._reachy is not None
