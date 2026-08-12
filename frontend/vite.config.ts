import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  build: {
    // Landet im Image in /app/static und wird von FastAPI ausgeliefert
    // (gleiche Origin, ADR 0005).
    outDir: "dist",
    sourcemap: true,
  },
  server: {
    // Nur fuer `pnpm dev`: Im Betrieb liegt alles auf derselben Origin, hier
    // schiebt der Dev-Server die API-Aufrufe an das lokale Backend weiter.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
