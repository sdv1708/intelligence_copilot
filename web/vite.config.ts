import type { ServerResponse } from "node:http";

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

/**
 * Without this, a connection refused by the API surfaces as the proxy's own
 * plain-text `500 Internal Server Error`, which the UI can only report as "the
 * health check failed" — indistinguishable from the API answering badly, and
 * silent about the actual cause, which is that nothing is listening.
 *
 * `kind` is how the client recognises it. `ApiUnreachable` is not a class in
 * `core/exceptions.py` and never collides with a real one.
 */
const UNREACHABLE = JSON.stringify({
  detail:
    "The API is not running on http://127.0.0.1:8077. Start it with " +
    "`.venv/Scripts/python.exe -m uvicorn api.main:app --port 8077 --reload`.",
  kind: "ApiUnreachable",
});

/**
 * The API's CORS allowlist in `api/main.py` names port 5173 and nothing else,
 * so `strictPort` makes a taken port a startup failure rather than a silent
 * move to 5174 that then fails every request with an opaque CORS error.
 *
 * The proxy means the client only ever issues same-origin `/api/...` requests:
 * the same relative URLs work in development and when FastAPI serves the built
 * bundle itself, so there is no base-URL branch in the client.
 */
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8077",
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on("error", (_error, _request, target) => {
            // A websocket upgrade hands back a raw socket, which cannot carry
            // a status line. Nothing here proxies websockets, but the handler
            // is called for both, so narrow before writing.
            if (!("writeHead" in target)) {
              target.destroy();
              return;
            }
            const response = target as ServerResponse;
            if (response.headersSent) return;
            response.writeHead(502, { "Content-Type": "application/json" });
            response.end(UNREACHABLE);
          });
        },
      },
    },
  },
  build: {
    // `api/main.py` mounts `web/dist/assets` by that exact name.
    outDir: "dist",
    sourcemap: true,
  },
});
