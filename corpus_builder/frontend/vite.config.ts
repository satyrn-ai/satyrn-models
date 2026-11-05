import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The built bundle is written directly into the Python package so that the Flask
// app can serve it as static files. During `npm run dev`, API calls are proxied
// to the Flask server started with `satyrn-dataset viewer <file>`.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "../src/satyrn/dataset/viewer/static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:5000",
    },
  },
});
