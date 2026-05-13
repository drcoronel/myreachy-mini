import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // AI services backend (LLM, vision AI, etc.)
      "/api/ai": "http://localhost:8001",
      // Reachy daemon — robot control, state, media
      "/daemon": {
        target: "http://reachy-mini.local:8000",
        rewrite: (path) => path.replace(/^\/daemon/, ""),
        ws: true,
      },
    },
  },
});
