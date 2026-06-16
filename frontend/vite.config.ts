import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev the app is reached through the nginx proxy (PROXY_PORT), so the HMR
// WebSocket must report that port back to the browser. Polling is required for
// file-change detection across the Docker bind mount on macOS.
const proxyPort = Number(process.env.PROXY_PORT) || 8082;

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    allowedHosts: true,
    hmr: { clientPort: proxyPort },
    watch: { usePolling: true, interval: 300 },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
