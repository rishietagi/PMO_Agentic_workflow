import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// Builds the SPA into ../app/spa, which FastAPI serves. During `npm run dev`
// the /api calls are proxied to the running uvicorn server.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  build: {
    outDir: "../app/spa",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
