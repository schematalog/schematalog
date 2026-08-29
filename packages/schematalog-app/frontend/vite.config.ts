import { resolve } from "node:path";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// The frontend builds into the FastAPI app's static dir; the Jinja `vite_asset()`
// helper resolves logical entries to these hashed files via the emitted manifest.
// `base` is the URL prefix the app serves the build under (mounted at /static).
export default defineConfig({
  base: "/static/dist/",
  plugins: [tailwindcss()],
  build: {
    manifest: true,
    // Relative to this file: the frontend now lives inside the package it builds for.
    outDir: resolve(__dirname, "../schematalog/app/presentation/webapp/static/dist"),
    emptyOutDir: true,
    rollupOptions: {
      // One entry per island/stylesheet (Vite content-hashes each for cache-busting).
      input: {
        app: resolve(__dirname, "src/styles/app.css"),
        clipboard: resolve(__dirname, "src/islands/clipboard.ts"),
        editor: resolve(__dirname, "src/islands/editor.ts"),
        slugify: resolve(__dirname, "src/islands/slugify.ts"),
        theme: resolve(__dirname, "src/islands/theme.ts"),
      },
    },
  },
});
