import { useEffect, useRef, useState } from "react";

const API = "/api/ai";

type Status = { robot_ready: boolean; tracking: boolean; has_frame: boolean };

const POLL_MS = 2000;

export default function App() {
  const [status, setStatus] = useState<Status>({ robot_ready: false, tracking: false, has_frame: false });
  const [loading, setLoading] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);

  // Poll status every 2s
  useEffect(() => {
    const poll = async () => {
      try {
        const [trackerRes, cameraRes] = await Promise.all([
          fetch(`${API}/tracker/status`),
          fetch(`${API}/camera/status`),
        ]);
        const tracker = await trackerRes.json();
        const camera = await cameraRes.json();
        setStatus({ ...tracker, ...camera });
      } catch {
        // backend not up yet
      }
    };
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => clearInterval(id);
  }, []);

  // Refresh MJPEG src when robot becomes ready
  useEffect(() => {
    if (status.robot_ready && imgRef.current) {
      imgRef.current.src = `${API}/camera/stream?t=${Date.now()}`;
    }
  }, [status.robot_ready]);

  const toggle = async () => {
    setLoading(true);
    await fetch(`${API}/tracker/${status.tracking ? "stop" : "start"}`, { method: "POST" });
    setLoading(false);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <h1 style={{ fontSize: 20, fontWeight: 600 }}>Reachy Mini Dashboard</h1>

      {/* Status bar */}
      <div style={{ display: "flex", gap: 12, fontSize: 13 }}>
        <Chip ok={status.robot_ready} label={status.robot_ready ? "Robot ready" : "Connecting…"} />
        <Chip ok={status.has_frame} label={status.has_frame ? "Camera live" : "No stream"} />
        <Chip ok={status.tracking} label={status.tracking ? "Tracking ON" : "Tracking OFF"} />
      </div>

      {/* Camera feed */}
      <div style={{
        background: "#1a1a1a",
        borderRadius: 8,
        overflow: "hidden",
        aspectRatio: "16/9",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}>
        {status.robot_ready ? (
          <img
            ref={imgRef}
            alt="Reachy camera"
            style={{ width: "100%", height: "100%", objectFit: "contain" }}
          />
        ) : (
          <p style={{ color: "#666", fontSize: 14 }}>
            {status.robot_ready === false ? "Waiting for robot…" : "No camera signal"}
          </p>
        )}
      </div>

      {/* Controls */}
      <button
        onClick={toggle}
        disabled={loading || !status.robot_ready}
        style={{
          padding: "10px 24px",
          borderRadius: 6,
          border: "none",
          cursor: status.robot_ready ? "pointer" : "not-allowed",
          background: status.tracking ? "#c0392b" : "#27ae60",
          color: "#fff",
          fontSize: 15,
          fontWeight: 600,
          opacity: (!status.robot_ready || loading) ? 0.5 : 1,
        }}
      >
        {loading ? "…" : status.tracking ? "Stop Tracking" : "Start Tracking"}
      </button>
    </div>
  );
}

function Chip({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span style={{
      padding: "3px 10px",
      borderRadius: 99,
      background: ok ? "#1e4d2b" : "#2a2a2a",
      color: ok ? "#4caf50" : "#888",
      border: `1px solid ${ok ? "#2e7d32" : "#444"}`,
    }}>
      {label}
    </span>
  );
}
