import { useEffect, useState } from "react";

export function useRobotStatus() {
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const ws = new WebSocket(`ws://${location.host}/ws/status`);
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data) as { connected: boolean };
      setConnected(data.connected);
    };
    return () => ws.close();
  }, []);

  return connected;
}
