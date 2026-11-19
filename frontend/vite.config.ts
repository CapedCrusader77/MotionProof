import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } },
  },
  build: {
    // three.js (about 940 kB) is its own chunk, loaded only by the screens with a 3D viewport;
    // manual chunking is left to the bundler, which otherwise pulled it into every page load.
    chunkSizeWarningLimit: 1000,
  },
});
