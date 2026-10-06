import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Builds into the Python package, where FastAPI serves it. The built files are committed so
// running the app needs no Node.js. Fixed file names keep the committed diff small.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/imageskin/static",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: "assets/app.js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/[name][extname]",
      },
    },
  },
  // `npm run dev` serves the app with live reload; API calls go to `imageskin serve`.
  server: { proxy: { "/api": "http://127.0.0.1:8000", "/health": "http://127.0.0.1:8000" } },
  test: {
    environment: "jsdom",
    coverage: { include: ["src/**"], exclude: ["src/main.tsx", "src/**/*.test.*"] },
  },
});
