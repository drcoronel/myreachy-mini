// Robot control — proxied to reachy-mini.local:8000 via /daemon
const DAEMON = "/daemon/api";

// AI services — our FastAPI backend on :8001
const AI = "/api/ai";

export async function getRobotStatus() {
  const res = await fetch(`${DAEMON}/status`);
  return res.json() as Promise<{ connected: boolean }>;
}

export async function getDaemonDocs() {
  return `${DAEMON.replace("/api", "")}/docs`;
}

export { AI };
