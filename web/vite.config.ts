import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Builds into the Python package, where FastAPI serves it. The built files are committed so
// running the app needs no Node.js. Our code goes to app.js, unminified so it can be read;
// the React library goes to react.js. Fixed file names keep the committed diff small.
const APP_BANNER =
  "// Generated from web/src/*.tsx by `npm run build` in web/. Do not edit; edit web/src.";
const REACT_BANNER =
  "// The React library, copied in by `npm run build` in web/. Not our code; do not edit.";
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/imageskin/static",
    emptyOutDir: true,
    minify: false,
    modulePreload: { polyfill: false },
    rollupOptions: {
      output: {
        manualChunks: (id) => (id.includes("node_modules") ? "react" : undefined),
        banner: (chunk) => (chunk.isEntry ? APP_BANNER : REACT_BANNER),
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
