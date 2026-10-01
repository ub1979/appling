import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// @studio → the Studio's dependency-free guided helpers (marker parsing,
// reply clean-up, phase order), shared rather than copied.
export default defineConfig({
  plugins: [react()],
  base: "/",
  resolve: { alias: { "@studio": path.resolve(__dirname, "../../web/src/lib") } },
  server: { proxy: { "/api": "http://127.0.0.1:9200", "/avatars": "http://127.0.0.1:9200" } },
});
