"""Factory that creates a ReachyMini instance using project settings."""

import logging
from typing import Optional

from reachy_mini import ReachyMini
from reachy_mini.media.camera_constants import CameraSpecs, get_camera_specs_by_name
from reachy_mini.media.media_manager import MediaBackend, MediaManager

from .config import settings

# Audio USB device lookup always fails when connecting over WiFi — not an error.
logging.getLogger("reachy_mini.media.audio_control_utils").setLevel(logging.CRITICAL)

logger = logging.getLogger(__name__)


class _VideoOnlyMediaManager(MediaManager):
    """MediaManager whose WebRTC client leaves audio transceivers INACTIVE.

    The standard GstWebRTCClient sets all audio transceivers to SENDRECV, which
    causes the robot's GStreamer pipeline to claim the mic array exclusively.
    This prevents the daemon's DOA processor from receiving audio.
    Setting the transceiver to INACTIVE stops GStreamer from touching the mic,
    leaving the XVF3800 DOA pipeline free.
    """

    def _init_webrtc(
        self,
        log_level: str,
        signalling_host: str,
        signalling_port: int,
        camera_specs: Optional[CameraSpecs] = None,
        daemon_url: str = "",
    ) -> None:
        from reachy_mini.media.webrtc_client_gstreamer import GstWebRTCClient
        from reachy_mini.media.webrtc_utils import find_producer_peer_id_by_name

        # Build the audio-free subclass lazily to avoid importing GStreamer at
        # module load time (GStreamer initialises on import).
        class _VideoOnlyWebRTCClient(GstWebRTCClient):
            def _on_new_transceiver(self, webrtcbin, transceiver):  # type: ignore[override]
                caps = transceiver.get_property("codec-preferences")
                if caps is not None and caps.get_size() > 0:
                    media = caps.get_structure(0).get_string("media")
                    if media == "audio":
                        transceiver.set_property("direction", 1)  # INACTIVE
                        logger.info("Audio transceiver set to INACTIVE (DOA mic freed)")
                        return
                super()._on_new_transceiver(webrtcbin, transceiver)

        peer_id = find_producer_peer_id_by_name(
            signalling_host, signalling_port, "reachymini"
        )
        webrtc_media = _VideoOnlyWebRTCClient(
            log_level=log_level,
            peer_id=peer_id,
            signaling_host=signalling_host,
            signaling_port=signalling_port,
            camera_specs=camera_specs,
        )
        webrtc_media.daemon_url = daemon_url or f"http://{signalling_host}:8000"
        self.camera = webrtc_media
        self.audio = webrtc_media
        self.camera.open()


class _ReachyMiniNetwork(ReachyMini):
    """ReachyMini subclass for connecting over a home network.

    Two overrides:
    1. signalling_host uses self.host instead of daemon_status.wlan_ip.
       The daemon reports the hotspot IP (10.42.x.x) which isn't reachable
       from a home-network client; the signaling server listens on all
       interfaces so self.host (reachy-mini.local) works.
    2. Uses _VideoOnlyMediaManager so GStreamer doesn't claim the mic array,
       leaving the XVF3800 DOA processor functional.
    """

    def _configure_mediamanager(self, media_backend: str, log_level: str) -> MediaManager:
        daemon_status = self.client.get_status()
        self._warn_if_daemon_version_mismatch(daemon_status)

        specs_name = getattr(daemon_status, "camera_specs_name", "")
        camera_specs = get_camera_specs_by_name(specs_name) if specs_name else None

        mbackend = (
            MediaBackend.NO_MEDIA
            if media_backend.lower() == "no_media"
            else MediaBackend.WEBRTC
        )

        return _VideoOnlyMediaManager(
            backend=mbackend,
            log_level=log_level,
            signalling_host=self.host,
            camera_specs=camera_specs,
            daemon_url=self._daemon_http_url,
        )


def create_robot(**kwargs) -> ReachyMini:
    """Create a ReachyMini connected to the configured daemon host/port."""
    kwargs.setdefault("host", settings.reachy_host)
    kwargs.setdefault("port", settings.reachy_port)
    kwargs.setdefault("connection_mode", "network")
    return _ReachyMiniNetwork(**kwargs)
