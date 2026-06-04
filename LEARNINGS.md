# Reachy Mini — Engineering Learnings

Hard-won findings from building on the Reachy Mini SDK. Saves re-learning the same lessons.

---

## DOA (Direction of Arrival)

### Angle convention
The XVF3800 mic array reports DOA via the daemon at `/api/state/doa`:
```json
{"angle": float_rad, "speech_detected": bool}
```
Convention: **0 rad = left, π/2 rad = front, π rad = right**.
Not the usual "0 = forward" convention. Always subtract `π/2` to get a delta from center.

### angle=0.0 is NOT always noise
When the speaker is 90° to one side, the XVF3800 legitimately reports ~0 rad.
Filtering `angle == 0.0` silently drops valid readings.
Instead, filter on minimum delta from forward:
```python
doa_delta = angle - math.pi / 2
if abs(doa_delta) > math.radians(20):   # speaker is meaningfully off-center
    # orient toward speaker
```

### Pointing the head at a DOA angle
Do NOT use `set_target(head=_build_pose(yaw, pitch))` — head pose in `set_target` is
**world/absolute frame**. Commanding (0, 0) while the body rotates causes the head to
counter-rotate and keeps the camera fixed.

Use `look_at_world` with the canonical world-frame projection instead:
```python
p_head = np.array([math.sin(doa_angle), math.cos(doa_angle), 0.0])
T_head = robot.get_current_head_pose()       # 4x4 world-frame head pose
p_world = T_head[:3, :3] @ p_head           # rotate direction into world frame
robot.look_at_world(p_world[0], p_world[1], p_world[2], duration=0)
```
Reference: `examples/sound_doa.py` in the upstream SDK.

---

## SDK Connection

### Always use connection_mode="network" on Mac
The SDK's `auto` connection mode picks `localhost_only` on macOS, which fails to connect
to the robot over WiFi. Always pass explicitly:
```python
ReachyMini(host="reachy-mini.local", connection_mode="network")
```

### WebRTC signaling uses self.host, not daemon_status.wlan_ip
The daemon reports `wlan_ip` as its hotspot IP (e.g. `10.42.0.1`), which is unreachable
from a home network. The signaling server listens on all interfaces, so `reachy-mini.local`
works. Override `_configure_mediamanager` to pass `signalling_host=self.host`.

### DOA polling: use requests, not httpx
`httpx.AsyncClient` raises `CancelledError` (a `BaseException`, not `Exception`) in some
async contexts, crashing pollers that only catch `Exception`. Use synchronous `requests`
via `asyncio.to_thread` for resilient polling:
```python
def _fetch():
    return requests.get(url, timeout=0.5).json()
result = await asyncio.to_thread(_fetch)
```

---

## Motor Control

### Call wake_up() before any set_target/goto_target loop
Without `robot.wake_up()`, motor commands are silently ignored after connection.
Add it after the camera stream is confirmed ready, before starting the control loop.

### set_target head pose is world-frame absolute
Commands passed to `set_target(head=...)` and `goto_target(head=...)` are in world frame,
not body-relative. This means rotating the body while holding head pose fixed causes the
head's neck motors to counter-rotate to maintain the absolute orientation.
Use `look_at_world` / `look_at_image` when you want the head to track a world or image target.

### body_yaw variable must be reset when re-entering LISTENING
If an orientation attempt times out before the robot reaches its target, `current_body_yaw`
in code drifts away from the robot's actual position. Reset to `0.0` on every transition
back to LISTENING so future orient targets are computed from ground truth.

---

## Background DOA Polling

### Latch speech_detected across the async boundary
`speech_detected=True` lasts only ~200ms. The face detection loop runs at ~10Hz and may
miss it. Use a latch: the poller sets True and never clears it; the main loop clears after reading:
```python
# poller
if speech:
    latest[1] = True   # latch

# main loop
angle, speech = latest[0], latest[1]
latest[1] = False      # clear after reading
```

### Catch BaseException in background pollers
`asyncio.CancelledError` is a `BaseException`, not an `Exception`. A poller that only
catches `Exception` will silently die on cancellation without logging. Use:
```python
except BaseException as exc:
    logger.error("Poller crashed: %s", exc, exc_info=True)
    raise
```
