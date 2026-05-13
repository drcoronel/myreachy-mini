"""Factory that creates a ReachyMini instance using project settings."""

import logging

from reachy_mini import ReachyMini

from .config import settings

# Audio USB device lookup always fails when connecting over WiFi — not an error.
logging.getLogger("reachy_mini.media.audio_control_utils").setLevel(logging.CRITICAL)


def create_robot(**kwargs) -> ReachyMini:
    """Create a ReachyMini connected to the configured daemon host/port."""
    kwargs.setdefault("host", settings.reachy_host)
    kwargs.setdefault("port", settings.reachy_port)
    return ReachyMini(**kwargs)
