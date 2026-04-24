/// <reference types="vitest" />
import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy backend API + webhooks during dev so the SPA talks to a real
      // Weftlyflow instance without CORS headaches.
      "/api": "http://localhost:5678",
      "/oauth2": "http://localhost:5678",
      "/webhook": "http://localhost:5678",
      "/healthz": "http://localhost:5678",
      "/readyz": "http://localhost:5678",
    },
  },
  build: {
    target: "es2022",
    sourcemap: true,
    outDir: "dist",
    emptyOutDir: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["tests/unit/**/*.spec.ts"],
  },
});
