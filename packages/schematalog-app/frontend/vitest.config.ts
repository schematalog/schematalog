import { defineConfig } from "vitest/config";

// Standalone from vite.config so unit tests don't pull in the Tailwind build plugin.
// jsdom gives the islands a DOM to enhance; tests live next to the code they cover.
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts"],
    setupFiles: ["./vitest.setup.ts"],
  },
});
