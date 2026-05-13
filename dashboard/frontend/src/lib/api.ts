const BASE = "/api";

export async function getRobotStatus() {
  const res = await fetch(`${BASE}/robot/status`);
  return res.json() as Promise<{ connected: boolean }>;
}

export async function moveHead(pan: number, tilt: number, roll: number) {
  await fetch(`${BASE}/robot/head/move`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pan, tilt, roll }),
  });
}

export async function resetHead() {
  await fetch(`${BASE}/robot/head/reset`, { method: "POST" });
}

export function getCameraStreamUrl() {
  return `${BASE}/vision/stream`;
}
