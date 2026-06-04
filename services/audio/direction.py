"""
Direction-of-arrival client for the Reachy Mini daemon.

The XVF3800 mic array processes DOA onboard; the daemon exposes the result at
/api/state/doa as {"angle": float (rad), "speech_detected": bool}.
"""

from __future__ import annotations

import asyncio
import logging

import requests

logger = logging.getLogger(__name__)


class DaemonDOA:
    """Async client for the daemon's onboard DOA endpoint."""

    def __init__(self, host: str, port: int) -> None:
        self._url = f"http://{host}:{port}/api/state/doa"

    async def start(self) -> None:
        logger.info("DaemonDOA started (%s)", self._url)

    async def stop(self) -> None:
        pass

    async def get(self) -> tuple[float | None, bool]:
        """
        Returns (angle_rad, speech_detected).
        angle is relative to the robot head's forward direction.
        Returns (None, False) on error.
        """
        url = self._url

        def _fetch() -> tuple[float | None, bool]:
            try:
                data = requests.get(url, timeout=0.5).json()
                if data is None:
                    return None, False
                return float(data["angle"]), bool(data["speech_detected"])
            except Exception as exc:
                logger.debug("DOA fetch error: %s", exc)
                return None, False

        return await asyncio.to_thread(_fetch)
