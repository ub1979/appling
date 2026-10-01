import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// @studio → the Studio's dependency-free guided helpers (marker parsing,
// reply clean-up, phase order), shared rather than copied.
export default defineConfig({
  plugins: [react()],
  base: "/",
  resolve: { alias: { "@studio": fileURLToPath(new URL("../../web/src/lib", import.meta.url)) } },
  server: { proxy: { "/api": "http://127.0.0.1:9200", "/avatars": "http://127.0.0.1:9200" } },
});
