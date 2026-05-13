import cv2
import numpy as np


def frame_to_bytes(frame: np.ndarray, fmt: str = ".jpg", quality: int = 85) -> bytes:
    params = [cv2.IMWRITE_JPEG_QUALITY, quality] if fmt == ".jpg" else []
    ok, buf = cv2.imencode(fmt, frame, params)
    if not ok:
        raise RuntimeError("Failed to encode frame")
    return buf.tobytes()
