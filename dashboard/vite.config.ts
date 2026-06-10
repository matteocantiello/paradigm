import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    proxy: {
      "/api": "http://localhost:8060",
    },
  },
  build: {
    outDir: "dist",
    // Single-file-ish output keeps FastAPI static serving trivial
    chunkSizeWarningLimit: 900,
  },
});
